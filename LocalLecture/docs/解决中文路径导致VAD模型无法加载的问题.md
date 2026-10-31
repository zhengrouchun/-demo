# 解决中文路径导致 VAD 模型无法加载的问题

日期：2026-10-02。

## 问题与原因

真实 Whisper 验证出现 `silero-vad unavailable, falling back to RMS gate`，提示 bundled `silero_vad.jit` 无法打开。文件实际存在，项目路径 `D:\语音转文字工具` 含中文。转写回退到能量阈值继续，但没有用预期的 Silero 模型。

阅读 `audio/vad.py` 的 `_get_model()`、已安装 `silero_vad/model.py` 的加载逻辑，核对 `silero_vad.data` 的打包资源存在。当前 Windows/PyTorch 底层路径打开无法处理该中文路径；改用内存字节加载后复测，区分了缺文件与路径加载问题。没有下载模型、移动项目或要求改英文目录。

## 解决流程

修改 `app/backend/meetingbro/audio/vad.py` 的 `SileroSpeechDetector._get_model()`：

1. 优先原来的 `load_silero_vad()`。
2. 捕获 `OSError`/`RuntimeError`，只在 Windows 且打包资源存在时启用补救。
3. 用 `importlib.resources.files('silero_vad.data')` 定位资源，Python `read_bytes()` 读取。
4. 用 `io.BytesIO` 和 `torch.jit.load(..., map_location='cpu')` 绕开底层直接打开中文文件路径。
5. 调 `eval()`，沿用缓存和锁；其他异常仍走原有回退。

## 阅读与使用的文件

- `app/backend/meetingbro/audio/vad.py`：加载、检测与回退；修改 `_get_model()`。
- 虚拟环境 `site-packages/silero_vad/model.py`、`silero_vad/data/silero_vad.jit`：加载路径与资源名称/存在性。
- `app/backend/meetingbro/growmate/voice_worker.py`：子进程启用真实 VAD。
- `scripts/verify_growmate_real_asr.py`：缓存模型、离线 WAV 验证，不开麦克风。
- `data/sample_en.wav`：22.5 秒原有样本，未修改。

## 指令与结果

在 `LocalLecture`：

```powershell
.\app\backend\.venv\Scripts\python.exe scripts\verify_growmate_real_asr.py
.\app\backend\.venv\Scripts\python.exe -m unittest discover -s tests -p test_growmate.py -v
.\app\backend\.venv\Scripts\python.exe scripts\verify_stop_drain.py
```

真实脚本设 `HF_HUB_OFFLINE=1`，不重新下载。修改后这次验证未再出现 Silero 回退提示，保存 5 段、子进程正常退出与释放；16 项规则/接口测试及停止回归通过。此修复针对当前环境中文路径，并非所有 VAD 故障，能量回退仍保留。
