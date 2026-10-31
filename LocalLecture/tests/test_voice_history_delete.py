"""Deleting one finished lesson must preserve other lessons and reject active work."""

from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from meetingbro.growmate.repository import Repository
from meetingbro.growmate.voice import VoiceController
from meetingbro.storage.db import Storage


class VoiceHistoryDeleteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.repo = Repository(self.root / "growmate.db")
        storage = Storage(self.root / "transcripts.db")
        storage.close()
        self.export_root = self.root / "transcripts"
        self.export_root.mkdir()
        with self.repo.transaction():
            for identifier in ("remove", "keep"):
                self.repo.db.execute(
                    "INSERT INTO voice_sessions(id,title,source,model,language,started_at,status,meeting_id,export_path) VALUES(?,?,?,?,?,?,?,?,?)",
                    (identifier, identifier, "system", "small", "zh", "2026-10-31T10:00:00+08:00", "ended", identifier, str(self.export_root / f"{identifier}_{identifier[:8]}.md")),
                )
                (self.export_root / f"{identifier}_{identifier[:8]}.md").write_text(identifier, encoding="utf-8")
        with closing(sqlite3.connect(self.root / "transcripts.db")) as connection, connection:
            for identifier in ("remove", "keep"):
                connection.execute("INSERT INTO meetings(id,started_at) VALUES(?,?)", (identifier, "2026-10-31T10:00:00+08:00"))
                connection.execute("INSERT INTO transcript_segments(id,meeting_id,start_time,end_time,text,original_language,confidence,created_at) VALUES(?,?,?,?,?,?,?,?)", (identifier, identifier, 0, 1, identifier, "zh", 0.9, "2026-10-31T10:00:01+08:00"))
        self.controller = VoiceController(self.repo, self.root)

    def tearDown(self):
        self.repo.close()
        self.folder.cleanup()

    def test_deletes_only_selected_finished_lesson(self):
        self.controller.current_id = "remove"
        self.controller.segments = {"remove": {"id": "remove", "start_time": 0}}
        self.controller.delete_history("remove")
        self.assertEqual([row["id"] for row in self.repo.rows("SELECT id FROM voice_sessions")], ["keep"])
        with closing(sqlite3.connect(self.root / "transcripts.db")) as connection:
            self.assertEqual(connection.execute("SELECT meeting_id FROM transcript_segments").fetchall(), [("keep",)])
        self.assertFalse((self.export_root / "remove_remove.md").exists())
        self.assertTrue((self.export_root / "keep_keep.md").exists())
        self.assertIsNone(self.controller.current_id)
        self.assertEqual(self.controller.segments, {})

    def test_rejects_active_lesson(self):
        self.controller.current_id = "remove"
        self.controller.process = Mock()
        self.controller.process.is_alive.return_value = True
        with self.assertRaisesRegex(ValueError, "不能删除"):
            self.controller.delete_history("remove")
        self.assertTrue((self.export_root / "remove_remove.md").exists())

    def test_database_error_restores_markdown(self):
        with closing(sqlite3.connect(self.root / "transcripts.db")) as connection, connection:
            connection.execute("DROP TABLE transcript_segments")
        with self.assertRaises(sqlite3.OperationalError):
            self.controller.delete_history("remove")
        self.assertTrue((self.export_root / "remove_remove.md").exists())
        self.assertFalse((self.export_root / "remove_remove.md.pending-delete").exists())
        self.assertEqual(len(self.repo.rows("SELECT id FROM voice_sessions WHERE id='remove'")), 1)

    def test_rejects_export_path_outside_transcript_directory(self):
        outside = self.root / "outside.md"
        outside.write_text("保留", encoding="utf-8")
        with self.repo.transaction():
            self.repo.db.execute("UPDATE voice_sessions SET export_path=? WHERE id='remove'", (str(outside),))
        with self.assertRaisesRegex(ValueError, "不在课程目录"):
            self.controller.delete_history("remove")
        self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
