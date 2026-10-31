# Fun-ASR 中文路径导致模型无法加载的解决说明

## 根因与证据

Windows CPU 版 `llama-funasr-cli.exe` 能运行，但从 Python 子进程收到包含 `D:\语音转文字工具` 的绝对 GGUF 路径时，报 `gguf_init_from_file: failed to open GGUF file`。先前从项目目录用英文相对路径运行同一模型成功。另一次端到端测试发现 CLI 的诊断输出含非 UTF-8 字节，直接以 UTF-8 解码整个子进程输出会抛 `UnicodeDecodeError` 并跳过音频窗口。

## 解决流程与涉及文件

先阅读 `voice_worker.py` 的模型加载与采音分支、`asr/base.py` 的 `transcribe` 接口、`session/manager.py` 的窗口调用、`transcript.py` 的导出模型名及 `start-growmate.ps1` 的启动地址。随后用 10 秒临时 WAV 验证 CLI 可在 6.93 秒内生成时间戳；真实会话测试复现中文绝对路径失败，再把 GGUF 和临时 WAV 参数改为相对于 LocalLecture 工作目录的英文路径。子进程输出先按字节接收，只对 SRT 正文解码；诊断字节按替换模式显示，不再影响正常识别。每个窗口的临时 WAV 由临时目录在调用后删除。

| 文件 | 本次关键语句的作用 |
|---|---|
| `asr/funasr_cli_adapter.py` | 定义可读名称的模型路径和工作目录；验证文件存在；把 16 kHz 音频写成短窗 PCM WAV；用英文相对参数调用本地 CLI；检查退出码；解析 SRT 时间戳并加上会话偏移；离开临时目录时删除 WAV。 |
| `growmate/voice_worker.py` | 只在选中 `funasr-nano-gguf-q8_0` 时加载新适配器，并关闭提前短窗刷新，维持 10 秒窗口处理。旧 Whisper 分支保留。 |
| `growmate/voice.py` | 接受真实模型名；只允许新模型处理系统声音；删除历史时拒绝活动课程和越界路径，并在数据库出错时恢复暂存 Markdown。 |
| `growmate/transcript.py` | 按会话记录的实际模型写 Markdown 标题，旧历史继续显示 Whisper。 |
| `growmate/web.py` | 新增单条历史 DELETE 路由，复用已有错误响应。 |
| `growmate/Voice.tsx`、`GrowMateApp.tsx`、`main.tsx` | 专用页面固定系统声音和 Fun-ASR-Nano，保留开始、暂停、结束、预览、历史下载及确认删除；原 GrowMate 入口保持可用。 |
| `scripts/start-growmate.ps1`、`启动课堂系统声音转文字.cmd` | 双击入口启动原后端并打开 `/?transcript`；已运行时直接打开同一页面。 |
| `LocalLecture/.gitignore` | 忽略运行时的短窗临时音频目录，防止录音片段进入提交。 |
| `test_funasr_cli_adapter.py` | 用伪造的 SRT 和非 UTF-8 诊断字节验证时间戳、文本与临时文件清理。 |
| `test_growmate.py` | 用真实 25 秒测试音频走完整子进程，验证中文路径、模型名、导出及资源清理。 |
| `test_voice_history_delete.py` | 建立两份隔离课程，验证只删除选中记录、活动课程拒绝、越界路径拒绝和数据库异常后的文件恢复。 |

## 验证与限制

`test_funasr_cli_adapter.py` 验证时间戳和临时 WAV 清理；`test_voice_history_delete.py` 验证选中删除、活动会话拒绝、越界路径拒绝和数据库错误时文件恢复。`test_growmate.py` 的真实 25 秒系统声 fixture 已通过，导出显示真实模型名；前端 `npm.cmd run build` 通过。完整 60 分钟系统回环录音、断网运行与人工逐句关键错误核对仍需验收，不能用短样本结果代替。

实际运行的关键命令和结果：

- `app/backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_growmate.py -v`：18 项通过，包含真实 Fun-ASR 子进程、旧页面和强退恢复。
- `app/backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_voice_history_delete.py -v`：4 项通过。
- `app/backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_funasr_cli_adapter.py -v`：1 项通过。
- `npm.cmd run build`：TypeScript 和 Vite 构建成功。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File LocalLecture/scripts/start-growmate.ps1 -NoBrowser -Transcript`：健康检查返回 GrowMate，`/?transcript` 返回 HTTP 200，历史删除路由已注册；随后通过 `/api/shutdown` 正常退出。
- 622.8 秒用户样本按真实时间回放：总耗时 644.77 秒、62 段、最终字错率 3.01%、会话错误为空、Markdown 已生成。该次是文件回放，不是 60 分钟扬声器回环验收。
