"""A short-lived process owns ALL capture, VAD, and Whisper resources."""
import asyncio
from contextlib import closing
from pathlib import Path
import queue
import sqlite3
import traceback


def run_voice_worker(options, commands, events):
    try:
        asyncio.run(_run(options, commands, events))
    except BaseException as exc:
        events.put({"type": "worker_error", "payload": {"message": str(exc), "detail": traceback.format_exc()[-3000:]}})


async def _run(options, commands, events):
    # Never move these imports to module scope: the parent stays lightweight.
    import numpy as np
    from ..asr.base import ASRAdapter, ASRSegment
    from ..asr.faster_whisper_adapter import FasterWhisperAdapter
    from ..asr.funasr_cli_adapter import FunASRNanoAdapter
    from ..audio import MicrophoneSource, MixedAudioSource, SystemAudioLoopbackSource, WavFileSource
    from ..session.manager import SessionConfig, SessionManager
    from ..storage.db import Storage
    from ..summarization.base import Summarizer
    from ..translation.base import Translator
    from .speech_coverage import model_options, session_options  # 集中使用防漏句配置。

    class DisabledSummary(Summarizer):
        def summarize(self, *args, **kwargs):
            raise RuntimeError("Transcript-only sessions must not call AI summaries")

    class DisabledTranslation(Translator):
        def translate(self, *args, **kwargs):
            raise RuntimeError("Transcript-only sessions must not call AI translation")

    class TranscriptSession(SessionManager):
        def _schedule_summary(self, coro):
            coro.close()

        async def _emit_final(self):
            return

        async def _emit_memory(self, *, force=False):
            return

    selected_model = options["model"]
    events.put({"type": "loading", "payload": {"message": f"正在加载本地 {selected_model} 模型。"}})
    if options.get("_test_asr"):
        class FixtureASR(ASRAdapter):
            def __init__(self):
                self.calls = 0

            def transcribe(self, samples, sample_rate, **kwargs):
                self.calls += 1
                return [ASRSegment(0, len(samples) / sample_rate, f"这是第{self.calls}段用于验证完整转写链路的测试文字。", "zh", .95)]
        asr = FixtureASR()
    elif selected_model == "funasr-nano-gguf-q8_0":
        model_root = Path(__file__).resolve().parents[4] / "models" / "classroom-benchmark"
        asr = FunASRNanoAdapter(
            executable=model_root / "funasr-runtime" / "llama-funasr-cli.exe",
            encoder=model_root / "funasr" / "funasr-encoder-f16.gguf",
            decoder=model_root / "funasr" / "qwen3-0.6b-q8_0.gguf",
            working_directory=model_root.parent.parent,
            chunk_seconds=30,
        )
        await asyncio.to_thread(asr.ensure_loaded)
    else:
        asr = FasterWhisperAdapter(**model_options(options["model"]))  # 限制线程争用并比较多个候选。
        await asyncio.to_thread(asr.ensure_loaded)
    try:
        early_command = commands.get_nowait()
        if early_command == "stop":
            events.put({"type": "worker_done", "payload": {"elapsed_seconds": 0}})
            return
    except queue.Empty:
        pass
    if options.get("_fixture_path"):
        source = WavFileSource(Path(options["_fixture_path"]), chunk_seconds=.5, realtime=options.get("_fixture_realtime", False))
    elif options["source"] == "system":
        source = SystemAudioLoopbackSource(chunk_seconds=.5, speaker_name=options.get("loopback_device") or None)
    elif options["source"] == "mixed":
        device = options.get("audio_device") or None
        if device is not None and str(device).isdigit():
            device = int(device)
        source = MixedAudioSource(chunk_seconds=.5, microphone_device=device, speaker_name=options.get("loopback_device") or None)
    else:
        device = options.get("audio_device") or None
        if device is not None and str(device).isdigit():
            device = int(device)
        source = MicrophoneSource(chunk_seconds=.5, device=device)
    storage = Storage(Path(options["transcript_db"]))
    coverage_options = session_options(options["language"])
    if selected_model == "funasr-nano-gguf-q8_0":
        coverage_options["asr_early_flush_enabled"] = False
        coverage_options["asr_accumulation_seconds"] = 30.0
    manager = TranscriptSession(SessionConfig(
        audio_source=source,  # 接收用户选定的麦克风或系统音频。
        audio_source_name=options["source"],  # 保存音频来源供状态显示。
        asr=asr,  # 使用本次子进程加载的识别模型。
        summarizer=DisabledSummary(),  # 逐字稿不调用摘要服务。
        translator=DisabledTranslation(),  # 逐字稿不调用翻译服务。
        storage=storage,  # 将确认的文字写入本地数据库。
        forced_language=None if options["language"] == "auto" else options["language"],  # 尊重语言选择。
        summary_language="zh",  # 保留会话所需的默认语言字段。
        language_lock_enabled=options["language"] != "auto",  # 自动模式不强制锁定语言。
        watchdog_enabled=not options.get("_fixture_path"),  # 实际录音检测卡顿，离线测试跳过。
        **coverage_options,  # 统一应用连续音频及所选语言的配置。
    ))
    with closing(sqlite3.connect(options["app_db"], timeout=10)) as conn:
        conn.execute("UPDATE voice_sessions SET meeting_id=? WHERE id=?", (manager.meeting_id, options["id"]))
        conn.commit()

    async def forward():
        async for event in manager.events():
            events.put({"type": event.type, "payload": event.payload})

    forward_task = None
    stopped = False
    try:
        await manager.start()
        events.put({"type": "worker_ready", "payload": {"meeting_id": manager.meeting_id}})
        forward_task = asyncio.create_task(forward())
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None
            if command == "stop" or (manager._task and manager._task.done()):
                events.put({"type": "draining", "payload": {"message": "正在处理剩余声音并保存逐字稿，请稍候。"}})
                await manager.stop(graceful=True)
                stopped = True
                break
            if command == "pause":
                await manager.pause()
            elif command == "resume":
                await manager.resume()
            await asyncio.sleep(.1)
        if forward_task:
            await asyncio.wait_for(forward_task, timeout=3)
        while not manager._event_queue.empty():
            event = manager._event_queue.get_nowait()
            events.put({"type": event.type, "payload": event.payload})
        events.put({"type": "worker_done", "payload": {"elapsed_seconds": manager._state.elapsed_seconds, "meeting_id": manager.meeting_id, "complete": not manager._task.cancelled(), "dropped_chunks": manager._state.audio_input_queue_drop_total + manager._audio_drop_total}})
    finally:
        if not stopped:
            await manager.stop(graceful=False)
        if forward_task and not forward_task.done():
            forward_task.cancel()
        storage.close()
