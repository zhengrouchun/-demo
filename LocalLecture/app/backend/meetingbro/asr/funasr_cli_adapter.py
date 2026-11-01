"""Run the local Fun-ASR-Nano Windows CPU binary on short audio windows."""

from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from .base import ASRAdapter, ASRSegment


SRT_ENTRY = re.compile(
    r"(?m)^\d+\s*\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n([^\n]*)"
)


def _srt_seconds(timestamp: str) -> float:
    hour, minute, second_with_milliseconds = timestamp.split(":")
    second, millisecond = second_with_milliseconds.split(",")
    return int(hour) * 3600 + int(minute) * 60 + int(second) + int(millisecond) / 1000


def _correct_network_terms(speech: str) -> str:
    if not re.search(r"地址|子网|网卡|路由|网关|IP", speech, re.IGNORECASE):
        return speech
    speech = re.sub(r"麦克(?=地址)", " MAC ", speech)
    speech = re.sub(r"(?<=原)麦克(?=为)", " MAC ", speech)
    speech = re.sub(r"(?<=自己的)麦克(?=[，。]|$)", " MAC", speech)
    speech = re.sub(r"万口(?=接入互联网)", " WAN 口", speech)
    speech = re.sub(r"[万烂]口(?=接入本地网络)", " LAN 口", speech)
    speech = re.sub(r"\s*one\s*口(?=接入互联网)", " WAN 口", speech, flags=re.IGNORECASE)
    speech = re.sub(r"(?<![A-Za-z])mac(?![A-Za-z])", "MAC", speech, flags=re.IGNORECASE)
    return re.sub(r"(?<![A-Za-z])lan(?![A-Za-z])", "LAN", speech, flags=re.IGNORECASE)


class FunASRNanoAdapter(ASRAdapter):
    def __init__(self, *, executable: Path, encoder: Path, decoder: Path, working_directory: Path | None = None, chunk_seconds: int = 10) -> None:
        self.executable = executable
        self.encoder = encoder
        self.decoder = decoder
        self.working_directory = working_directory
        self.chunk_seconds = chunk_seconds

    def _command_path(self, path: Path) -> str:
        if self.working_directory:
            return str(path.resolve().relative_to(self.working_directory.resolve()))
        return str(path)

    def ensure_loaded(self) -> None:
        for model_file in (self.executable, self.encoder, self.decoder):
            if not model_file.is_file():
                raise FileNotFoundError(f"Fun-ASR-Nano file is missing: {model_file}")

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        forced_language: str | None = None,
        offset_seconds: float = 0.0,
        initial_prompt: str | None = None,
        quality_preset: str = "realtime",
    ) -> list[ASRSegment]:
        if sample_rate != 16000:
            raise ValueError(f"Fun-ASR-Nano expects 16 kHz audio, got {sample_rate}")
        if samples.size == 0:
            return []
        temporary_root = self.working_directory / "data" / "funasr-temp" if self.working_directory else None
        if temporary_root:
            temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="locallecture-funasr-", dir=temporary_root) as temporary_directory:
            wav_path = Path(temporary_directory) / "window.wav"
            sf.write(wav_path, np.clip(samples, -1, 1), sample_rate, subtype="PCM_16")
            command = [str(self.executable), "--enc", self._command_path(self.encoder), "-m", self._command_path(self.decoder), "--chunk", str(self.chunk_seconds), "--srt", "-a", self._command_path(wav_path)]
            completed = subprocess.run(command, cwd=self.working_directory, check=False, capture_output=True, timeout=max(120, len(samples) / sample_rate * 3))
        if completed.returncode != 0:
            diagnostic = completed.stderr[-500:].decode("utf-8", errors="replace")
            raise RuntimeError(f"Fun-ASR-Nano failed with exit code {completed.returncode}: {diagnostic}")
        subtitles = completed.stdout.decode("utf-8-sig", errors="replace")
        language = "en" if forced_language == "en" else "zh"
        return [
            ASRSegment(offset_seconds + _srt_seconds(start), offset_seconds + _srt_seconds(end), _correct_network_terms(speech.strip()), language, 0.5)
            for start, end, speech in SRT_ENTRY.findall(subtitles)
            if speech.strip()
        ]
