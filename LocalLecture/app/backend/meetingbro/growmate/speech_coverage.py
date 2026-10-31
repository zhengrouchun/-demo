"""避免短句被前置裁音丢弃；集中管理 GrowMate 逐字稿的识别配置。"""

import os  # 读取逻辑处理器数量，为录音和网页保留运行余量。


def model_options(model_size: str) -> dict:
    """返回本地模型参数，不下载模型，也不修改系统音频设备。"""
    logical_cores = os.cpu_count() or 2  # 无法读取硬件数量时按双线程处理。
    return {
        "model_size": model_size,  # 保留用户选择的识别模型。
        "device": "cpu",  # 沿用当前项目的本地 CPU 运行方式。
        "compute_type": "int8",  # 沿用量化模型以控制内存用量。
        "cpu_threads": max(1, min(4, logical_cores // 2)),  # 限制识别线程争用。
        "num_workers": 1,  # 同时只解码一个音频窗口，避免重复抢占 CPU。
        "beam_size": 3,  # 比较三个解码候选，改善只选单一候选造成的错词。
    }


def session_options(language: str | None = None) -> dict:
    """保留连续波形，让模型内部 VAD 在较完整的上下文中判断人声。"""
    return {
        "pre_vad_enabled": False,  # 不在每半秒音频上提前裁掉疑似非人声。
        "pre_vad_conditioning_enabled": False,  # 在完整窗口统一调节音量。
        "weak_speech_rescue_enabled": False,  # 没有前置丢音，不再重复补识别。
        "asr_accumulation_seconds": 10.0,  # 连续讲话最多积累十秒；实测比六秒切分保留更完整的句意。
        "asr_early_flush_enabled": True,  # 遇到停顿时允许提前提交短句。
        "asr_early_flush_min_seconds": 2.0,  # 减少不足一秒窗口的频繁解码。
        "silence_rms_threshold": 0.0008,  # 放行轻声，纯静音仍跳过识别。
        "audio_conditioning_min_rms": 0.0008,  # 允许对同一范围的轻声增益。
        "audio_conditioning_max_gain": 4.0,  # 限制放大量，峰值保护仍然有效。
        "fast_preview_enabled": False,  # 逐字稿模式只运行一个识别通道。
        "filler_filter_enabled": False,  # 不自动删除口头语，保留逐字稿内容。
        "audio_input_queue_max_seconds": 600,  # 保留现有十分钟内存缓冲上限。
        "vocabulary_hint": "以下是简体中文的语音转写。" if language == "zh" else None,  # 中文模式统一提示简体；其他语言不附加中文提示。
    }
