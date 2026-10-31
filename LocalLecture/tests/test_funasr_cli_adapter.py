"""Fun-ASR-Nano must return usable segments without retaining temporary audio."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from meetingbro.asr.funasr_cli_adapter import FunASRNanoAdapter


class FunASRNanoAdapterTests(unittest.TestCase):
    def test_transcribe_parses_timestamps_and_removes_temporary_wav(self):
        adapter = FunASRNanoAdapter(
            executable=Path("C:/models/llama-funasr-cli.exe"),
            encoder=Path("C:/models/encoder.gguf"),
            decoder=Path("C:/models/decoder.gguf"),
        )
        srt = "1\n00:00:00,000 --> 00:00:01,000\n你好。\n\n2\n00:00:01,000 --> 00:00:02,000\nTCP 协议。\n"
        with patch("meetingbro.asr.funasr_cli_adapter.subprocess.run") as run:
            run.return_value.stdout = srt.encode("utf-8")
            run.return_value.stderr = b"\xff"
            run.return_value.returncode = 0
            segments = adapter.transcribe(np.zeros(32000, dtype=np.float32), 16000, offset_seconds=5.0)
            temporary_wav = Path(run.call_args.args[0][-1])
        self.assertEqual([(segment.start_time, segment.end_time, segment.text) for segment in segments], [(5.0, 6.0, "你好。"), (6.0, 7.0, "TCP 协议。")])
        self.assertFalse(temporary_wav.exists())


if __name__ == "__main__":
    unittest.main()
