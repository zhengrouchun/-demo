"""Check the agreed classroom transcription accuracy gate on controlled text."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from score_classroom_transcription import character_error_rate, evaluate_transcripts, score_manifest


class ClassroomAccuracyTests(unittest.TestCase):
    def test_normalizes_fullwidth_case_punctuation_and_spaces(self):
        self.assertEqual(character_error_rate("ＴＣＰ 协议，ＡＢＣ。", "tcp协议abc"), 0.0)

    def test_both_sources_are_weighted_equally(self):
        result = evaluate_transcripts(
            references={"system": "甲乙", "mic": "甲乙丙丁戊己辛壬癸子"},
            transcripts={
                "whisper-small": {"system": "甲错", "mic": "甲乙丙丁戊己辛壬癸子"},
                "candidate": {"system": "甲乙", "mic": "甲乙丙丁戊己辛壬癸子"},
            },
        )
        self.assertEqual(result["baseline_mean_cer"], 0.25)
        self.assertEqual(result["engines"]["candidate"]["mean_cer"], 0.0)
        self.assertTrue(result["engines"]["candidate"]["cer_gate_passed"])

    def test_rejects_a_candidate_that_worsens_one_source(self):
        result = evaluate_transcripts(
            references={"system": "甲乙丙丁戊", "mic": "甲乙丙丁戊"},
            transcripts={
                "whisper-small": {"system": "甲错丙错戊", "mic": "甲乙丙丁戊"},
                "candidate": {"system": "甲乙丙丁戊", "mic": "甲错丙丁戊"},
            },
        )
        self.assertFalse(result["engines"]["candidate"]["cer_gate_passed"])
        self.assertEqual(result["engines"]["candidate"]["mean_cer"], 0.1)

    def test_requires_nonempty_references_for_both_sources(self):
        with self.assertRaisesRegex(ValueError, "mic"):
            evaluate_transcripts(
                references={"system": "课堂", "mic": "。"},
                transcripts={"whisper-small": {"system": "课堂", "mic": ""}},
            )

    def test_manifest_reads_relative_text_files_without_exposing_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, content in {
                "system-ref.txt": "ＴＣＰ 协议。",
                "mic-ref.txt": "语音识别",
                "system-baseline.txt": "TCP协议",
                "mic-baseline.txt": "语音识错",
                "system-candidate.txt": "TCP协议",
                "mic-candidate.txt": "语音识别",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            manifest = root / "samples.json"
            manifest.write_text(json.dumps({
                "references": {"system": "system-ref.txt", "mic": "mic-ref.txt"},
                "transcripts": {
                    "whisper-small": {"system": "system-baseline.txt", "mic": "mic-baseline.txt"},
                    "candidate": {"system": "system-candidate.txt", "mic": "mic-candidate.txt"},
                },
            }), encoding="utf-8")

            result = score_manifest(manifest)

        self.assertEqual(result["engines"]["candidate"]["mean_cer"], 0.0)
        self.assertNotIn("协议", json.dumps(result, ensure_ascii=False))

    def test_command_prints_machine_readable_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, content in {
                "reference.txt": "甲乙",
                "baseline.txt": "甲错",
                "candidate.txt": "甲乙",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            manifest = root / "samples.json"
            manifest.write_text(json.dumps({
                "references": {"system": "reference.txt", "mic": "reference.txt"},
                "transcripts": {
                    "whisper-small": {"system": "baseline.txt", "mic": "baseline.txt"},
                    "candidate": {"system": "candidate.txt", "mic": "candidate.txt"},
                },
            }), encoding="utf-8")
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "score_classroom_transcription.py"), str(manifest)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["engines"]["candidate"]["cer_gate_passed"])


if __name__ == "__main__":
    unittest.main()
