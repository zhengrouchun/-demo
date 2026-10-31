"""Regression check: normal Stop transcribes audio already captured in memory."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

from meetingbro.asr.base import ASRAdapter, ASRSegment  # noqa: E402
from meetingbro.audio.capture import AudioChunk, AudioSource  # noqa: E402
from meetingbro.session.manager import SessionConfig, SessionManager  # noqa: E402
from meetingbro.storage.db import Storage  # noqa: E402
from meetingbro.summarization.base import Summarizer  # noqa: E402
from meetingbro.translation.base import Translator  # noqa: E402


class BufferedSource(AudioSource):
    def __init__(self) -> None:
        self.produced = asyncio.Event()
        self.closed = asyncio.Event()

    @property
    def sample_rate(self) -> int:
        return 16_000

    async def stream(self):
        samples = (0.04 * np.sin(2.0 * np.pi * 440.0 * np.arange(8_000) / self.sample_rate)).astype(np.float32)
        for index in range(10):
            yield AudioChunk(samples.copy(), self.sample_rate, index * 0.5)
            await asyncio.sleep(0)
        self.produced.set()
        await self.closed.wait()

    async def aclose(self) -> None:
        self.closed.set()


class SlowASR(ASRAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, samples, sample_rate, *, forced_language=None, offset_seconds=0.0, initial_prompt=None, quality_preset="realtime"):
        time.sleep(0.05)
        self.calls += 1
        return [ASRSegment(0.0, len(samples) / sample_rate, f"第{self.calls}段", "zh", 0.95)]


class OfflineSummary(Summarizer):
    def summarize(self, segments, *, kind, language, previous_summary=None, vocabulary=None):
        return ""


class NoTranslation(Translator):
    def translate(self, text, *, source_language, target_language):
        return text


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = Storage(Path(temp_dir) / "stop-drain.db")
        source = BufferedSource()
        asr = SlowASR()
        try:
            manager = SessionManager(SessionConfig(
                audio_source=source,
                asr=asr,
                summarizer=OfflineSummary(),
                translator=NoTranslation(),
                storage=storage,
                forced_language="zh",
                summary_language="zh",
                pre_vad_enabled=False,
                asr_accumulation_seconds=0.5,
                asr_early_flush_enabled=False,
                audio_conditioning_enabled=False,
                rolling_interval_seconds=10_000,
                cumulative_interval_seconds=10_000,
                memory_interval_seconds=10_000,
                watchdog_enabled=False,
                fast_preview_enabled=False,
            ))
            await manager.start()
            await asyncio.wait_for(source.produced.wait(), timeout=3)
            await manager.stop()
            segments = storage.list_segments(manager._state.meeting_id)
            assert manager._state.audio_input_queue_drop_total == 0
            assert manager._state.elapsed_seconds >= 5.0, manager._state.elapsed_seconds
            assert asr.calls >= 10, asr.calls
            assert segments, "no transcript was saved"
            print(f"[OK] Stop drained 5.0s of buffered audio; ASR calls={asr.calls}, saved segments={len(segments)}")
        finally:
            storage.close()


if __name__ == "__main__":
    asyncio.run(main())
