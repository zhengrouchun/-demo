from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3
import threading
import uuid

from .domain import SPECIES, growth_stage, has_three_day_streak, missing_water_days, water_reward
from .task_support import migrate as migrate_tasks, sync_tasks, read_tasks, validate_metadata, set_task_completed


def now_local() -> datetime:
    return datetime.now().astimezone()


def new_id() -> str:
    return uuid.uuid4().hex


SCHEMA = """
CREATE TABLE IF NOT EXISTS trees(id TEXT PRIMARY KEY,species_id TEXT,status TEXT,growth INTEGER,health INTEGER,planted_at TEXT,last_watered_at TEXT,last_health_penalty_date TEXT,matured_at TEXT,died_at TEXT,total_water INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS one_growing_tree ON trees(status) WHERE status='growing';
CREATE TABLE IF NOT EXISTS focus_sessions(id TEXT PRIMARY KEY,mode TEXT,started_at TEXT,ended_at TEXT,planned_seconds INTEGER,actual_seconds INTEGER DEFAULT 0,completed INTEGER DEFAULT 0,interrupted INTEGER DEFAULT 0,water_earned INTEGER DEFAULT 0,tree_id TEXT,cycle INTEGER);
CREATE TABLE IF NOT EXISTS water_transactions(id TEXT PRIMARY KEY,amount INTEGER,type TEXT,source_id TEXT,tree_id TEXT,created_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_focus_reward ON water_transactions(source_id) WHERE type='focus_reward';
CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,title TEXT,markdown TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS note_images(id TEXT PRIMARY KEY,note_id TEXT,uri TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS daily_health_logs(date TEXT PRIMARY KEY,breakfast TEXT DEFAULT '',lunch TEXT DEFAULT '',dinner TEXT DEFAULT '',snacks TEXT DEFAULT '',stomach_note TEXT DEFAULT '',general_note TEXT DEFAULT '',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS mood_logs(id TEXT PRIMARY KEY,date TEXT,mood TEXT,content TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,title TEXT,body TEXT,hour INTEGER,minute INTEGER,enabled INTEGER DEFAULT 1,last_notified_date TEXT);
CREATE TABLE IF NOT EXISTS ai_conversations(id TEXT PRIMARY KEY,title TEXT,mode TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS ai_messages(id TEXT PRIMARY KEY,conversation_id TEXT,role TEXT,content TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS ai_memories(id TEXT PRIMARY KEY,content TEXT,created_at TEXT,enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS voice_sessions(id TEXT PRIMARY KEY,title TEXT,source TEXT,model TEXT,language TEXT,started_at TEXT,ended_at TEXT,meeting_id TEXT,status TEXT,elapsed_seconds REAL DEFAULT 0,export_path TEXT,error TEXT);
"""


class Repository:
    def __init__(self, path: Path, clock=now_local):
        self.path = path
        self.clock = clock
        self.lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(SCHEMA)
        self.db.commit()
        migrate_tasks(self)
        with self.transaction():
            if not self.setting("initialized", False):
                self._plant("apple")
                for title, hour, minute in [("早餐提醒", 8, 0), ("午餐提醒", 12, 0), ("专注与浇树", 20, 0), ("记录今天的心情", 23, 0)]:
                    self.db.execute("INSERT INTO reminders VALUES(?,?,?,?,?,1,NULL)", (new_id(), title, "小狗在等你一起照顾自己。", hour, minute))
                self.set_setting("initialized", True)

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                yield
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def close(self):
        self.db.close()

    def rows(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO app_settings VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def balance(self):
        return self.db.execute("SELECT COALESCE(SUM(amount),0) FROM water_transactions").fetchone()[0]

    def _plant(self, species):
        stamp = self.clock().isoformat()
        self.db.execute("INSERT INTO trees VALUES(?,?,'growing',0,3,?,NULL,NULL,NULL,NULL,0)", (new_id(), species, stamp))

    def unlocked_species(self):
        sessions = self.rows("SELECT started_at,planned_seconds FROM focus_sessions WHERE completed=1")
        days = {datetime.fromisoformat(s["started_at"]).astimezone().date().isoformat() for s in sessions}
        return {"apple": True, "cherry": has_three_day_streak(days), "orange": any(s["planned_seconds"] >= 3600 for s in sessions)}

    def apply_health(self):
        today = self.clock().date()
        for tree in self.rows("SELECT * FROM trees WHERE status='growing'"):
            days = missing_water_days(tree["last_watered_at"] or tree["planted_at"], tree["last_health_penalty_date"], today)
            if days:
                hp = max(0, tree["health"] - len(days))
                self.db.execute("UPDATE trees SET health=?,last_health_penalty_date=?,status=?,died_at=? WHERE id=?", (hp, days[-1], "growing" if hp else "dead", None if hp else self.clock().isoformat(), tree["id"]))

    def plant(self, species):
        with self.transaction():
            self.apply_health()
            if not self.unlocked_species().get(species):
                raise ValueError("这个树种还没有解锁。")
            if self.rows("SELECT id FROM trees WHERE status='growing'"):
                raise ValueError("先把当前的小树培养成熟，才能种下一棵。")
            self._plant(species)

    def water(self, amount):
        with self.transaction():
            self.apply_health()
            if type(amount) is not int or amount < 1 or amount > 500:
                raise ValueError("浇水量应是 1 到 500 之间的整数。")
            trees = self.rows("SELECT * FROM trees WHERE status='growing'")
            if not trees:
                raise ValueError("先种下一棵小树。枯树与成熟树不需要浇水。")
            tree = trees[0]
            amount = min(amount, 500 - tree["growth"])
            if self.balance() < amount:
                raise ValueError("水滴还不够，完成专注可以获得水滴。")
            growth = tree["growth"] + amount
            stamp = self.clock().isoformat()
            self.db.execute("INSERT INTO water_transactions VALUES(?,?,'watering',NULL,?,?)", (new_id(), -amount, tree["id"], stamp))
            self.db.execute("UPDATE trees SET growth=?,total_water=total_water+?,last_watered_at=?,status=?,matured_at=? WHERE id=?", (growth, amount, stamp, "mature" if growth >= 500 else "growing", stamp if growth >= 500 else None, tree["id"]))

    def start_focus(self, mode, minutes, rest, cycles, task_id=None):
        if mode not in {"normal", "pomodoro", "strict"} or not (1 <= minutes <= 180) or not (1 <= rest <= 60) or not (1 <= cycles <= 12):
            raise ValueError("请检查专注时间（1—180 分钟）、休息时间（1—60 分钟）和轮数（1—12）。")
        with self.transaction():
            self.settle_focus()
            if self.setting("timer"):
                raise ValueError("已有专注任务，请先结束。")
            task = None
            if task_id:
                rows = self.rows("SELECT id,note_id,text FROM note_tasks WHERE id=?", (task_id,))
                if not rows: raise ValueError("专注任务已被移除，请刷新备忘录后重试。")
                task = rows[0]
            tree = self.rows("SELECT id FROM trees WHERE status='growing'")
            stamp = self.clock()
            timer = {"mode": mode, "minutes": minutes, "rest": rest, "cycles": cycles if mode == "pomodoro" else 1, "cycle": 1, "phase": "focus", "deadline": (stamp + timedelta(minutes=minutes)).isoformat(), "last_heartbeat": stamp.isoformat(), "tree_id": tree[0]["id"] if tree else None}
            timer.update(task_id=task["id"] if task else None, task_note_id=task["note_id"] if task else None, task_text=task["text"] if task else None)
            self._new_focus_round(timer, stamp)
            self.set_setting("timer", timer)

    def _new_focus_round(self, timer, stamp):
        timer["session_id"] = new_id()
        self.db.execute("INSERT INTO focus_sessions(id,mode,started_at,planned_seconds,tree_id,cycle,task_id,task_note_id,task_text) VALUES(?,?,?,?,?,?,?,?,?)", (timer["session_id"], timer["mode"], stamp.isoformat(), timer["minutes"] * 60, timer["tree_id"], timer["cycle"], timer.get("task_id"), timer.get("task_note_id"), timer.get("task_text")))

    def settle_focus(self):
        timer = self.setting("timer")
        if not timer:
            return
        now = self.clock()
        if timer["mode"] == "strict" and (now - datetime.fromisoformat(timer["last_heartbeat"])).total_seconds() > 20:
            self._interrupt(timer, "严格专注中断了，小树掉了一片叶子。")
            return
        deadline = datetime.fromisoformat(timer["deadline"])
        if now < deadline:
            return
        if timer["phase"] == "rest":
            timer["cycle"] += 1
            timer["phase"] = "focus"
            timer["deadline"] = (now + timedelta(minutes=timer["minutes"])).isoformat()
            self._new_focus_round(timer, now)
            self.set_setting("timer", timer)
            return
        row = self.rows("SELECT * FROM focus_sessions WHERE id=?", (timer["session_id"],))[0]
        if not row["ended_at"]:
            earned = water_reward(row["planned_seconds"])
            bonus = 1 if row["task_id"] and earned > 0 else 0
            self.db.execute("UPDATE focus_sessions SET ended_at=?,actual_seconds=planned_seconds,completed=1,water_earned=? WHERE id=?", (deadline.isoformat(), earned, row["id"]))
            self.db.execute("INSERT INTO water_transactions VALUES(?,?,'focus_reward',?,?,?)", (new_id(), earned, row["id"], row["tree_id"], deadline.isoformat()))
            if bonus:
                self.db.execute("INSERT OR IGNORE INTO water_transactions VALUES(?,?,'task_focus_bonus',?,?,?)", (new_id(),bonus,row["id"],row["tree_id"],deadline.isoformat()))
                self.db.execute("UPDATE focus_sessions SET water_earned=? WHERE id=?", (earned+bonus,row["id"]))
            self.set_setting("focus_result", {"id": row["id"], "message": f"完成 {timer['minutes']} 分钟专注，获得 {earned+bonus} 滴水。" + ("含任务专注额外 1 滴。" if bonus else ""), "earned": earned+bonus, "minutes": timer["minutes"], "task_id": row["task_id"], "task_note_id": row["task_note_id"], "task_text": row["task_text"], "task_decision": None})
        if timer["cycle"] < timer["cycles"]:
            timer["phase"] = "rest"
            timer["deadline"] = (now + timedelta(minutes=timer["rest"])).isoformat()
            self.set_setting("timer", timer)
        else:
            self.set_setting("timer", None)

    def _interrupt(self, timer, message):
        if timer["phase"] == "focus":
            row = self.rows("SELECT * FROM focus_sessions WHERE id=?", (timer["session_id"],))[0]
            if not row["ended_at"]:
                actual = min(row["planned_seconds"], max(0, int((self.clock() - datetime.fromisoformat(row["started_at"])).total_seconds())))
                strict = timer["mode"] == "strict"
                self.db.execute("UPDATE focus_sessions SET ended_at=?,actual_seconds=?,interrupted=? WHERE id=?", (self.clock().isoformat(), actual, int(strict), row["id"]))
                if strict and timer["tree_id"]:
                    self.db.execute("UPDATE trees SET health=MAX(0,health-1) WHERE id=? AND status='growing'", (timer["tree_id"],))
                    self.db.execute("UPDATE trees SET status='dead',died_at=? WHERE id=? AND health=0 AND status='growing'", (self.clock().isoformat(), timer["tree_id"]))
        self.set_setting("timer", None)
        self.set_setting("focus_result", {"id": new_id(), "message": message, "earned": 0})

    def interrupt_focus(self):
        with self.transaction():
            self.settle_focus()
            timer = self.setting("timer")
            if timer:
                self._interrupt(timer, "本次专注已结束，没有获得水滴。" if timer["mode"] != "strict" else "严格专注中断了，小树生命值减一。")

    def heartbeat(self):
        with self.transaction():
            self.settle_focus()
            timer = self.setting("timer")
            if timer:
                timer["last_heartbeat"] = self.clock().isoformat()
                self.set_setting("timer", timer)

    def state(self):
        with self.transaction():
            self.settle_focus()
            self.apply_health()
            trees = self.rows("SELECT * FROM trees ORDER BY planted_at DESC")
            for tree in trees:
                tree["stage"] = growth_stage(tree["growth"])
                tree["focus_count"] = self.rows("SELECT COUNT(*) n FROM focus_sessions WHERE tree_id=? AND completed=1", (tree["id"],))[0]["n"]
            unlocked = self.unlocked_species()
            today = self.clock().date().isoformat()
            focus = self.rows("SELECT * FROM focus_sessions ORDER BY started_at DESC LIMIT 100")
            today_seconds = self.rows("SELECT COALESCE(SUM(actual_seconds),0) total FROM focus_sessions WHERE completed=1 AND substr(started_at,1,10)=?", (today,))[0]["total"]
            return {"today": today, "water_balance": self.balance(), "transactions": self.rows("SELECT * FROM water_transactions ORDER BY created_at DESC LIMIT 50"), "trees": trees, "species": [dict(s, unlocked=unlocked[s["id"]]) for s in SPECIES], "focus_sessions": focus, "today_focus_seconds": today_seconds, "timer": self.setting("timer"), "focus_result": self.setting("focus_result"), "notes": [self.note(row["id"]) for row in self.rows("SELECT id FROM notes ORDER BY updated_at DESC")], "images": self.rows("SELECT * FROM note_images"), "health_logs": self.rows("SELECT * FROM daily_health_logs ORDER BY date DESC LIMIT 90"), "mood_logs": self.rows("SELECT * FROM mood_logs ORDER BY created_at DESC LIMIT 100"), "reminders": self.rows("SELECT * FROM reminders ORDER BY hour,minute"), "memories": self.rows("SELECT * FROM ai_memories ORDER BY created_at DESC"), "conversations": self.rows("SELECT * FROM ai_conversations ORDER BY updated_at DESC"), "voice_sessions": self.rows("SELECT * FROM voice_sessions ORDER BY started_at DESC LIMIT 100"), "ai_model": self.setting("ai_model", "openai/gpt-oss-20b")}

    def save_note(self, title, markdown, note_id=None, task_links=None, base_updated_at=None):
        with self.transaction():
            stamp = self.clock().isoformat()
            if note_id:
                if not self.rows("SELECT id FROM notes WHERE id=?", (note_id,)):
                    raise ValueError("备忘录不存在。")
                if base_updated_at and self.rows("SELECT updated_at FROM notes WHERE id=?", (note_id,))[0]["updated_at"] != base_updated_at:
                    raise ValueError("备忘录已在其他页面更新。草稿仍保留，请复制当前正文后重新打开这份备忘录，核对合并后再保存。")
                self.db.execute("UPDATE notes SET title=?,markdown=?,updated_at=? WHERE id=?", (title.strip() or "未命名备忘录", markdown, stamp, note_id))
            else:
                note_id = new_id()
                self.db.execute("INSERT INTO notes VALUES(?,?,?,?,?)", (note_id, title.strip() or "未命名备忘录", markdown, stamp, stamp))
            sync_tasks(self, note_id, markdown, task_links)
            return note_id

    def note(self, note_id):
        with self.lock:
            rows = self.rows("SELECT * FROM notes WHERE id=?", (note_id,))
            if not rows: raise ValueError("备忘录不存在。")
            return dict(rows[0], tasks=read_tasks(self, note_id))

    def update_task(self, note_id, task_id, tags, due_date):
        tags, due_date = validate_metadata(tags, due_date)
        with self.transaction():
            if not self.rows("SELECT id FROM note_tasks WHERE id=? AND note_id=?", (task_id,note_id)):
                raise ValueError("任务已移除或不属于这份备忘录，请刷新后重试。")
            stamp = self.clock().isoformat()
            self.db.execute("UPDATE note_tasks SET tags=?,due_date=?,updated_at=? WHERE id=?", (json.dumps(tags,ensure_ascii=False),due_date,stamp,task_id))
            self.db.execute("UPDATE notes SET updated_at=? WHERE id=?", (stamp,note_id))
            return self.note(note_id)

    def decide_focus_task(self, session_id, completed):
        with self.transaction():
            rows = self.rows("SELECT * FROM focus_sessions WHERE id=?", (session_id,))
            if not rows or not rows[0]["completed"] or not rows[0]["task_id"]:
                raise ValueError("这次专注尚未完成或没有绑定学习任务。")
            session = rows[0]
            if session["task_decision"]: return {"ok": True, "decision": session["task_decision"]}
            if completed:
                tasks = self.rows("SELECT * FROM note_tasks WHERE id=? AND note_id=?", (session["task_id"],session["task_note_id"]))
                if not tasks: raise ValueError("任务已被移除，专注记录仍保留；可选择继续保持未完成。")
                note = self.note(session["task_note_id"])
                markdown = set_task_completed(note["markdown"],tasks[0],True)
                self.db.execute("UPDATE notes SET markdown=?,updated_at=? WHERE id=?", (markdown,self.clock().isoformat(),note["id"]))
                sync_tasks(self,note["id"],markdown,[{"id":t["id"],"line_index":t["line_index"]} for t in note["tasks"]])
            decision = "complete" if completed else "keep"
            self.db.execute("UPDATE focus_sessions SET task_decision=? WHERE id=?", (decision,session_id))
            result = self.setting("focus_result")
            if result and result["id"] == session_id:
                result["task_decision"] = decision; self.set_setting("focus_result",result)
            return {"ok": True, "decision": decision}

    def save_health(self, data):
        with self.transaction():
            stamp = self.clock().isoformat()
            day = data.get("date") or self.clock().date().isoformat()
            datetime.strptime(day, "%Y-%m-%d")
            fields = ("breakfast", "lunch", "dinner", "snacks", "stomach_note", "general_note")
            self.db.execute("INSERT INTO daily_health_logs VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET breakfast=excluded.breakfast,lunch=excluded.lunch,dinner=excluded.dinner,snacks=excluded.snacks,stomach_note=excluded.stomach_note,general_note=excluded.general_note,updated_at=excluded.updated_at", (day, *(str(data.get(f, "")) for f in fields), stamp, stamp))

    def save_mood(self, mood, content):
        if mood not in {"happy", "good", "normal", "sad", "tired", "angry"}:
            raise ValueError("请选择心情。")
        with self.transaction():
            self.db.execute("INSERT INTO mood_logs VALUES(?,?,?,?,?)", (new_id(), self.clock().date().isoformat(), mood, content, self.clock().isoformat()))

    def save_reminder(self, data):
        with self.transaction():
            if not (0 <= data["hour"] <= 23 and 0 <= data["minute"] <= 59):
                raise ValueError("提醒时间无效。")
            self.db.execute("INSERT INTO reminders VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,hour=excluded.hour,minute=excluded.minute,enabled=excluded.enabled,last_notified_date=NULL", (data.get("id") or new_id(), data["title"], data.get("body", ""), data["hour"], data["minute"], int(data.get("enabled", True))))

    def due_reminders(self):
        with self.transaction():
            now = self.clock()
            day = now.date().isoformat()
            rows = self.rows("SELECT * FROM reminders WHERE enabled=1 AND hour=? AND minute=? AND (last_notified_date IS NULL OR last_notified_date<>?)", (now.hour, now.minute, day))
            for row in rows:
                self.db.execute("UPDATE reminders SET last_notified_date=? WHERE id=?", (day, row["id"]))
            return rows
