"""Run with the existing venv: python -m unittest discover -s tests -p test_growmate.py -v."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone, date
import io
from pathlib import Path
import sys
import tempfile
import unittest
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

from meetingbro.growmate.domain import water_reward, missing_water_days, growth_stage
from meetingbro.growmate.repository import Repository
from meetingbro.growmate.ai import SecretStore
from meetingbro.growmate.transcript import safe_filename, saved_segments
from meetingbro.growmate.voice import VoiceController
from meetingbro.growmate.web import create_app
from fastapi.testclient import TestClient


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 10, 2, 9, tzinfo=timezone(timedelta(hours=8)))
        self.repo = Repository(Path(self.temp.name) / "growmate.db", clock=lambda: self.now)

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def test_rewards_and_idempotency(self):
        self.assertEqual([water_reward(m * 60) for m in (1, 9, 10, 25, 45, 60, 90)], [0, 0, 2, 6, 12, 18, 30])
        self.repo.start_focus("normal", 25, 5, 1)
        self.now += timedelta(minutes=25)
        for _ in range(4): self.repo.state()
        self.assertEqual(self.repo.balance(), 6)
        self.assertEqual(self.repo.rows("SELECT COUNT(*) n FROM water_transactions")[0]["n"], 1)
        self.assertEqual(self.repo.state()["trees"][0]["growth"], 0, "Rewards must not water automatically")

    def test_strict_interrupt_once_and_no_reward(self):
        self.repo.start_focus("strict", 25, 5, 1)
        self.now += timedelta(seconds=10)
        self.repo.interrupt_focus()
        self.repo.interrupt_focus()
        self.assertEqual(self.repo.state()["trees"][0]["health"], 2)
        self.assertEqual(self.repo.balance(), 0)

    def test_strict_heartbeat_timeout(self):
        self.repo.start_focus("strict", 1, 5, 1)
        self.now += timedelta(seconds=21)
        self.assertIsNone(self.repo.state()["timer"])
        self.assertEqual(self.repo.state()["trees"][0]["health"], 2)

    def test_missing_days_once_and_mature_survives(self):
        self.assertEqual(missing_water_days("2026-09-27", None, date(2026, 9, 29)), ["2026-09-28"])
        self.now += timedelta(days=2)
        self.assertEqual(self.repo.state()["trees"][0]["health"], 2)
        self.assertEqual(self.repo.state()["trees"][0]["health"], 2)
        with self.repo.transaction():
            self.repo.db.execute("UPDATE trees SET status='mature',growth=500")
        self.now += timedelta(days=100)
        self.assertEqual(self.repo.state()["trees"][0]["health"], 2)

    def test_water_atomic_balance_and_single_tree(self):
        with self.repo.transaction():
            self.repo.db.execute("INSERT INTO water_transactions VALUES('credit',500,'fixture',NULL,NULL,?)", (self.now.isoformat(),))
        with self.assertRaises(ValueError): self.repo.plant("apple")
        self.repo.water(500)
        self.assertEqual(self.repo.balance(), 0)
        self.assertEqual(self.repo.state()["trees"][0]["status"], "mature")
        self.repo.plant("apple")
        with self.assertRaises(ValueError): self.repo.water(1)
        self.assertEqual(self.repo.balance(), 0)
        self.assertEqual(self.repo.rows("SELECT SUM(total_water) w FROM trees")[0]["w"], 500)

    def test_unlocks_and_pomodoro_rounds(self):
        for _ in range(3):
            self.repo.start_focus("normal", 60, 5, 1)
            self.now += timedelta(hours=1)
            self.repo.state()
            self.now += timedelta(days=1)
        self.assertTrue(self.repo.unlocked_species()["cherry"])
        self.assertTrue(self.repo.unlocked_species()["orange"])
        self.repo.start_focus("pomodoro", 10, 1, 2)
        self.now += timedelta(minutes=10)
        self.assertEqual(self.repo.state()["timer"]["phase"], "rest")
        self.now += timedelta(minutes=1)
        self.assertEqual(self.repo.state()["timer"]["cycle"], 2)
        self.now += timedelta(minutes=10)
        self.assertIsNone(self.repo.state()["timer"])
        self.assertEqual(self.repo.balance(), 58)

    def test_safe_filenames_and_stages(self):
        self.assertNotIn("/", safe_filename("网课/第五课:TCP?"))
        self.assertTrue(safe_filename("CON").startswith("课程_"))
        self.assertEqual(growth_stage(500), "结果")

    def test_reminder_only_once_per_day(self):
        self.repo.save_reminder({"title": "验证提醒", "hour": 9, "minute": 0})
        self.assertEqual(len(self.repo.due_reminders()), 1)
        self.assertEqual(self.repo.due_reminders(), [])
        self.now += timedelta(days=1)
        self.assertEqual(len(self.repo.due_reminders()), 1)


class FakeProvider:
    def __init__(self, secrets): self.requests = []
    async def chat(self, messages, model):
        self.requests.append(messages)
        return "我在听，你可以慢慢说。"


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.app = create_app(self.directory, enable_notifications=False, provider_factory=FakeProvider)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = {"X-GrowMate-Request": "1"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_local_access_and_private_key(self):
        self.assertEqual(self.client.post("/api/tree/water", json={"amount": 1}).status_code, 403)
        self.assertEqual(self.client.post("/api/focus/start", json={"mode": "normal"}, headers={**self.headers, "Origin": "https://evil.example"}).status_code, 403)
        result = self.client.put("/api/ai/settings", json={"key": "fake-secret-key", "remember": False}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("fake-secret-key", self.client.get("/api/state").text)
        self.assertNotIn(b"fake-secret-key", (self.directory / "growmate.db").read_bytes())

    def test_notes_health_mood_and_backup(self):
        response = self.client.post("/api/notes", json={"title": "学习笔记", "markdown": "# 标题\n\n- [ ] 任务"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        identifier = response.json()["id"]
        self.assertEqual(self.client.post("/api/health-log", json={"breakfast": "粥"}, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post("/api/mood", json={"mood": "good", "content": "今天完成了任务"}, headers=self.headers).status_code, 200)
        note_zip = zipfile.ZipFile(io.BytesIO(self.client.get(f"/api/notes/{identifier}/download").content))
        self.assertIn("学习笔记.md", note_zip.namelist())
        backup = zipfile.ZipFile(io.BytesIO(self.client.get("/api/backup").content))
        self.assertIn("growmate.db", backup.namelist())
        self.assertNotIn("groq.key", backup.namelist())

    def test_images_and_path_validation(self):
        identifier = self.client.post("/api/notes", json={"title": "图片笔记"}, headers=self.headers).json()["id"]
        self.assertEqual(self.client.post(f"/api/notes/{identifier}/images", content=b"<svg>bad</svg>", headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get("/api/images/groq.key").status_code, 404)

    def test_ai_context_opt_in_and_history(self):
        self.client.post("/api/health-log", json={"breakfast": "ONLY_WITH_CONSENT"}, headers=self.headers)
        first = self.client.post("/api/ai/chat", json={"content": "你好"}, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        request = self.app.state.provider.requests[-1]
        self.assertNotIn("ONLY_WITH_CONSENT", str(request))
        second = self.client.post("/api/ai/chat", json={"content": "今天吃什么", "conversation_id": first.json()["conversation_id"], "include_today_health": True}, headers=self.headers)
        self.assertEqual(second.status_code, 200)
        self.assertIn("ONLY_WITH_CONSENT", str(self.app.state.provider.requests[-1]))
        self.assertEqual(len(self.client.get(f"/api/ai/conversations/{first.json()['conversation_id']}").json()), 4)

    def test_voice_socket_snapshot_and_internal_options_rejected(self):
        with self.client.websocket_connect("/api/voice/socket") as ws:
            payload = ws.receive_json()
            self.assertTrue(payload["payload"]["resources_released"])
        result = self.client.post("/api/voice/start", json={"_test_asr": True}, headers=self.headers)
        self.assertEqual(result.status_code, 422)

    def test_windows_encrypted_key_roundtrip(self):
        import os
        if os.name != "nt": self.skipTest("Windows DPAPI only")
        path = self.directory / "groq.key"
        first = SecretStore(path)
        first.set("fake-dpapi-secret", True)
        self.assertNotIn(b"fake-dpapi-secret", path.read_bytes())
        self.assertEqual(SecretStore(path).key, "fake-dpapi-secret")
        first.set("", False)
        self.assertFalse(path.exists())

    def test_voice_reconnect_keeps_recording(self):
        fixture = self.directory / "test.wav"
        with wave.open(str(fixture), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b"\x10\x20" * 160_000)
        controller = self.app.state.voice
        result = self.client.portal.call(controller.start, {"title": "刷新恢复验证", "source": "mic", "model": "small", "language": "zh", "_test_asr": True, "_fixture_path": str(fixture), "_fixture_realtime": True})
        identifier = result["session"]["id"]
        with self.client.websocket_connect("/api/voice/socket") as ws:
            self.assertEqual(ws.receive_json()["payload"]["session"]["id"], identifier)
        self.assertTrue(controller.active(), "Disconnecting a page must not stop recording")
        with self.client.websocket_connect("/api/voice/socket") as ws:
            self.assertEqual(ws.receive_json()["payload"]["session"]["id"], identifier)
        self.assertEqual(self.client.post("/api/voice/stop", json={}, headers=self.headers).status_code, 200)
        self.client.portal.call(controller.close)
        self.assertFalse(controller.active())


class VoiceProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_transcript_and_process_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture = folder / "fixture.wav"
            import math, struct
            with wave.open(str(fixture), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(i * 2 * math.pi * 440 / 16000))) for i in range(192_000)))  # 十二秒覆盖完整窗口与结束尾音。
            app_data = folder / "data"
            repo = Repository(app_data / "growmate.db")
            controller = VoiceController(repo, app_data)
            try:
                await controller.start({"title": "测试/课程", "source": "mic", "model": "small", "language": "zh", "_test_asr": True, "_fixture_path": str(fixture)})
                await asyncio.wait_for(controller.task, timeout=90)
                snapshot = controller.snapshot()["payload"]
                self.assertTrue(snapshot["resources_released"])
                self.assertEqual(controller.process.exitcode, 0)
                self.assertEqual(snapshot["phase"], "ended", snapshot)
                self.assertTrue(snapshot["segments"], snapshot)
                self.assertGreaterEqual(len(snapshot["segments"]), 2)
                self.assertGreaterEqual(snapshot["segments"][-1]["end_time"], 12)  # 不能只保存前十秒而遗漏最后两秒。
                self.assertTrue(Path(snapshot["session"]["export_path"]).exists())
                self.assertIn("课堂逐字稿", Path(snapshot["session"]["export_path"]).read_text(encoding="utf8"))
                self.assertFalse(list(app_data.rglob("*.wav")))
                with closing(__import__("sqlite3").connect(controller.transcript_db)) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM summary_snapshots").fetchone()[0], 0)
            finally:
                await controller.close()
                repo.close()


    async def test_funasr_system_audio_fixture_exports_real_model_name(self):
        fixture = ROOT / "data" / "benchmark" / "coverage_zh.wav"
        with tempfile.TemporaryDirectory() as temporary_folder:
            app_data = Path(temporary_folder) / "data"
            repo = Repository(app_data / "growmate.db")
            controller = VoiceController(repo, app_data)
            try:
                await controller.start({"title": "系统声测试", "source": "system", "model": "funasr-nano-gguf-q8_0", "language": "zh", "_fixture_path": str(fixture)})
                await asyncio.wait_for(controller.task, timeout=180)
                snapshot = controller.snapshot()["payload"]
                self.assertEqual(snapshot["phase"], "ended", snapshot)
                self.assertTrue(snapshot["segments"])
                exported = Path(snapshot["session"]["export_path"])
                self.assertIn("Fun-ASR-Nano GGUF Q8_0 / CPU", exported.read_text(encoding="utf-8"))
                self.assertFalse(list(app_data.rglob("*.wav")))
            finally:
                await controller.close()
                repo.close()

    async def test_forced_exit_recovers_committed_text(self):
        fixture = ROOT / "data" / "benchmark" / "coverage_zh.wav"
        with tempfile.TemporaryDirectory() as temporary_folder:
            app_data = Path(temporary_folder) / "data"
            repo = Repository(app_data / "growmate.db")
            controller = VoiceController(repo, app_data)
            try:
                await controller.start({"title": "强退恢复测试", "source": "system", "model": "funasr-nano-gguf-q8_0", "language": "zh", "_test_asr": True, "_fixture_path": str(fixture), "_fixture_realtime": True})
                for _ in range(200):
                    if controller.segments:
                        break
                    await asyncio.sleep(0.1)
                self.assertTrue(controller.segments)
                session_id = controller.current_id
                controller.process.kill()
                await asyncio.wait_for(controller.task, timeout=30)
                row = repo.rows("SELECT * FROM voice_sessions WHERE id=?", (session_id,))[0]
                self.assertEqual(row["status"], "interrupted")
                self.assertTrue(saved_segments(controller.transcript_db, row["meeting_id"]))
            finally:
                await controller.close()
                repo.close()


if __name__ == "__main__":
    unittest.main()
