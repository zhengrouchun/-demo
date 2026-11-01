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

    def test_network_terms_are_corrected_only_in_clear_network_phrases(self):
        adapter = FunASRNanoAdapter(
            executable=Path("C:/models/llama-funasr-cli.exe"),
            encoder=Path("C:/models/encoder.gguf"),
            decoder=Path("C:/models/decoder.gguf"),
        )
        srt = (
            "1\n00:00:00,000 --> 00:00:10,000\n"
            "计算机B的麦克地址，修改原麦克为自己的麦克，然后从子网二的网卡发出。\n\n"
            "2\n00:00:10,000 --> 00:00:20,000\n"
            "路由器有一个万口接入互联网，多个烂口接入本地网络。\n\n"
            "3\n00:00:20,000 --> 00:00:30,000\n"
            "麦克风接入电脑，麦克住在万口村。\n"
        )
        with patch("meetingbro.asr.funasr_cli_adapter.subprocess.run") as run:
            run.return_value.stdout = srt.encode("utf-8")
            run.return_value.stderr = b""
            run.return_value.returncode = 0
            segments = adapter.transcribe(np.zeros(480000, dtype=np.float32), 16000)
        self.assertEqual(
            [segment.text for segment in segments],
            [
                "计算机B的 MAC 地址，修改原 MAC 为自己的 MAC，然后从子网二的网卡发出。",
                "路由器有一个 WAN 口接入互联网，多个 LAN 口接入本地网络。",
                "麦克风接入电脑，麦克住在万口村。",
            ],
        )

    def test_configured_window_is_forwarded_to_local_runtime(self):
        adapter = FunASRNanoAdapter(
            executable=Path("C:/models/llama-funasr-cli.exe"),
            encoder=Path("C:/models/encoder.gguf"),
            decoder=Path("C:/models/decoder.gguf"),
            chunk_seconds=30,
        )
        with patch("meetingbro.asr.funasr_cli_adapter.subprocess.run") as run:
            run.return_value.stdout = b""
            run.return_value.stderr = b""
            run.return_value.returncode = 0
            adapter.transcribe(np.zeros(16000, dtype=np.float32), 16000)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--chunk") + 1], "30")

    def test_network_acronyms_from_long_window_keep_standard_spelling(self):
        adapter = FunASRNanoAdapter(
            executable=Path("C:/models/llama-funasr-cli.exe"),
            encoder=Path("C:/models/encoder.gguf"),
            decoder=Path("C:/models/decoder.gguf"),
        )
        srt = (
            "1\n00:00:00,000 --> 00:00:10,000\n"
            "计算机 b 的 mac 地址。路由器有一个 one 口接入互联网，多个 lan 口接入本地网络。\n\n"
            "2\n00:00:10,000 --> 00:00:20,000\n"
            "one 口喝水，MacBook 放在桌上。\n"
        )
        with patch("meetingbro.asr.funasr_cli_adapter.subprocess.run") as run:
            run.return_value.stdout = srt.encode("utf-8")
            run.return_value.stderr = b""
            run.return_value.returncode = 0
            segments = adapter.transcribe(np.zeros(320000, dtype=np.float32), 16000)
        self.assertEqual(
            [segment.text for segment in segments],
            [
                "计算机 b 的 MAC 地址。路由器有一个 WAN 口接入互联网，多个 LAN 口接入本地网络。",
                "one 口喝水，MacBook 放在桌上。",
            ],
        )


if __name__ == "__main__":
    unittest.main()
