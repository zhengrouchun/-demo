"""离线比较旧分段和连续音频方案；只读取已有 WAV，不录音、不联网。"""
import argparse  # 接收测试音频和语言。
import asyncio  # 执行真实会话处理链。
import json  # 输出可复核的识别结果。
import math  # 向上计算末尾不足半秒的音频块。
import os  # 强制缓存模型离线运行。
from pathlib import Path  # 定位项目文件。
import sys  # 导入项目模块。
import tempfile  # 隔离测试数据库。
import time  # 记录实际处理时长。
from unittest.mock import MagicMock  # 禁用本任务无关的摘要与翻译。
import soundfile as sf  # 读取样本时长，与 WAV 回放器使用相同的解码库。

ROOT = Path(__file__).resolve().parents[1]  # 取得项目根目录。
sys.path.insert(0, str(ROOT / "app" / "backend"))  # 使用工作区源码。
os.environ["HF_HUB_OFFLINE"] = "1"  # 不下载任何模型。
sys.stdout.reconfigure(encoding="utf-8")  # Windows 输出中文时避免控制台代码页乱码。
from meetingbro.asr.faster_whisper_adapter import FasterWhisperAdapter  # 运行真实本地识别。
from meetingbro.audio.capture import WavFileSource  # 按半秒音频块回放样本。
from meetingbro.growmate.speech_coverage import model_options, session_options  # 读取修复配置。
from meetingbro.session.manager import SessionConfig, SessionManager  # 使用实际会话处理。
from meetingbro.storage.db import Storage  # 保存并核对最终文字。
from asr_metrics import cer  # 使用项目已有字符错误率算法。

AUDIO_CHUNK_SECONDS = 0.5  # 基准脚本每次向会话输入半秒音频。
LONG_COURSE_AUDIO_SECONDS = 60 * 60  # 验收中的一小时课程时长。
POST_COURSE_DELIVERY_SECONDS = 10 * 60  # 验收允许的结束后十分钟。
BENCHMARK_TIMEOUT_GRACE_SECONDS = 10 * 60  # 慢模型额外保留的诊断时间。
MIN_BENCHMARK_TIMEOUT_SECONDS = 180  # 小样本仍保留既有三分钟等待预算。
MAX_BENCHMARK_TIMEOUT_SECONDS = 80 * 60  # 即使任务卡住也在八十分钟内结束。


def offline_queue_capacity_seconds(wav_path: Path, *, chunk_seconds: float) -> float:
    duration_seconds = sf.info(str(wav_path)).duration  # 读取原始样本的完整时长。
    audio_chunk_count = math.ceil(duration_seconds / chunk_seconds)  # 计入不足一个整块的尾音频。
    return (audio_chunk_count + 1) * chunk_seconds  # 队列可容纳全部块并留一个缓冲位。


def offline_benchmark_time_limits(duration_seconds: float) -> tuple[float, float]:
    speed_target_seconds = duration_seconds * (LONG_COURSE_AUDIO_SECONDS + POST_COURSE_DELIVERY_SECONDS) / LONG_COURSE_AUDIO_SECONDS  # 按长课验收比例换算吞吐目标。
    timeout_seconds = min(MAX_BENCHMARK_TIMEOUT_SECONDS, max(MIN_BENCHMARK_TIMEOUT_SECONDS, speed_target_seconds + BENCHMARK_TIMEOUT_GRACE_SECONDS))  # 在目标外允许诊断但限制总等待。
    return speed_target_seconds, timeout_seconds  # 让速度判定和超时分别可复核。


class TranscriptOnlySession(SessionManager):
    def _schedule_summary(self, coro):
        coro.close()  # 与 GrowMate 一样不运行摘要任务。

    async def _emit_final(self):
        return  # 不请求最终摘要。

    async def _emit_memory(self, *, force=False):
        return  # 不请求记忆提取。


async def compare(args):
    queue_capacity_seconds = offline_queue_capacity_seconds(Path(args.wav), chunk_seconds=AUDIO_CHUNK_SECONDS)  # 非实时回放仍须完整保留样本。
    duration_seconds = sf.info(str(args.wav)).duration  # 用同一输入时长计算速度目标。
    speed_target_seconds, timeout_seconds = offline_benchmark_time_limits(duration_seconds)  # 长音频不再被固定三分钟截断。
    for label in ("previous", "continuous"):
        parameters = model_options("small")  # 使用同一模型规模。
        if label == "previous":
            parameters.update(cpu_threads=max(1, min(8, os.cpu_count() or 4)), beam_size=1)  # 还原旧模型参数。
        asr = FasterWhisperAdapter(**parameters)  # 每组独立加载以隔离配置。
        await asyncio.to_thread(asr.ensure_loaded)  # 将加载时间排除在处理耗时之外。
        options = session_options(args.language) if label == "continuous" else {
            "fast_preview_enabled": False, "filler_filter_enabled": False,
            "pre_vad_enabled": True, "asr_accumulation_seconds": 2.0,
        }  # 旧方案保留原来的前置 VAD 与两秒窗口。
        if args.window and label == "continuous":
            options["asr_accumulation_seconds"] = args.window  # 允许验证候选窗口长度。
        options["audio_input_queue_max_seconds"] = queue_capacity_seconds  # 两组使用相同的无丢块离线队列。
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "transcripts.db")  # 不触碰真实历史记录。
            manager = TranscriptOnlySession(SessionConfig(
                audio_source=WavFileSource(Path(args.wav), chunk_seconds=AUDIO_CHUNK_SECONDS), asr=asr,
                storage=storage, summarizer=MagicMock(), translator=MagicMock(),
                forced_language=args.language, summary_language=args.language,
                watchdog_enabled=False, **options,
            ))
            try:
                started = time.perf_counter()  # 记录回放处理开始时间。
                await manager.start()  # 启动真实会话流程。
                await asyncio.wait_for(asyncio.shield(manager._task), timeout=timeout_seconds)  # 给长音频有上限的完整处理时间。
                await manager.stop()  # 排空文字并释放线程资源。
                text = " ".join(segment.text for segment in manager._state.segments)  # 拼接最终文字。
                elapsed_seconds = time.perf_counter() - started  # 用实际耗时判断速度，而不是用超时作为达标标志。
                result = {"profile": label, "seconds": round(elapsed_seconds, 2), "text": text,
                          "speed_target_seconds": round(speed_target_seconds, 2), "speed_target_met": elapsed_seconds <= speed_target_seconds,
                          "segments": len(manager._state.segments), "queue_drops": manager._state.audio_input_queue_drop_total}
                if result["queue_drops"]:
                    raise RuntimeError(f"{label} 输入队列丢弃了 {result['queue_drops']} 个音频块，结果不能用于准确率比较")  # 拒绝不完整的比较结果。
                if args.reference:
                    reference = Path(args.reference).read_text(encoding="utf-8-sig")  # 使用确定的原文比较。
                    result["character_error_rate"] = round(cer(reference, text), 4)  # 不以主观感觉报告准确率。
                print(json.dumps(result, ensure_ascii=False), flush=True)  # 输出每组完整证据。
            finally:
                await manager.stop()  # 失败时也释放后台任务。
                storage.close()  # Windows 删除临时目录前释放数据库。


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)  # 提供可复现的命令行入口。
    parser.add_argument("wav", nargs="?", default=str(ROOT / "data" / "sample_en.wav"))  # 默认使用已有英语样本。
    parser.add_argument("--language", choices=("zh", "en"), default="en")  # 指定样本语言。
    parser.add_argument("--reference")  # 可选人工原文，用于字符错误率计算。
    parser.add_argument("--window", type=float)  # 可选候选窗口长度。
    asyncio.run(compare(parser.parse_args()))  # 顺序测试，避免两个模型同时抢占 CPU。
