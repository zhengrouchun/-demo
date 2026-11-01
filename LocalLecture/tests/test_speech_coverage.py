"""验证轻声、末尾缓存、识别重试及采音异常不会悄悄丢失。"""
import asyncio  # 驱动真实会话的异步消费流程。
import sys  # 让独立测试可以导入项目后端。
import tempfile  # 隔离测试数据库，避免修改用户录音。
import unittest  # 使用标准库测试运行器。
from pathlib import Path  # 构造跨平台测试路径。
from unittest.mock import MagicMock, patch  # 模拟硬件与模型，不打开真实录音设备。

import numpy as np  # 生成具有可核对顺序的测试波形。

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))  # 加载本地模块。
from meetingbro.asr.base import ASRSegment  # 构造带质量指标的模型结果。
from meetingbro.audio.capture import AudioChunk, AudioSource  # 使用真实音频接口。
from meetingbro.audio.loopback import SystemAudioLoopbackSource  # 验证系统采音失败传递。
from meetingbro.growmate.repository import Repository  # 验证警告能够持久保存。
from meetingbro.growmate.speech_coverage import session_options  # 使用生产环境同一配置。
from meetingbro.growmate.transcript import export_transcript  # 验证导出包含异常提示。
from meetingbro.growmate.voice import VoiceController  # 模拟前端收到的状态事件。
from meetingbro.session.manager import SessionConfig, SessionManager  # 运行实际转写调度。


class FixtureSource(AudioSource):
    sample_rate = 16_000  # 与生产识别模型的采样率一致。

    def __init__(self, chunks):
        self.chunks = chunks  # 保存待回放音频块及其顺序。

    async def stream(self):
        for index, samples in enumerate(self.chunks):  # 按半秒一个块模拟采音。
            yield AudioChunk(samples, self.sample_rate, index * 0.5)  # 保留原始时间轴。


class RecordingASR:
    def __init__(self):
        self.windows = []  # 记录实际进入识别器的波形。

    def transcribe(self, samples, sample_rate, **kwargs):
        self.windows.append(samples.copy())  # 复制输入，防止后续复用影响断言。
        return []  # 此测试验证音频覆盖，不用假文字冒充识别准确率。


class CoverageTests(unittest.IsolatedAsyncioTestCase):
    def make_manager(self, source, asr, **overrides):
        config = session_options()  # 默认使用正在修复的逐字稿配置。
        config.update(overrides)  # 只覆盖各测试需要控制的因素。
        summarizer = MagicMock()  # 模拟成功但内容为空的摘要服务。
        summarizer.summarize.return_value = ""  # 避免无关的摘要字段校验干扰转写测试。
        manager = SessionManager(SessionConfig(
            audio_source=source, asr=asr, storage=MagicMock(),  # 隔离存储及模型。
            summarizer=summarizer, translator=MagicMock(),  # 不访问网络服务。
            forced_language="zh", summary_language="zh", watchdog_enabled=False,
            **config,
        ))
        for executor in (manager._asr_executor, manager._summary_executor, manager._translation_executor):
            self.addCleanup(executor.shutdown, wait=True)  # 测试结束释放工作线程。
        return manager

    async def test_soft_speech_and_short_final_tail_reach_asr_once(self):
        chunks = [np.full(8_000, 0.001 + index * 0.00001, np.float32) for index in range(23)]  # 11.5 秒轻声，包括完整窗口及短尾音。
        asr = RecordingASR()  # 收集每个识别窗口的实际音频。
        manager = self.make_manager(FixtureSource(chunks), asr, audio_conditioning_enabled=False)
        manager._state.asr_safeguard_cooldown_windows = 5  # 模拟 CPU 忙，补救机制被禁用的场景。
        with patch("meetingbro.audio.vad.SileroSpeechDetector.detect", side_effect=AssertionError("不应提前裁音")):
            await manager._run()  # 自然结束也必须处理不足一个完整窗口的尾音。
        np.testing.assert_array_equal(np.concatenate(asr.windows), np.concatenate(chunks))  # 所有采样恰好一次。
        self.assertEqual(manager._state.audio_input_queue_drop_total, 0)  # 不允许丢队列音频。

    async def test_full_queue_natural_end_preserves_last_chunk(self):
        chunks = [np.full(8_000, 0.02, np.float32)]  # 一个块刚好填满容量为一的队列。
        asr = RecordingASR()  # 记录结束标记是否挤掉最后一块。
        manager = self.make_manager(FixtureSource(chunks), asr, audio_input_queue_max_seconds=0.5)
        manager._graceful_stop_requested = False  # 音源自然结束，用户没有点击停止。
        await manager._run()  # 执行生产代码中的入队和末尾排空。
        self.assertEqual(manager._state.audio_input_queue_drop_total, 0)  # 结束标记不得丢弃尾音。
        self.assertEqual(sum(len(window) for window in asr.windows), 8_000)  # 尾音完整进入模型。

    async def test_pure_silence_does_not_trigger_recognition(self):
        asr = RecordingASR()  # 记录静音是否误送入模型导致幻觉文字。
        manager = self.make_manager(FixtureSource([np.zeros(8_000, np.float32)] * 23), asr)
        await manager._run()  # 包括完整窗口及不足窗口的尾部静音。
        self.assertEqual(asr.windows, [])  # 降低轻声门槛后仍然跳过纯静音。

    async def test_retry_keeps_original_when_empty_or_worse(self):
        original = [ASRSegment(0, 1, "需要保留的一句话", "zh", 0.7, -1.0, 0.8, 1.0)]  # 两项可疑信号触发重试。
        worse = [ASRSegment(0, 1, "重复噪声", "zh", 0.1, -1.0, 0.8, 3.0)]  # 三项信号表示更差结果。
        better = [ASRSegment(0, 1, "更准确的一句话", "zh", 0.95, -0.1, 0.1, 1.0)]  # 正常结果允许替换。
        for retry_result, expected in (([], original), (worse, original), (RuntimeError("retry failed"), original), (better, better)):
            with self.subTest(retry_result=retry_result):
                asr = MagicMock()  # 依次返回首轮结果与重试结果。
                asr.transcribe.side_effect = [original, retry_result]
                manager = self.make_manager(FixtureSource([]), asr)
                with patch.object(manager, "_allow_asr_retry", return_value=(True, None)):
                    result = await manager._transcribe_window(asyncio.get_running_loop(), np.ones(16_000, np.float32), 16_000, prompt=None, forced_language="zh")
                self.assertEqual(result, expected)  # 重试不能清空或恶化首轮文字。

    async def test_uncertain_sentences_survive_disabled_retry_and_final_flush(self):
        for chunk_count in (1, 20):  # 分别覆盖不足一个窗口的尾句与普通完整窗口。
            with self.subTest(chunk_count=chunk_count):
                source = FixtureSource([np.full(8_000, 0.02, np.float32)] * chunk_count)
                asr = MagicMock()  # 模拟已经识别到文字，但质量处于需要核对的等级。
                asr.transcribe.return_value = [ASRSegment(0, 0.5, "需要核对但不能删除。", "zh", 0.7, -1.0, 0.8, 1.0)]
                manager = self.make_manager(source, asr, asr_retry_enabled=False)
                await manager._run()  # 不允许重试时也不应无声删除已经识别的句子。
                self.assertEqual([segment.text for segment in manager._state.segments], ["需要核对但不能删除。"])
                self.assertEqual(manager._state.segments[0].quality, "uncertain")  # 页面可提醒用户核对。

    async def test_joining_sentence_preserves_uncertain_quality(self):
        source = FixtureSource([np.full(8_000, 0.02, np.float32)] * 21)  # 十秒完整窗和半秒尾句。
        asr = MagicMock()  # 模拟一句话被分成两个窗口识别。
        asr.transcribe.side_effect = [
            [ASRSegment(0, 10, "如果", "zh", 0.7, -1.0, 0.8, 1.0)],  # 前半句需要核对。
            [ASRSegment(0, 0.5, "声音比较轻也要保留。", "zh", 0.95)],  # 后半句清楚。
        ]
        manager = self.make_manager(source, asr, asr_retry_enabled=False)
        await manager._run()  # 合并时不能将整句的质量重置为正常。
        self.assertEqual(manager._state.segments[0].text, "如果声音比较轻也要保留。")
        self.assertEqual(manager._state.segments[0].quality, "uncertain")

    async def test_loopback_retries_open_and_surfaces_capture_failure(self):
        source = SystemAudioLoopbackSource(chunk_seconds=0.5)  # 创建接口但不打开硬件。
        mic = MagicMock()  # 模拟第一个采样率初始化失败。
        rejected = MagicMock()  # 错误发生在进入上下文而非构造 recorder 时。
        rejected.__enter__.side_effect = RuntimeError("unsupported rate")
        accepted = MagicMock()  # 第二个采样率可以成功打开。
        accepted.__enter__.return_value = accepted
        accepted.record.side_effect = [np.ones((22_050, 2), np.float32), RuntimeError("device disconnected")]
        mic.recorder.side_effect = [rejected, accepted]
        fake_com = MagicMock()  # 不初始化真实 COM 设备。
        fake_com.CoInitializeEx.return_value = 0
        collected = []  # 检查异常之前已捕获的声音仍能读取。
        with patch.dict(sys.modules, {"soundcard": MagicMock()}), patch("ctypes.WinDLL", return_value=fake_com), patch.object(source, "_resolve_loopback_mic", return_value=mic):
            with self.assertRaisesRegex(RuntimeError, "device disconnected"):
                async for chunk in source.stream():
                    collected.append(chunk)
        self.assertEqual(len(collected), 1)  # 已采集音频不能被错误覆盖。
        self.assertEqual(len(collected[0].samples), 8_000)  # 按成功打开的 44.1kHz 重采样。
        self.assertEqual(mic.recorder.call_count, 2)  # 确实尝试了下一个采样率。
        accepted.__exit__.assert_called_once()  # 异常之后正确关闭设备。


class WarningTests(unittest.TestCase):
    def test_pending_preview_is_visible_without_being_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder) / "app.db")
            try:
                controller = VoiceController(repo, Path(folder))
                draft = {"id": "draft", "start_time": 0.0, "end_time": 30.0, "text": "待确认的课堂文字"}
                controller._event({"type": "transcript_preview", "payload": {"segment": draft}})
                snapshot = controller.snapshot()["payload"]
                self.assertEqual(snapshot["preview"], draft)
                self.assertEqual(snapshot["segments"], [])
                controller._event({"type": "transcript_preview", "payload": {"segment": None}})
                self.assertIsNone(controller.snapshot()["payload"]["preview"])
            finally:
                repo.close()

    def test_capture_warning_survives_progress_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder) / "app.db")  # 只使用临时数据库。
            self.addCleanup(repo.close)  # 异常退出测试时同样关闭连接。
            repo.db.execute("INSERT INTO voice_sessions(id,title,source,model,language,started_at,status) VALUES('test','测试','system','small','zh','2026-10-21T10:00:00+08:00','running')")
            repo.db.commit()  # 准备一条活动录音记录。
            controller = VoiceController(repo, Path(folder))  # 不启动子进程。
            controller.current_id = "test"  # 指定事件所属录音。
            controller._event({"type": "error", "payload": {"code": "audio_source_crashed", "message": "采音中断"}})
            controller._event({"type": "session_state", "payload": {"state": "running", "meeting_id": "meeting", "elapsed_seconds": 1}})
            row = repo.rows("SELECT * FROM voice_sessions WHERE id='test'")[0]  # 模拟网页刷新读取。
            self.assertIn("采音中断", row["error"])  # 状态更新不能抹掉历史警告。
            output = export_transcript(row, [], Path(folder) / "exports")  # 验证导出也带完整性提示。
            self.assertIn("采音中断", output.read_text(encoding="utf-8"))
            repo.close()  # Windows 删除临时目录前先释放数据库句柄。


if __name__ == "__main__":
    unittest.main()  # 支持直接运行这个回归文件。
