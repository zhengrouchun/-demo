"""Read saved text and export Markdown without importing ML libraries."""
from datetime import datetime
from contextlib import closing
from pathlib import Path
import re
import sqlite3


def saved_segments(db_path: Path, meeting_id: str | None):
    if not meeting_id or not db_path.exists():
        return []
    with closing(sqlite3.connect(db_path, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT id,start_time,end_time,text,confidence,quality FROM transcript_segments WHERE meeting_id=? ORDER BY start_time,created_at", (meeting_id,))]


def clock(seconds):
    total = max(0, int(seconds or 0))
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def safe_filename(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:80]
    name = re.sub(r"\s+", "_", name) or "课堂逐字稿"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "课程_" + name
    return name


def export_transcript(session, segments, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    date = datetime.fromisoformat(session["started_at"]).astimezone().strftime("%Y-%m-%d")
    filename = f"{safe_filename(session['title'])}_{date}_{session['id'][:8]}.md"
    path = root / filename
    sources = {"mic": "麦克风", "system": "电脑系统声音", "mixed": "系统声音与麦克风", "fixture": "测试音频"}
    duration = max([session["elapsed_seconds"] or 0, *(s["end_time"] for s in segments)])
    title = session["title"].replace("\r", " ").replace("\n", " ")
    lines = [f"# {title}", "", f"- 日期：{date}", f"- 时长：{clock(duration)}", f"- 音频来源：{sources.get(session['source'], session['source'])}", f"- 识别语言：{session['language']}", f"- 识别模型：Whisper {session['model']} / CPU int8", "", "---", "", "## 课堂逐字稿", ""]
    if session["status"] not in ("ended", "export_failed"):
        lines += ["这是一份恢复或中途导出的逐字稿，包含已经保存的文字。", ""]
    if session.get("error"):  # 导出后仍保留漏音或识别失败提示，便于核对原视频。
        lines += ["转写完整性提示：" + session["error"].replace("\r", " ").replace("\n", " "), ""]
    for segment in segments:
        lines += [f"### [{clock(segment['start_time'])} - {clock(segment['end_time'])}]", "", segment["text"].strip(), ""]
    if not segments:
        lines += ["本次尚未识别到文字。", ""]
    temp = path.with_suffix(".md.tmp")
    temp.write_text("\n".join(lines), encoding="utf-8")
    temp.replace(path)
    return path
