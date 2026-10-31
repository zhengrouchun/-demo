"""离线课堂基准必须完整保留长音频。"""
import math  # 计算 WAV 将生成的半秒块数。
from pathlib import Path  # 定位待测脚本。
import sys  # 将脚本目录加入模块搜索路径。
import tempfile  # 为测试 WAV 建立隔离目录。
import unittest  # 使用项目现有测试框架。
import wave  # 写入低采样率、长时长的小体积 WAV。

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))  # 导入实际基准脚本。
from verify_speech_coverage_accuracy import offline_benchmark_time_limits, offline_queue_capacity_seconds  # 检查两项基准保护。


class OfflineQueueCapacityTests(unittest.TestCase):
    def test_just_over_ten_minutes_still_fits_every_audio_chunk(self):
        with tempfile.TemporaryDirectory() as folder:
            wav_path = Path(folder) / "long_sample.wav"  # 样本长度略大于生产队列的十分钟上限。
            with wave.open(str(wav_path), "wb") as recording:
                recording.setnchannels(1)  # 仅需模拟单声道输入。
                recording.setsampwidth(2)  # 使用 16 位 PCM。
                recording.setframerate(10)  # 低采样率可用小文件表达十分钟。
                recording.writeframes(b"\0\0" * 6001)  # 表达 600.1 秒。
            capacity_seconds = offline_queue_capacity_seconds(wav_path, chunk_seconds=0.5)
        required_chunks = math.ceil(600.1 / 0.5)  # 包括最后一个不足半秒的音频块。
        self.assertGreaterEqual(int(capacity_seconds / 0.5), required_chunks + 1)

    def test_long_recording_uses_bounded_timeout_after_speed_target(self):
        speed_target_seconds, timeout_seconds = offline_benchmark_time_limits(600.1)
        self.assertGreater(speed_target_seconds, 600.1)  # 长课允许十分钟排队收尾的等比余量。
        self.assertGreater(timeout_seconds, speed_target_seconds)  # 超速失败先记录，随后才超时。
        self.assertLessEqual(timeout_seconds, 80 * 60)  # 异常卡住仍有明确封顶时间。


if __name__ == "__main__":
    unittest.main()  # 允许单独运行此测试文件。
