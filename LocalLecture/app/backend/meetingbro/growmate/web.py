from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import zipfile

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .ai import GroqProvider, SecretStore, companion_prompt
from .repository import Repository, new_id
from .transcript import safe_filename, saved_segments
from .voice import VoiceController

ROOT = Path(__file__).resolve().parents[4]
LOG = logging.getLogger("growmate")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FocusInput(Input):
    mode: str = "normal"
    minutes: int = Field(default=25, ge=1, le=180)
    rest: int = Field(default=5, ge=1, le=60)
    cycles: int = Field(default=1, ge=1, le=12)
    task_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class FocusTaskDecisionInput(Input):
    completed: bool


class TaskLink(Input):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    line_index: int = Field(ge=0)


class TaskMetadataInput(Input):
    tags: list[str] = Field(default_factory=list, max_length=12)
    due_date: str | None = None


class NoteInput(Input):
    id: str | None = None
    title: str = Field(default="", max_length=200)
    markdown: str = Field(default="", max_length=500_000)
    task_links: list[TaskLink] | None = Field(default=None, max_length=5000)
    base_updated_at: str | None = None


class MoodInput(Input):
    mood: str
    content: str = Field(default="", max_length=20_000)


class HealthInput(Input):
    date: str | None = None
    breakfast: str = Field(default="", max_length=5000)
    lunch: str = Field(default="", max_length=5000)
    dinner: str = Field(default="", max_length=5000)
    snacks: str = Field(default="", max_length=5000)
    stomach_note: str = Field(default="", max_length=10_000)
    general_note: str = Field(default="", max_length=10_000)


class ReminderInput(Input):
    id: str | None = None
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(default="小狗在等你一起照顾自己。", max_length=300)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    enabled: bool = True


class AISettings(Input):
    key: str | None = Field(default=None, max_length=500)
    remember: bool = False
    model: str = Field(default="openai/gpt-oss-20b", min_length=1, max_length=100)


class ChatInput(Input):
    conversation_id: str | None = None
    mode: str = "chat"
    style: str = "listen"
    content: str = Field(min_length=1, max_length=6000)
    include_today_health: bool = False


class VoiceInput(Input):
    title: str = Field(default="课堂逐字稿", max_length=200)
    source: str = "system"
    model: str = "small"
    language: str = "zh"
    audio_device: str = Field(default="", max_length=200)
    loopback_device: str = Field(default="", max_length=300)


def desktop_reminder(title, body):
    if os.name == "nt":
        script = ROOT / "scripts" / "growmate-notify.ps1"
        return subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Title", title, "-Body", body], creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


def create_app(directory: Path | None = None, *, enable_notifications=True, provider_factory=GroqProvider):
    directory = directory or ROOT / "data" / "growmate"

    @asynccontextmanager
    async def lifespan(app):
        directory.mkdir(parents=True, exist_ok=True)
        app.state.repo = Repository(directory / "growmate.db")
        app.state.secrets = SecretStore(directory / "groq.key")
        app.state.provider = provider_factory(app.state.secrets)
        app.state.voice = VoiceController(app.state.repo, directory)
        app.state.chat_lock = asyncio.Lock()
        app.state.notices = []
        notification_processes = []

        async def tick():
            while True:
                try:
                    with app.state.repo.transaction():
                        app.state.repo.settle_focus()
                        app.state.repo.apply_health()
                    due = app.state.repo.due_reminders()
                    for reminder in due:
                        app.state.notices.append(dict(reminder, delivered_at=datetime.now().astimezone().isoformat()))
                        app.state.notices = app.state.notices[-30:]
                        if enable_notifications:
                            process = desktop_reminder(reminder["title"], reminder["body"])
                            if process:
                                notification_processes.append(process)
                    notification_processes[:] = [p for p in notification_processes if p.poll() is None]
                except Exception:
                    LOG.exception("GrowMate background check failed")
                await asyncio.sleep(1)

        tick_task = asyncio.create_task(tick())
        try:
            yield
        finally:
            tick_task.cancel()
            await asyncio.gather(tick_task, return_exceptions=True)
            await app.state.voice.close()
            for process in notification_processes:
                if process.poll() is None:
                    process.terminate()
            app.state.repo.close()

    app = FastAPI(title="GrowMate 本地网页版", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host')}"
            if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "仅允许本地 GrowMate 页面访问。"}, status_code=403)
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-growmate-request") != "1":
                return JSONResponse({"detail": "请从 GrowMate 页面执行操作。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(OSError)
    async def file_error(request, exc):
        LOG.error("Local file operation failed: %s", type(exc).__name__)
        return JSONResponse({"detail": "本地文件操作失败，请检查磁盘空间、文件权限或是否被其他程序占用。已经保存的记录仍可恢复。"}, status_code=500)

    def repo():
        return app.state.repo

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": "GrowMate", "ready": True, "learning_tasks": 1}

    @app.post("/api/shutdown")
    async def shutdown():
        callback = getattr(app.state, "request_shutdown", None)
        if callback is None:
            raise ValueError("当前运行方式不支持页面退出，请从启动窗口退出。")
        callback()
        return {"ok": True}

    @app.get("/api/state")
    async def state():
        return dict(repo().state(), ai=app.state.secrets.status(), notices=app.state.notices, voice=app.state.voice.snapshot()["payload"])

    @app.post("/api/focus/start")
    async def focus_start(data: FocusInput):
        repo().start_focus(**data.model_dump())
        return {"ok": True}

    @app.post("/api/focus/interrupt")
    async def focus_interrupt():
        repo().interrupt_focus()
        return {"ok": True}

    @app.post("/api/focus/heartbeat")
    async def focus_heartbeat():
        repo().heartbeat()
        return {"ok": True}

    @app.post("/api/focus/{session_id}/task-decision")
    async def focus_task_decision(session_id: str, data: FocusTaskDecisionInput):
        return repo().decide_focus_task(session_id, data.completed)

    @app.post("/api/tree/plant")
    async def plant(data: dict):
        repo().plant(data.get("species"))
        return {"ok": True}

    @app.post("/api/tree/water")
    async def water(data: dict):
        repo().water(data.get("amount"))
        return {"ok": True}

    @app.post("/api/notes")
    async def save_note(data: NoteInput):
        identifier = repo().save_note(data.title, data.markdown, data.id, [link.model_dump() for link in data.task_links] if data.task_links is not None else None, data.base_updated_at)
        return {"id": identifier, "note": repo().note(identifier)}

    @app.patch("/api/notes/{identifier}/tasks/{task_id}")
    async def task_metadata(identifier: str, task_id: str, data: TaskMetadataInput):
        return repo().update_task(identifier, task_id, data.tags, data.due_date)

    @app.delete("/api/notes/{identifier}")
    async def delete_note(identifier: str):
        with repo().transaction():
            repo().db.execute("DELETE FROM notes WHERE id=?", (identifier,))
            repo().db.execute("DELETE FROM note_images WHERE note_id=?", (identifier,))
            repo().db.execute("DELETE FROM note_tasks WHERE note_id=?", (identifier,))
        # Keep image files for recoverability; backups include them.
        return {"ok": True}

    @app.post("/api/notes/{identifier}/images")
    async def upload_image(identifier: str, request: Request):
        if not repo().rows("SELECT id FROM notes WHERE id=?", (identifier,)):
            raise HTTPException(404, "请先保存备忘录。")
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > 5 * 1024 * 1024:
                raise HTTPException(413, "每张图片最多 5 MB。")
        data = bytes(chunks)
        extension = None
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        elif data.startswith(b"\xff\xd8\xff"):
            extension = "jpg"
        elif data.startswith((b"GIF87a", b"GIF89a")):
            extension = "gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            extension = "webp"
        if not extension:
            raise ValueError("请选择 PNG、JPEG、GIF 或 WebP 图片。")
        filename = f"{new_id()}.{extension}"
        image_dir = directory / "images"
        image_dir.mkdir(exist_ok=True)
        (image_dir / filename).write_bytes(data)
        uri = f"/api/images/{filename}"
        with repo().transaction():
            repo().db.execute("INSERT INTO note_images VALUES(?,?,?,?)", (new_id(), identifier, uri, datetime.now().astimezone().isoformat()))
        return {"uri": uri}

    @app.get("/api/images/{filename}")
    async def image(filename: str):
        if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|gif|webp)", filename):
            raise HTTPException(404)
        path = directory / "images" / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/api/notes/{identifier}/download")
    async def download_note(identifier: str):
        rows = repo().rows("SELECT * FROM notes WHERE id=?", (identifier,))
        if not rows:
            raise HTTPException(404)
        note = rows[0]
        images = repo().rows("SELECT uri FROM note_images WHERE note_id=?", (identifier,))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            text = f"# {note['title']}\n\n{note['markdown']}\n"
            for entry in images:
                filename = entry["uri"].rsplit("/", 1)[-1]
                path = directory / "images" / filename
                if path.is_file():
                    z.write(path, f"images/{filename}")
                    text = text.replace(entry["uri"], f"images/{filename}")
            z.writestr(safe_filename(note["title"]) + ".md", text)
            z.writestr("tasks.json", json.dumps(repo().note(identifier)["tasks"], ensure_ascii=False, indent=2))
        archive.seek(0)
        return StreamingResponse(archive, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="note-{identifier[:8]}.zip"'})

    @app.post("/api/health-log")
    async def health_log(data: HealthInput):
        repo().save_health(data.model_dump())
        return {"ok": True}

    @app.post("/api/mood")
    async def mood(data: MoodInput):
        repo().save_mood(data.mood, data.content)
        return {"ok": True}

    @app.post("/api/reminders")
    async def reminder(data: ReminderInput):
        repo().save_reminder(data.model_dump())
        return {"ok": True}

    @app.delete("/api/reminders/{identifier}")
    async def delete_reminder(identifier: str):
        with repo().transaction():
            repo().db.execute("DELETE FROM reminders WHERE id=?", (identifier,))
        return {"ok": True}

    @app.put("/api/ai/settings")
    async def ai_settings(data: AISettings):
        if data.key is not None:
            app.state.secrets.set(data.key, data.remember)
        with repo().transaction():
            repo().set_setting("ai_model", data.model.strip())
        return app.state.secrets.status()

    @app.post("/api/ai/memories")
    async def add_memory(data: dict):
        content = str(data.get("content", "")).strip()
        if not content or len(content) > 1000:
            raise ValueError("记忆内容应为 1—1000 个字符。")
        with repo().transaction():
            repo().db.execute("INSERT INTO ai_memories VALUES(?,?,?,1)", (new_id(), content, datetime.now().astimezone().isoformat()))
        return {"ok": True}

    @app.delete("/api/ai/memories/{identifier}")
    async def delete_memory(identifier: str):
        with repo().transaction():
            repo().db.execute("DELETE FROM ai_memories WHERE id=?", (identifier,))
        return {"ok": True}

    @app.get("/api/ai/conversations/{identifier}")
    async def messages(identifier: str):
        return repo().rows("SELECT * FROM ai_messages WHERE conversation_id=? ORDER BY created_at,rowid", (identifier,))

    @app.post("/api/ai/chat")
    async def chat(data: ChatInput):
        if data.mode not in {"chat", "food", "stomach", "emotion"} or data.style not in {"listen", "comfort", "solve"}:
            raise ValueError("陪伴模式无效。")
        async with app.state.chat_lock:
            conversation = data.conversation_id
            if conversation and not repo().rows("SELECT id FROM ai_conversations WHERE id=?", (conversation,)):
                raise ValueError("对话不存在，请新建对话。")
            history = repo().rows("SELECT role,content FROM ai_messages WHERE conversation_id=? ORDER BY created_at DESC,rowid DESC LIMIT 19", (conversation,)) if conversation else []
            history.reverse()
            memories = [row["content"] for row in repo().rows("SELECT content FROM ai_memories WHERE enabled=1 ORDER BY created_at DESC LIMIT 20")]
            health = repo().rows("SELECT * FROM daily_health_logs WHERE date=?", (datetime.now().astimezone().date().isoformat(),)) if data.include_today_health else []
            prompt = companion_prompt(data.mode, data.style, memories, health[0] if health else None)
            response = await app.state.provider.chat([{"role": "system", "content": prompt}, *history, {"role": "user", "content": data.content}], repo().setting("ai_model", "openai/gpt-oss-20b"))
            stamp = datetime.now().astimezone().isoformat()
            with repo().transaction():
                if not conversation:
                    conversation = new_id()
                    repo().db.execute("INSERT INTO ai_conversations VALUES(?,?,?,?,?)", (conversation, data.content[:40], data.mode, stamp, stamp))
                repo().db.execute("UPDATE ai_conversations SET updated_at=? WHERE id=?", (stamp, conversation))
                repo().db.execute("INSERT INTO ai_messages VALUES(?,?,?,?,?)", (new_id(), conversation, "user", data.content, stamp))
                repo().db.execute("INSERT INTO ai_messages VALUES(?,?,?,?,?)", (new_id(), conversation, "assistant", response, stamp))
            return {"conversation_id": conversation, "content": response}

    @app.get("/api/audio/devices")
    async def devices():
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "meetingbro.growmate.devices", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=20)
            if process.returncode:
                raise ValueError("声音设备读取失败，请检查 Windows 音频设备和权限。")
            return json.loads(out.decode())
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ValueError("声音设备读取超时，请重新连接设备后重试。") from None

    @app.post("/api/voice/start")
    async def voice_start(data: VoiceInput):
        return await app.state.voice.start(data.model_dump())

    @app.post("/api/voice/{command}")
    async def voice_command(command: str):
        await app.state.voice.command(command)
        return {"ok": True}

    @app.get("/api/voice/history/{identifier}")
    async def voice_history(identifier: str):
        rows = repo().rows("SELECT * FROM voice_sessions WHERE id=?", (identifier,))
        if not rows:
            raise HTTPException(404)
        return {"session": rows[0], "segments": saved_segments(app.state.voice.transcript_db, rows[0]["meeting_id"])}

    @app.get("/api/voice/history/{identifier}/download")
    async def voice_download(identifier: str):
        path = app.state.voice.export(identifier)
        return FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")

    @app.delete("/api/voice/history/{identifier}")
    async def voice_delete(identifier: str):
        app.state.voice.delete_history(identifier)
        return {"ok": True}

    @app.websocket("/api/voice/socket")
    async def voice_socket(ws: WebSocket):
        host = ws.headers.get("host")
        if host not in {"testserver", "127.0.0.1:8876", "localhost:8876", "127.0.0.1:5173", "localhost:5173"} or ws.headers.get("origin") not in {None, f"http://{host}", f"https://{host}"}:
            await ws.close(code=1008)
            return
        await ws.accept()
        controller = app.state.voice
        controller.listeners.add(ws)
        try:
            await ws.send_json(controller.snapshot())
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            controller.listeners.discard(ws)

    @app.get("/api/backup")
    async def backup():
        backup_dir = directory / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = backup_dir / f"GrowMate备份-{stamp}.zip"
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for db_name in ("growmate.db", "transcripts.db"):
                source = directory / db_name
                if source.exists():
                    snapshot = backup_dir / (db_name + ".snapshot")
                    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(snapshot)) as dst:
                        src.backup(dst)
                    archive.write(snapshot, db_name)
                    snapshot.unlink()
            for folder in ("images", "transcripts"):
                for path in (directory / folder).glob("*"):
                    if path.is_file():
                        archive.write(path, f"{folder}/{path.name}")
            archive.writestr("恢复说明.txt", "先停止 GrowMate 服务，再把数据库与 images、transcripts 文件夹放回 LocalLecture/data/growmate。API Key 不在备份中，需要重新填写。")
        return FileResponse(output, filename=output.name)

    dist = ROOT / "app" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def run():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8876, log_level="info", timeout_graceful_shutdown=620))
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    run()
