"""Offline smoke test with the repository's sample WAV; never opens a mic."""
from __future__ import annotations
import asyncio
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))
os.environ["HF_HUB_OFFLINE"] = "1"

from meetingbro.growmate.repository import Repository
from meetingbro.growmate.voice import VoiceController


def working_set(pid):
    if os.name != "nt": return 0
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), *[(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle: return 0
    try:
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / 1024 / 1024
        return 0
    finally:
        kernel.CloseHandle(handle)


async def main():
    baseline = working_set(os.getpid())
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        repo = Repository(folder / "growmate.db")
        controller = VoiceController(repo, folder)
        peak = 0
        try:
            await controller.start({"title": "真实Whisper离线验证", "source": "mic", "model": "small", "language": "en", "_fixture_path": str(ROOT / "data" / "sample_en.wav")})
            task = controller.task
            deadline = asyncio.get_running_loop().time() + 120
            while not task.done():
                if asyncio.get_running_loop().time() > deadline: raise TimeoutError("ASR smoke test exceeded 120 seconds")
                peak = max(peak, working_set(controller.process.pid))
                await asyncio.sleep(.2)
            await task
            snapshot = controller.snapshot()["payload"]
            assert snapshot["phase"] == "ended", snapshot
            assert snapshot["segments"], snapshot
            assert snapshot["resources_released"] and controller.process.exitcode == 0
            text = " ".join(s["text"] for s in snapshot["segments"])
            assert "planning" in text.lower() or "meeting" in text.lower(), text
            assert not list(folder.rglob("*.wav"))
            print(json.dumps({"ok": True, "model": "small / cpu / int8", "text": text, "segments": len(snapshot["segments"]), "elapsed_seconds": snapshot["session"]["elapsed_seconds"], "worker_peak_mb": round(peak, 1), "parent_before_mb": round(baseline, 1), "parent_after_mb": round(working_set(os.getpid()), 1), "worker_exit_code": controller.process.exitcode, "resources_released": snapshot["resources_released"], "raw_audio_files_created": 0}, ensure_ascii=False))
        finally:
            await controller.close()
            repo.close()


if __name__ == "__main__":
    asyncio.run(main())
