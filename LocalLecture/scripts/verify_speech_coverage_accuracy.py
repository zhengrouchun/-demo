"""离线比较旧分段和连续音频方案；只读取已有 WAV，不录音、不联网。"""
import argparse  # 接收测试音频和语言。
import asyncio  # 执行真实会话处理链。
import json  # 输出可复核的识别结果。
import os  # 强制缓存模型离线运行。
from pathlib import Path  # 定位项目文件。
import sys  # 导入项目模块。
import tempfile  # 隔离测试数据库。
import time  # 记录实际处理时长。
from unittest.mock import MagicMock  # 禁用本任务无关的摘要与翻译。

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


class TranscriptOnlySession(SessionManager):
    def _schedule_summary(self, coro):
        coro.close()  # 与 GrowMate 一样不运行摘要任务。

    async def _emit_final(self):
        return  # 不请求最终摘要。

    async def _emit_memory(self, *, force=False):
        return  # 不请求记忆提取。


async def compare(args):
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
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / "transcripts.db")  # 不触碰真实历史记录。
            manager = TranscriptOnlySession(SessionConfig(
                audio_source=WavFileSource(Path(args.wav), chunk_seconds=0.5), asr=asr,
                storage=storage, summarizer=MagicMock(), translator=MagicMock(),
                forced_language=args.language, summary_language=args.language,
                watchdog_enabled=False, **options,
            ))
            try:
                started = time.perf_counter()  # 记录回放处理开始时间。
                await manager.start()  # 启动真实会话流程。
                await asyncio.wait_for(asyncio.shield(manager._task), timeout=180)  # 等待所有音频识别完毕。
                await manager.stop()  # 排空文字并释放线程资源。
                text = " ".join(segment.text for segment in manager._state.segments)  # 拼接最终文字。
                result = {"profile": label, "seconds": round(time.perf_counter() - started, 2), "text": text,
                          "segments": len(manager._state.segments), "queue_drops": manager._state.audio_input_queue_drop_total}
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
