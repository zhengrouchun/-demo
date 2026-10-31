"""Learning-task metadata, reconciliation and additive migration."""
from datetime import date, datetime
from contextlib import closing
import json
import re
import sqlite3
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS note_tasks(id TEXT PRIMARY KEY,note_id TEXT NOT NULL,line_index INTEGER NOT NULL,text TEXT NOT NULL,completed INTEGER NOT NULL DEFAULT 0,tags TEXT NOT NULL DEFAULT '[]',due_date TEXT,completion_rewarded INTEGER NOT NULL DEFAULT 0,first_completed_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS tasks_by_note ON note_tasks(note_id,line_index);
CREATE UNIQUE INDEX IF NOT EXISTS one_task_completion_reward ON water_transactions(source_id) WHERE type='task_completion_reward';
CREATE UNIQUE INDEX IF NOT EXISTS one_task_focus_bonus ON water_transactions(source_id) WHERE type='task_focus_bonus';
"""
MIGRATION = "learning_tasks_v1"

def parse_tasks(markdown):
    result, fence = [], None
    for index, raw in enumerate(markdown.split("\n")):
        text = raw.removesuffix("\r")
        if fence:
            close = re.fullmatch(r" {0,3}(`{3,}|~{3,})[ \t]*", text)
            if close and close[1][0] == fence[0] and len(close[1]) >= fence[1]: fence = None
            continue
        opening = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", text)
        if opening and (opening[1][0] == "~" or "`" not in opening[2]):
            fence = (opening[1][0], len(opening[1])); continue
        if re.match(r"(?: {4}|\t)", text): continue
        task = re.fullmatch(r"( {0,3}- \[)([ xX])(\](?:[ \t]+(.*))?)", text)
        if task: result.append({"line_index": index, "text": task[4] or "", "completed": task[2] != " ", "marker_offset": len(task[1])})
    if len(result) > 5000: raise ValueError("单份备忘录最多支持 5000 条任务。")
    return result

def match_existing(parsed, existing):
    assigned, used = {}, set()
    if len(parsed) == len(existing):
        for new, old in zip(parsed, existing):
            if new["text"] == old["text"]:
                assigned[new["line_index"]] = old["id"]; used.add(old["id"])
    for new in parsed:
        if new["line_index"] in assigned: continue
        old = next((old for old in existing if old["id"] not in used and old["text"] == new["text"]), None)
        if old: assigned[new["line_index"]] = old["id"]; used.add(old["id"])
    new_left = [new for new in parsed if new["line_index"] not in assigned]
    old_left = [old for old in existing if old["id"] not in used]
    if len(new_left) == len(old_left):
        for new, old in zip(new_left, old_left): assigned[new["line_index"]] = old["id"]
    return assigned

def sync_tasks(repo, note_id, markdown, links=None, *, baseline=False):
    # Caller owns the note/metadata/reward transaction; do not commit independently.
    parsed = parse_tasks(markdown)
    existing = repo.rows("SELECT * FROM note_tasks WHERE note_id=? ORDER BY line_index", (note_id,))
    old_by_id = {task["id"]: task for task in existing}
    if links is None: assigned = match_existing(parsed, existing)
    else:
        expected, assigned, used = {task["line_index"] for task in parsed}, {}, set()
        if len(links) != len(parsed): raise ValueError("任务关联与正文不一致，请重新保存。")
        for link in links:
            identifier, index = link["id"], link["line_index"]
            if not re.fullmatch(r"[a-f0-9]{32}", identifier) or index not in expected or index in assigned or identifier in used: raise ValueError("任务 ID 或源行关联无效。")
            owner = repo.rows("SELECT note_id FROM note_tasks WHERE id=?", (identifier,))
            if owner and owner[0]["note_id"] != note_id: raise ValueError("任务不属于当前备忘录。")
            assigned[index] = identifier; used.add(identifier)
    stamp, retained = repo.clock().isoformat(), []
    for task in parsed:
        identifier = assigned.get(task["line_index"]) or uuid.uuid4().hex
        old = old_by_id.get(identifier)
        if old:
            repo.db.execute("UPDATE note_tasks SET line_index=?,text=?,completed=?,updated_at=? WHERE id=?", (task["line_index"], task["text"], int(task["completed"]), stamp, identifier))
        else:
            repo.db.execute("INSERT INTO note_tasks(id,note_id,line_index,text,completed,completion_rewarded,first_completed_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (identifier,note_id,task["line_index"],task["text"],int(task["completed"]),int(baseline and task["completed"]),stamp if baseline and task["completed"] else None,stamp,stamp))
        handled = bool(old["completion_rewarded"]) if old else baseline and task["completed"]
        if task["completed"] and not handled:
            repo.db.execute("INSERT OR IGNORE INTO water_transactions(id,amount,type,source_id,tree_id,created_at) VALUES(?,1,'task_completion_reward',?,NULL,?)", (uuid.uuid4().hex, identifier, stamp))
            repo.db.execute("UPDATE note_tasks SET completion_rewarded=1,first_completed_at=COALESCE(first_completed_at,?) WHERE id=?", (stamp,identifier))
        retained.append(identifier)
    removed = set(old_by_id) - set(retained)
    repo.db.executemany("DELETE FROM note_tasks WHERE id=? AND note_id=?", [(identifier,note_id) for identifier in removed])

def read_tasks(repo, note_id):
    tasks = repo.rows("""SELECT t.*,
      COALESCE((SELECT SUM(s.actual_seconds) FROM focus_sessions s WHERE s.task_id=t.id AND s.ended_at IS NOT NULL),0) focus_seconds,
      EXISTS(SELECT 1 FROM water_transactions w WHERE w.type='task_completion_reward' AND w.source_id=t.id AND w.amount>0) reward_awarded
      FROM note_tasks t WHERE t.note_id=? ORDER BY t.line_index""", (note_id,))
    for task in tasks:
        task["tags"] = json.loads(task["tags"])
        for key in ("completed","completion_rewarded","reward_awarded"): task[key] = bool(task[key])
    return tasks

def validate_metadata(tags, due_date):
    cleaned = []
    if not isinstance(tags,list) or len(tags)>12: raise ValueError("每条任务最多添加 12 个标签。")
    for tag in tags:
        if not isinstance(tag,str) or not 1<=len(tag.strip())<=30: raise ValueError("标签应为 1—30 个字符。")
        if tag.strip() not in cleaned: cleaned.append(tag.strip())
    if due_date:
        if not isinstance(due_date,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",due_date): raise ValueError("截止日期应为 YYYY-MM-DD。")
        try: date.fromisoformat(due_date)
        except ValueError: raise ValueError("截止日期无效。") from None
    return cleaned,due_date or None

def set_task_completed(markdown, task, completed):
    parsed = next((line for line in parse_tasks(markdown) if line["line_index"]==task["line_index"]),None)
    if not parsed: raise ValueError("任务已从正文移除，请刷新备忘录。")
    lines = markdown.split("\n")
    index,offset = task["line_index"],parsed["marker_offset"]
    lines[index] = lines[index][:offset]+("x" if completed else " ")+lines[index][offset+1:]
    return "\n".join(lines)

def migrate(repo):
    exists = repo.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if exists and repo.db.execute("SELECT 1 FROM schema_migrations WHERE name=?",(MIGRATION,)).fetchone(): return
    if repo.setting("initialized",False):
        backup = repo.path.with_name(repo.path.stem+".before-learning-tasks-"+datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6]+".db")
        with closing(sqlite3.connect(backup)) as target: repo.db.backup(target)
    repo.db.executescript(SCHEMA)
    with repo.transaction():
        columns = {row["name"] for row in repo.rows("PRAGMA table_info(focus_sessions)")}
        for name in ("task_id","task_note_id","task_text","task_decision"):
            if name not in columns: repo.db.execute(f"ALTER TABLE focus_sessions ADD COLUMN {name} TEXT")
        repo.db.execute("CREATE INDEX IF NOT EXISTS focus_by_task ON focus_sessions(task_id,ended_at)")
        for note in repo.rows("SELECT id,markdown FROM notes"): sync_tasks(repo,note["id"],note["markdown"],baseline=True)
        repo.db.execute("INSERT INTO schema_migrations VALUES(?,?)",(MIGRATION,repo.clock().isoformat()))
