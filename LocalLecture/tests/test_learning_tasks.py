"""Learning-task persistence/reward tests with temporary databases and an injected clock."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app/backend"))
from meetingbro.growmate.repository import Repository, SCHEMA
from meetingbro.growmate.task_support import parse_tasks
from meetingbro.growmate.web import create_app
from fastapi.testclient import TestClient


class LearningTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"growmate.db"
        self.now = datetime(2026,10,3,9,tzinfo=timezone(timedelta(hours=8)))
        self.repo = Repository(self.path,clock=lambda:self.now)
    def tearDown(self):
        self.repo.close(); self.temp.cleanup()
    def note(self,body="- [ ] 外部中断"): return self.repo.save_note("学习",body)
    def task(self,note): return self.repo.note(note)["tasks"][0]
    def finish(self,minutes):
        self.now += timedelta(minutes=minutes)
        return self.repo.state()

    def test_old_database_migration_baseline_backup_and_reopen(self):
        self.repo.close()
        old_path = Path(self.temp.name)/"old.db"
        with closing(sqlite3.connect(old_path)) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO app_settings VALUES('initialized','true')")
            db.execute("INSERT INTO notes VALUES('old','旧笔记','- [x] 过去已完成\n- [ ] 待学习','old-created','old-updated')")
            db.execute("INSERT INTO water_transactions VALUES('old-credit',8,'fixture',NULL,NULL,'old-time')")
            db.commit()
        self.repo = Repository(old_path,clock=lambda:self.now)
        old = self.repo.note("old")
        ids = [t["id"] for t in old["tasks"]]
        self.assertEqual(old["markdown"],"- [x] 过去已完成\n- [ ] 待学习")
        self.assertEqual(old["created_at"],"old-created")
        self.assertEqual(self.repo.balance(),8)
        self.assertEqual(len(list(old_path.parent.glob("old.before-learning-tasks-*.db"))),1)
        self.repo.save_note("旧笔记","- [ ] 过去已完成\n- [ ] 待学习","old")
        self.repo.save_note("旧笔记","- [x] 过去已完成\n- [ ] 待学习","old")
        self.assertEqual(self.repo.balance(),8)
        self.repo.close(); self.repo = Repository(old_path,clock=lambda:self.now)
        self.assertEqual([t["id"] for t in self.repo.note("old")["tasks"]],ids)
        self.assertEqual(len(list(old_path.parent.glob("old.before-learning-tasks-*.db"))),1)

    def test_duplicate_ids_rename_reorder_and_cleanup(self):
        note = self.note("- [ ] 复习\n- [ ] 复习\n\n```c\n- [ ] 示例\n```")
        first,second = self.repo.note(note)["tasks"]
        self.assertNotEqual(first["id"],second["id"])
        self.repo.update_task(note,second["id"],["STM32","Proteus"],"2026-10-07")
        self.repo.save_note("学习","- [ ] 复习\n- [ ] 复习第二部分",note,[{"id":first["id"],"line_index":0},{"id":second["id"],"line_index":1}])
        self.repo.save_note("学习","- [ ] 复习第二部分\n- [ ] 复习",note,[{"id":second["id"],"line_index":0},{"id":first["id"],"line_index":1}])
        changed = self.repo.note(note)["tasks"][0]
        self.assertEqual(changed["id"],second["id"])
        self.assertEqual(changed["tags"],["STM32","Proteus"])
        self.assertEqual(changed["due_date"],"2026-10-07")
        self.repo.save_note("学习","- [ ] 复习第二部分",note,[{"id":second["id"],"line_index":0}])
        self.assertEqual(len(self.repo.note(note)["tasks"]),1)
        self.assertFalse(self.repo.rows("SELECT id FROM note_tasks WHERE id=?",(first["id"],)))

    def test_completion_reward_once_across_undo_and_restart(self):
        note = self.note(); identifier = self.task(note)["id"]
        for _ in range(3):
            self.repo.save_note("学习","- [x] 外部中断",note)
            self.repo.save_note("学习","- [ ] 外部中断",note)
        self.assertEqual(self.repo.balance(),1)
        self.repo.close(); self.repo = Repository(self.path,clock=lambda:self.now)
        self.repo.save_note("学习","- [x] 外部中断",note)
        self.assertEqual(self.task(note)["id"],identifier)
        self.assertEqual(self.repo.balance(),1)
        self.assertEqual(len(self.repo.rows("SELECT * FROM water_transactions WHERE source_id=?",(identifier,))),1)

    def test_focus_binding_cumulative_reward_and_explicit_completion(self):
        note = self.note(); identifier = self.task(note)["id"]
        self.repo.start_focus("normal",25,5,1,identifier)
        session = self.repo.setting("timer")["session_id"]
        self.assertEqual(self.repo.setting("timer")["task_id"],identifier)
        self.finish(25)
        for _ in range(5): self.repo.state()
        self.assertEqual(self.task(note)["focus_seconds"],1500)
        self.assertFalse(self.task(note)["completed"])
        self.assertEqual(self.repo.balance(),7)
        self.repo.decide_focus_task(session,True)
        for _ in range(3): self.repo.decide_focus_task(session,True)
        self.assertEqual(self.repo.balance(),8)
        self.assertEqual(self.repo.note(note)["markdown"],"- [x] 外部中断")
        self.repo.water(1)
        self.assertEqual(self.repo.state()["trees"][0]["growth"],1)
        self.assertEqual(self.repo.balance(),7)

    def test_focus_keep_is_idempotent_and_session_rewards_are_separate(self):
        note=self.note(); identifier=self.task(note)["id"]
        for _ in range(2):
            self.repo.start_focus("normal",25,5,1,identifier)
            session=self.repo.setting("timer")["session_id"]
            self.finish(25)
            self.repo.decide_focus_task(session,False)
            self.repo.decide_focus_task(session,True)
        self.assertEqual(self.repo.balance(),14)
        self.assertFalse(self.task(note)["completed"])
        self.assertEqual(self.task(note)["focus_seconds"],3000)
        self.assertEqual(len(self.repo.rows("SELECT * FROM water_transactions WHERE type='task_focus_bonus'")),2)

    def test_short_and_interrupted_focus_no_bonus(self):
        note=self.note(); identifier=self.task(note)["id"]
        self.repo.start_focus("normal",5,1,1,identifier); self.finish(5)
        self.assertEqual(self.repo.balance(),0)
        self.repo.start_focus("normal",25,1,1,identifier)
        self.now += timedelta(minutes=2); self.repo.interrupt_focus()
        self.assertEqual(self.repo.balance(),0)
        self.assertEqual(self.task(note)["focus_seconds"],420)
        self.assertFalse(self.task(note)["completed"])

    def test_pomodoro_reuses_task_binding_and_single_reward_each_round(self):
        note=self.note(); identifier=self.task(note)["id"]
        self.repo.start_focus("pomodoro",10,1,2,identifier)
        first=self.repo.setting("timer")["session_id"]
        self.finish(10); self.finish(1)
        self.assertEqual(self.repo.setting("timer")["task_id"],identifier)
        self.assertNotEqual(self.repo.setting("timer")["session_id"],first)
        self.finish(10)
        self.assertEqual(self.repo.balance(),6)
        self.assertEqual(self.task(note)["focus_seconds"],1200)
        self.assertFalse(self.task(note)["completed"])

    def test_metadata_validation_and_failed_save_roll_back(self):
        note=self.note(); identifier=self.task(note)["id"]
        self.repo.update_task(note,identifier,["STM32","STM32"],"2026-10-07")
        self.assertEqual(self.task(note)["tags"],["STM32"])
        for tags,due in [([" "],None),(["x"]*13,None),([],"2026-02-30"),([],"2026-1-1")]:
            with self.assertRaises(ValueError): self.repo.update_task(note,identifier,tags,due)
        with self.assertRaises(ValueError): self.repo.save_note("错误","- [x] 外部中断",note,[{"id":identifier,"line_index":22}])
        self.assertEqual(self.repo.note(note)["markdown"],"- [ ] 外部中断")
        self.assertEqual(self.repo.balance(),0)
        self.assertEqual(self.task(note)["due_date"],"2026-10-07")

    def test_cross_note_ids_rejected_and_stale_save_is_preserved(self):
        note=self.note(); other=self.note("- [ ] 其他任务")
        wrong=self.task(other)["id"]
        with self.assertRaises(ValueError): self.repo.save_note("学习","- [x] 外部中断",note,[{"id":wrong,"line_index":0}])
        before=self.repo.note(note)["updated_at"]
        self.now += timedelta(seconds=1)
        self.repo.update_task(note,self.task(note)["id"],["Java"],None)
        with self.assertRaises(ValueError): self.repo.save_note("学习","- [x] 外部中断",note,base_updated_at=before)
        self.assertEqual(self.task(note)["tags"],["Java"])
        self.assertEqual(self.repo.balance(),0)

    def test_missing_task_focus_rejected_without_starting_timer(self):
        with self.assertRaises(ValueError): self.repo.start_focus("normal",25,5,1,uuid.uuid4().hex)
        self.assertIsNone(self.repo.setting("timer"))
        self.assertEqual(self.repo.balance(),0)

    def test_code_fences_and_crlf_parser(self):
        self.assertEqual([t["text"] for t in parse_tasks("# 学习\r\n  - [ ] TIM2\r\n~~~~\r\n- [ ] 示例\r\n~~~\r\n~~~~\r\n- [X] GPIO")],["TIM2","GPIO"])


class LearningTaskApiTests(unittest.TestCase):
    def test_api_metadata_and_untrusted_reward_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(Path(folder),enable_notifications=False)) as client:
                headers={"X-GrowMate-Request":"1"}
                result=client.post("/api/notes",json={"title":"学习","markdown":"- [ ] 任务"},headers=headers).json()
                note=result["note"]; task=note["tasks"][0]
                response=client.patch(f"/api/notes/{note['id']}/tasks/{task['id']}",json={"tags":["STM32"],"due_date":"2026-10-07"},headers=headers)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()["tasks"][0]["due_date"],"2026-10-07")
                self.assertEqual(client.post("/api/notes",json={"id":note["id"],"title":"学习","markdown":"- [x] 任务","water_earned":100},headers=headers).status_code,422)
                self.assertEqual(client.post("/api/focus/start",json={"task_id":task["id"],"mode":"normal","minutes":25},headers=headers).status_code,200)
                self.assertEqual(client.get("/api/state").json()["timer"]["task_id"],task["id"])
                session=client.get("/api/state").json()["timer"]["session_id"]
                self.assertEqual(client.post(f"/api/focus/{session}/task-decision",json={"completed":True},headers=headers).status_code,400)
                self.assertEqual(client.get("/api/state").json()["water_balance"],0)


if __name__=="__main__": unittest.main()
