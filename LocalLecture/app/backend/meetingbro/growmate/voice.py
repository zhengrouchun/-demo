from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime
import multiprocessing as mp
from pathlib import Path
import queue
import sqlite3
from typing import Any

from .repository import new_id
from .transcript import export_transcript, saved_segments
from .voice_worker import run_voice_worker


class VoiceController:
    """Browser connections observe a session; they do not own its lifetime."""
    def __init__(self, repo, directory: Path):
        self.repo = repo
        self.directory = directory
        self.transcript_db = directory / "transcripts.db"
        self.export_root = directory / "transcripts"
        self.process = None
        self.commands = None
        self.events = None
        self.task = None
        self.listeners: set[Any] = set()
        self.current_id = None
        self.phase = "idle"
        self.detail = "准备好后，开始实时转文字。"
        self.segments: dict[str, dict] = {}
        self.stats = {}
        self.lock = asyncio.Lock()
        with repo.transaction():
            repo.db.execute("UPDATE voice_sessions SET status='interrupted',error='上次服务意外退出；已经识别的文字仍可恢复。' WHERE status IN ('loading','running','paused','draining')")

    def active(self):
        return self.process is not None and self.process.is_alive()

    def snapshot(self):
        rows = self.repo.rows("SELECT * FROM voice_sessions WHERE id=?", (self.current_id,)) if self.current_id else []
        return {"type": "voice_snapshot", "payload": {"phase": self.phase, "detail": self.detail, "session": rows[0] if rows else None, "segments": sorted(self.segments.values(), key=lambda s: s["start_time"]), "stats": self.stats, "worker_pid": self.process.pid if self.active() else None, "resources_released": not self.active()}}

    async def broadcast(self, event):
        for listener in list(self.listeners):
            try:
                await asyncio.wait_for(listener.send_json(event), timeout=2)
            except Exception:
                self.listeners.discard(listener)

    async def start(self, options):
        async with self.lock:
            if self.active() or (self.task and not self.task.done()):
                raise ValueError("已有转写任务，请先结束并等待资源释放。")
            if options["source"] not in {"mic", "system", "mixed"} or options["model"] not in {"tiny", "base", "small", "funasr-nano-gguf-q8_0"} or options["language"] not in {"zh", "en", "auto"}:
                raise ValueError("声音来源、模型或识别语言无效。")
            if options["model"] == "funasr-nano-gguf-q8_0" and options["source"] != "system":
                raise ValueError("Fun-ASR-Nano 首版仅支持系统声音。")
            identifier = new_id()
            stamp = datetime.now().astimezone().isoformat()
            with self.repo.transaction():
                self.repo.db.execute("INSERT INTO voice_sessions(id,title,source,model,language,started_at,status) VALUES(?,?,?,?,?,?,'loading')", (identifier, options["title"].strip() or "课堂逐字稿", options["source"], options["model"], options["language"], stamp))
            context = mp.get_context("spawn")
            self.commands = context.Queue()
            self.events = context.Queue()
            self.current_id = identifier
            self.phase = "loading"
            self.detail = "正在加载本地识别模型，请等待。"
            self.segments = {}
            self.stats = {}
            payload = dict(options, id=identifier, app_db=str(self.repo.path), transcript_db=str(self.transcript_db))
            self.process = context.Process(target=run_voice_worker, args=(payload, self.commands, self.events), name="LocalLecture-ASR", daemon=True)
            try:
                self.process.start()
            except Exception:
                with self.repo.transaction():
                    self.repo.db.execute("UPDATE voice_sessions SET status='interrupted',error='识别进程无法启动。' WHERE id=?", (identifier,))
                self.phase = "error"
                self.detail = "识别进程无法启动，请重启服务。"
                raise
            self.task = asyncio.create_task(self._pump())
            return self.snapshot()["payload"]

    async def command(self, command):
        if command not in {"pause", "resume", "stop"}:
            raise ValueError("转写操作无效。")
        if not self.active():
            raise ValueError("当前没有正在进行的转写。")
        if command == "stop":
            if self.phase == "loading":
                # No audio is being captured yet. Cancel model download/loading.
                self.detail = "已取消加载，正在释放资源。"
                self.process.terminate()
            else:
                self.phase = "draining"
                self.detail = "正在处理剩余声音，请等待完整逐字稿保存。"
                self.commands.put(command)
        elif self.phase in {"running", "paused"}:
            self.commands.put(command)
        await self.broadcast(self.snapshot())

    def _event(self, event):
        kind = event["type"]
        payload = event.get("payload") or {}
        if kind == "loading":
            self.detail = payload["message"]
        elif kind == "session_state":
            self.stats = payload
            if payload["state"] in {"running", "paused"} and self.phase != "draining":
                self.phase = payload["state"]
                self.detail = "声音正在实时转成文字，识别内容会自动保存。" if self.phase == "running" else "已暂停。继续后恢复转写。"
                backlog_seconds = payload.get("audio_input_backlog_seconds", 0) or 0  # 读取尚未进入识别的音频时长。
                if self.phase == "running" and backlog_seconds >= 3:  # 避免用户将处理延迟误认为已经漏写。
                    self.detail = f"还有约 {backlog_seconds:.0f} 秒声音等待识别；结束后会继续处理，请等待保存完成。"
            with self.repo.transaction():
                self.repo.db.execute("UPDATE voice_sessions SET meeting_id=?,elapsed_seconds=?,status=? WHERE id=?", (payload["meeting_id"], payload.get("elapsed_seconds", 0), self.phase, self.current_id))
        elif kind == "transcript_segment":
            self.segments[payload["id"]] = payload
        elif kind == "transcript_segment_removed":
            self.segments.pop(payload.get("segment_id") or payload.get("id"), None)
        elif kind == "draining":
            self.phase = "draining"
            self.detail = payload["message"]
        elif kind == "worker_done":
            self._completed = payload.get("complete", True)
            self._elapsed = payload.get("elapsed_seconds", 0)
            if payload.get("dropped_chunks", 0):
                self._worker_error = f"识别速度跟不上，丢弃了 {payload['dropped_chunks']} 个音频块。请核对逐字稿，并尝试更小的模型。"
        elif kind == "worker_error":
            self._worker_error = "识别出错：" + payload["message"][:500]
            self._save_voice_warning()  # 立即保存警告，刷新页面也能看到失败原因。
        elif kind == "error":
            self.detail = "转写提示：" + payload.get("message", "请检查声音来源。")[:500]
            if payload.get("code") in {"audio_input_queue_dropped", "audio_source_crashed", "session_loop", "asr_error", "audio_drop", "audio_drops_sustained", "asr_buffer_overflow"}:
                self._worker_error = self.detail
                self._save_voice_warning()  # 后续运行状态更新不再掩盖已经发生的漏音错误。

    def _save_voice_warning(self):
        """将影响完整性的错误保存在当前录音记录，而不只短暂显示状态文字。"""
        with self.repo.transaction():  # 使用仓库事务确保错误信息写入成功。
            self.repo.db.execute(  # 只更新本次录音的警告，保留已有转写内容。
                "UPDATE voice_sessions SET error=? WHERE id=?", (self._worker_error, self.current_id)
            )

    async def _pump(self):
        self._completed = False
        self._worker_error = None
        self._elapsed = 0
        try:
            while True:
                batch = []
                for _ in range(100):
                    try:
                        batch.append(self.events.get_nowait())
                    except queue.Empty:
                        break
                for event in batch:
                    self._event(event)
                if batch:
                    await self.broadcast(self.snapshot())
                if not self.process.is_alive():
                    await asyncio.to_thread(self.process.join, 2)
                    # Join ensures the multiprocessing queue feeder finished.
                    while True:
                        try:
                            self._event(self.events.get_nowait())
                        except queue.Empty:
                            break
                    break
                await asyncio.sleep(.2)
            ended = datetime.now().astimezone().isoformat()
            with self.repo.transaction():
                self.repo.db.execute("UPDATE voice_sessions SET status=?,ended_at=?,elapsed_seconds=MAX(elapsed_seconds,?),error=? WHERE id=?", ("ended" if self._completed else "interrupted", ended, self._elapsed, self._worker_error or (None if self._completed else "转写进程已退出，已保存的文字可以恢复导出。"), self.current_id))
            row = self.repo.rows("SELECT * FROM voice_sessions WHERE id=?", (self.current_id,))[0]
            segments = saved_segments(self.transcript_db, row["meeting_id"])
            self.segments = {s["id"]: s for s in segments}
            try:
                path = export_transcript(row, segments, self.export_root)
                with self.repo.transaction():
                    self.repo.db.execute("UPDATE voice_sessions SET export_path=? WHERE id=?", (str(path), self.current_id))
                self.phase = "ended" if self._completed else "interrupted"
                self.detail = "逐字稿已保存，识别进程已退出，模型和音频内存已释放。" if self._completed else "转写已中断，已保存的文字可以下载。识别资源已释放。"
            except OSError:
                self.phase = "export_failed"
                self.detail = "文字已保存在数据库，但 Markdown 导出失败。请检查磁盘空间后重试下载。识别资源已释放。"
                with self.repo.transaction():
                    self.repo.db.execute("UPDATE voice_sessions SET status='export_failed' WHERE id=?", (self.current_id,))
        finally:
            for ipc in (self.commands, self.events):
                if ipc:
                    ipc.close()
                    ipc.join_thread()
            await self.broadcast(self.snapshot())

    def export(self, identifier):
        rows = self.repo.rows("SELECT * FROM voice_sessions WHERE id=?", (identifier,))
        if not rows:
            raise ValueError("找不到这份逐字稿。")
        row = rows[0]
        segments = saved_segments(self.transcript_db, row["meeting_id"])
        path = export_transcript(row, segments, self.export_root)
        with self.repo.transaction():
            self.repo.db.execute("UPDATE voice_sessions SET export_path=? WHERE id=?", (str(path), identifier))
        return path

    def delete_history(self, identifier):
        rows = self.repo.rows("SELECT * FROM voice_sessions WHERE id=?", (identifier,))
        if not rows:
            raise ValueError("找不到这份逐字稿。")
        if identifier == self.current_id and (self.active() or (self.task and not self.task.done())):
            raise ValueError("正在转写的课程不能删除。请先结束并等待保存完成。")
        row = rows[0]
        export_path = Path(row["export_path"]).resolve() if row["export_path"] else None
        if export_path and not export_path.is_relative_to(self.export_root.resolve()):
            raise ValueError("逐字稿路径不在课程目录内，已停止删除。")
        if export_path and not export_path.name.endswith(f"_{identifier[:8]}.md"):
            raise ValueError("逐字稿文件名与课程不匹配，已停止删除。")
        pending_path = export_path.with_suffix(".md.pending-delete") if export_path and export_path.exists() else None
        if pending_path:
            if pending_path.exists():
                raise ValueError("发现尚未清理的删除备份，请先检查课程目录。")
            export_path.replace(pending_path)
        try:
            with closing(sqlite3.connect(self.repo.path, timeout=10)) as connection, connection:
                has_transcript_db = self.transcript_db.exists()
                if has_transcript_db:
                    connection.execute("ATTACH DATABASE ? AS transcript_data", (str(self.transcript_db),))
                connection.execute("BEGIN IMMEDIATE")
                if has_transcript_db and row["meeting_id"]:
                    for table in ("transcript_segments", "summary_snapshots", "notes", "speakers"):
                        connection.execute(f"DELETE FROM transcript_data.{table} WHERE meeting_id=?", (row["meeting_id"],))
                    connection.execute("DELETE FROM transcript_data.meetings WHERE id=?", (row["meeting_id"],))
                connection.execute("DELETE FROM voice_sessions WHERE id=?", (identifier,))
                connection.commit()
        except Exception:
            if pending_path and pending_path.exists():
                pending_path.replace(export_path)
            raise
        if pending_path:
            try:
                pending_path.unlink()
            except OSError:
                pending_path.replace(export_path)
                raise
        if self.current_id == identifier:
            self.current_id = None
            self.segments = {}
            self.stats = {}
            self.phase = "idle"
            self.detail = "课程已删除。"

    async def close(self):
        if self.active():
            if self.phase == "loading":
                self.process.terminate()
            else:
                self.commands.put("stop")
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=610)
            except asyncio.TimeoutError:
                self.process.terminate()
                await asyncio.to_thread(self.process.join, 5)
        if self.task and not self.task.done():
            await self.task
