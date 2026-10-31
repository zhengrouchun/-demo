# LocalLecture 本地离线课堂语音转文字助手——产品需求文档 PRD V1.0

版本：V1.0  
目标平台：Windows 10 / Windows 11  
建议技术底座：MeetingBro 二次开发  
核心目标：只做“本地语音转文字 + Markdown 逐字稿”，不做 AI 总结，不保存原始音频，不强制使用任何付费 API。  
适用场景：B站、学习通、浏览器课程、Windows 本地播放课程、现实课堂老师授课。  

---

## 1. 项目背景

LocalLecture 的目标不是做一个“大而全”的 AI 学习平台，而是解决一个最明确的问题：

> 上课时自动把老师讲的话转成文字，下课后得到一份完整、可继续交给 ChatGPT 网页版处理的 Markdown 逐字稿。

用户已经有 ChatGPT 网页版用于后续知识总结，因此 V1.0 不集成 OpenAI、Claude、DeepSeek、Groq、Ollama 等任何大模型总结功能，也不需要联网消耗 Token。

V1.0 必须优先保证：

1. 稳定抓到声音。
2. 能长时间持续转录。
3. 不保存原始录音。
4. 转录结果不中途丢失。
5. 下课能得到一个完整 `.md` 文件。
6. 不为了“功能多”破坏原有稳定链路。

---

## 2. 技术选型结论

### 2.1 建议底座：MeetingBro，不建议同时混合 Buzz 源码

V1.0 建议以 MeetingBro 为唯一底座。

原因：

- MeetingBro 已经有 Windows 系统音频捕获。
- MeetingBro 已经有麦克风捕获。
- MeetingBro 已经有本地 faster-whisper。
- MeetingBro 已经有 VAD、音频重采样、会话管理、SQLite、Markdown 导出。
- MeetingBro 已经有 Electron + React 桌面 UI。
- MeetingBro 已经有 Windows 安装和启动脚本。
- MeetingBro 已经有多项验证脚本和测试。

Buzz 可以作为“参考项目”，但不要直接把 Buzz 的转录代码复制进 MeetingBro。

原因是两个项目的：
- UI 框架不同；
- 会话模型不同；
- 音频接口不同；
- 线程模型不同；
- 导出结构不同；
- ASR 生命周期不同。

把两个项目拼接，很容易制造依赖冲突、线程阻塞、设备抢占和重复转录 Bug。

### 2.2 V1.0 不追求 Intel Arc GPU / NPU 加速

当前电脑配置大致为：

- Intel Core Ultra 5 225H
- 32 GB 内存
- Intel Arc 130T 集成 GPU
- Intel AI Boost NPU
- NVMe SSD

MeetingBro 当前正式 ASR 路径使用 faster-whisper。V1.0 应先选择：

- Whisper：`small`
- Device：`cpu`
- Compute type：`int8`
- Language：固定 `zh`

不要为了使用 Intel Arc / NPU，在 V1.0 引入 OpenVINO、DirectML、oneAPI、Whisper.cpp Vulkan 等第二套推理后端。

原因：

> V1.0 的第一目标是“稳定得到完整逐字稿”，不是硬件利用率最大化。

等 CPU 版本稳定后，再单独做 V1.1/V2.0 性能优化。

---

## 3. 产品目标

### 3.1 核心用户故事

#### 场景 A：B站网课

用户：
1. 打开 LocalLecture。
2. 输入“计算机网络 第5课”。
3. 选择“电脑系统声音”。
4. 点击“开始转录”。
5. 打开 B站课程。
6. 正常看课。
7. 下课点击“结束课程”。
8. 得到：

`计算机网络_第5课_2026-09-10.md`

#### 场景 B：学习通

流程与 B站一致。

LocalLecture 不需要知道“这是学习通”。

只要声音通过 Windows 默认播放设备播放，就从系统音频抓取。

#### 场景 C：现实课堂

用户：
1. 打开 LocalLecture。
2. 输入课程名称。
3. 选择“麦克风”。
4. 点击“开始转录”。
5. 笔记本放在课桌上。
6. 下课点击“结束课程”。
7. 得到完整 Markdown 逐字稿。

---

## 4. V1.0 功能范围

### 4.1 必须实现

| ID | 功能 | 优先级 |
|---|---|---|
| FR-001 | Windows 系统声音捕获 | P0 |
| FR-002 | 麦克风捕获 | P0 |
| FR-003 | 本地 Whisper 中文语音识别 | P0 |
| FR-004 | 不依赖付费 API | P0 |
| FR-005 | 不持久化保存原始音频 | P0 |
| FR-006 | 课程名称输入 | P0 |
| FR-007 | 开始转录 | P0 |
| FR-008 | 暂停 / 继续 | P0 |
| FR-009 | 结束课程 | P0 |
| FR-010 | 生成一个 Markdown 逐字稿 | P0 |
| FR-011 | 逐段时间戳 | P0 |
| FR-012 | 转录结果自动落盘，防止崩溃全丢 | P0 |
| FR-013 | 最近识别内容预览 | P1 |
| FR-014 | 转录时长、字数、状态显示 | P1 |
| FR-015 | 历史课程列表 | P1 |
| FR-016 | 打开输出文件夹 | P1 |
| FR-017 | 音频设备诊断 | P1 |

### 4.2 V1.0 明确不做

以下功能不得擅自添加：

- OpenAI API
- Claude API
- DeepSeek API
- Groq API
- 云端 Whisper API
- Ollama 总结
- AI 课堂总结
- 实时翻译
- 说话人识别
- 会议决策
- Action Items
- 会议看板
- 实时双语字幕
- 原始 WAV/MP3/M4A 长期保存
- 登录注册
- 云同步
- 多端同步
- 浏览器插件
- B站账号接入
- 学习通账号接入
- 爬虫
- 自动上传 ChatGPT

原则：

> V1.0 只把“声音 → 文字 → Markdown”做稳定。

---

## 5. 关键产品逻辑

### 5.1 为什么“实时转录”但“不需要实时字幕”

用户并不需要在软件里一直看字幕，因为 B站/学习通本身可能已有字幕。

所以 LocalLecture 的“实时”含义是：

> 上课时持续把音频送给 Whisper 识别，而不是等下课后再处理整段录音。

原因是用户要求“不保存原始音频”。

正确流水线：

```text
老师声音 / 系统声音
        ↓
短音频块
        ↓
Whisper
        ↓
得到文字
        ↓
保存文字
        ↓
释放音频块
```

禁止：

```text
整节课
↓
保存 90 分钟 WAV
↓
下课后再转录
```

因为这与“不保存原始音频”的要求冲突。

### 5.2 音频只允许存在于内存缓冲区

允许：
- 内存中的 `numpy.ndarray`
- Queue 中尚未处理的短音频块
- Whisper 当前处理窗口

不允许：
- 自动生成整节课 `.wav`
- 自动生成 `.mp3`
- 自动生成 `.m4a`
- 在 cache/temp 中长期残留整节课音频

程序退出后，不应在输出目录找到课堂原始音频。

---

## 6. 建议界面

### 6.1 首页 / 新建课程

```text
┌──────────────────────────────────────┐
│ LocalLecture                         │
│ 本地离线课堂转录助手                 │
├──────────────────────────────────────┤
│                                      │
│ 课程名称                             │
│ [ 计算机网络 第5课               ]   │
│                                      │
│ 声音来源                             │
│ ● 电脑系统声音                       │
│   B站 / 学习通 / 浏览器 / 本地视频    │
│                                      │
│ ○ 麦克风                             │
│   现实课堂                           │
│                                      │
│ 识别语言：中文                       │
│ Whisper：Small                       │
│                                      │
│          [ 开始转录 ]                │
│                                      │
└──────────────────────────────────────┘
```

### 6.2 转录中

```text
┌──────────────────────────────────────┐
│ 计算机网络 第5课                     │
│ ● 正在转录                           │
├──────────────────────────────────────┤
│ 已转录：00:38:26                     │
│ 已识别：5,842 字                     │
│ 音频源：电脑系统声音                 │
│ 模型：Whisper Small / 中文           │
│                                      │
│ 最近识别：                           │
│ TCP 是一种面向连接的传输层协议……    │
│                                      │
│ [ 暂停 ]          [ 结束课程 ]       │
└──────────────────────────────────────┘
```

### 6.3 结束课程

```text
转录完成

课程：
计算机网络 第5课

时长：
01:26:52

文字：
12,438 字

保存位置：
D:\LocalLecture\Transcripts\
计算机网络_第5课_2026-09-10.md

[打开逐字稿]   [打开文件夹]   [返回首页]
```

---

## 7. Markdown 输出规范

只生成一个用户核心文件。

示例：

```markdown
# 计算机网络 第5课

- 日期：2026-09-10
- 时长：01:26:52
- 音频来源：电脑系统声音
- 识别语言：中文
- 识别模型：Whisper Small

---

## 课堂逐字稿

### [00:00:07 - 00:00:18]

今天我们继续讲 TCP 协议，上节课我们已经介绍过 TCP 和 UDP 的区别。

### [00:00:20 - 00:00:35]

TCP 是一种面向连接的可靠传输协议。

### [00:03:14 - 00:03:48]

下面大家重点注意一下三次握手……
```

V1.0 不要自动改写老师原话。

不自动：
- 总结
- 润色
- 补全
- 翻译
- 纠正专业内容
- 猜测老师没说完的话

因为逐字稿的价值就在于保留原始课堂信息。

---

# 8. 需要 Codex 先阅读的 MeetingBro 文件

下面是本项目最关键的一部分。

**Codex 不得直接开始大改。必须先阅读以下文件。**

仓库：

`https://github.com/armpro24-blip/MeetingBro`

---

## 8.1 第一组：先理解架构，只读不改

### `README.md`
用途：
- 项目安装方法
- Windows 系统声音能力
- Whisper 工作模式
- 当前功能范围

Codex 第一件事先读。

### `README.zh-CN.md`
用途：
- 中文版整体说明
- 快速确认系统音频、麦克风、Markdown 导出

### `docs/architecture.md`
这是最重要的架构文件。

必须搞清楚：

```text
系统声音 / 麦克风
↓
AudioSource
↓
VAD
↓
Whisper
↓
SessionManager
↓
SQLite
↓
Exporter
↓
Markdown
```

不要绕开现有流水线另造一套。

### `docs/platform-support.md`
重点读：
- Windows 系统音频
- 麦克风
- 设备兼容性

### `docs/troubleshooting.md`
在修改之前先了解已有问题和解决办法。

---

# 9. 各知识点对应哪个文件

## 9.1 Windows 系统声音 / WASAPI Loopback

核心文件：

`app/backend/meetingbro/audio/loopback.py`

核心知识点：

- WASAPI Loopback
- `soundcard`
- Windows 默认扬声器
- loopback microphone
- 采样率
- 48 kHz → 16 kHz 重采样
- stereo → mono
- 音频 Queue
- 音频设备切换
- Bluetooth / USB 耳机兼容性
- COM 线程初始化
- Queue 满时丢块处理

Codex 要保留现有：

`SystemAudioLoopbackSource`

不要自己重新用 PyAudio 写第二套系统音频采集。

现有路径本身已经会：
- 找默认扬声器；
- 寻找对应 loopback；
- 尝试多个采样率；
- 降为 mono；
- 重采样为 Whisper 使用的 16 kHz；
- 使用 Queue 将录音线程和 async 主流程隔开。

**修改原则：尽量不改 `loopback.py`。**

LocalLecture V1 的系统声音功能优先直接复用。

---

## 9.2 现实课堂麦克风

核心文件：

`app/backend/meetingbro/audio/capture.py`

重点类：

`MicrophoneSource`

需要理解：

- `sounddevice.InputStream`
- callback
- `queue.Queue`
- `AudioChunk`
- chunk duration
- mono float32
- 16 kHz

这里已经能满足现实课堂。

**V1 尽量不要重写。**

---

## 9.3 音频设备

核心文件：

`app/backend/meetingbro/audio/devices.py`

辅助脚本：

`scripts/list_audio_devices.py`

用途：

如果出现：

- 软件没有声音；
- 选错麦克风；
- 蓝牙耳机没抓到；
- 学习通有声音但 LocalLecture 没文字；

先诊断音频设备，而不是先改 Whisper。

---

## 9.4 VAD：判断“什么时候有人讲话”

核心文件：

`app/backend/meetingbro/audio/vad.py`

依赖：
`silero-vad`

概念：

VAD = Voice Activity Detection。

作用：

```text
10 秒音频
↓
只有 4 秒有人说话
↓
只把有讲话的部分交给 Whisper
```

可以降低 CPU 压力，也减少“安静时 Whisper 胡乱生成文字”。

V1 保留 VAD。

不要因为“只想要逐字稿”就删掉 VAD。

---

## 9.5 音频预处理

核心文件：

`app/backend/meetingbro/audio/enhancement.py`

主要知识点：

- RMS
- 音量归一化
- peak limiting
- 噪声较弱时的处理

现实课堂中老师距离电脑较远，这部分有价值。

V1 保留现有逻辑，先不要重新做降噪算法。

---

## 9.6 Whisper 本地语音识别

核心文件：

`app/backend/meetingbro/asr/base.py`

`app/backend/meetingbro/asr/faster_whisper_adapter.py`

重点类：

`FasterWhisperAdapter`

必须理解：

- faster-whisper
- WhisperModel
- `device`
- `compute_type`
- `beam_size`
- `forced_language`
- `vad_filter`
- `initial_prompt`
- segment timestamp
- confidence
- CPU int8

LocalLecture V1 推荐配置：

```text
model_size = small
device = cpu
compute_type = int8
forced_language = zh
```

原因：

- 课程主要中文；
- 固定中文可减少语言漂移；
- 32GB 内存足够；
- 不折腾 Intel Arc CUDA 不兼容问题；
- CPU int8 更容易先稳定跑通。

---

## 9.7 实时字幕 Preview ASR

相关文件：

`app/backend/meetingbro/asr/streaming.py`

`app/backend/meetingbro/asr/streaming_whisper_adapter.py`

`app/backend/meetingbro/asr/qwen3_asr_adapter.py`

LocalLecture V1：

**这些不是核心需求。**

用户不需要实时低延迟字幕。

目标：

- 不运行额外 Qwen3 preview；
- 不重复跑两次 ASR；
- 只保留正式 Whisper transcript 路径。

但是：

**不要直接删除文件。**

正确方式：

在 `SessionManager` 增加“transcript-only / low-load”模式，让 Preview ASR 不启动。

这样保留上游结构，减少破坏范围。

---

## 9.8 整个课堂转录流程的“大脑”

核心文件：

`app/backend/meetingbro/session/manager.py`

这是 Codex 改动最需要谨慎的文件。

它负责：

```text
音频输入
↓
VAD
↓
ASR
↓
转录 segment
↓
保存数据库
↓
WebSocket 通知前端
```

同时原版还会负责：

- preview ASR
- speaker diarization
- translation
- summarization

LocalLecture V1 应在这里增加明确的：

`transcript_only`

或：

`LOCALLECTURE_TRANSCRIPT_ONLY=true`

逻辑。

Transcript-only 模式下：

保留：
- Audio capture
- VAD
- Formal Whisper
- Transcript segment
- SQLite
- WebSocket transcript event

关闭：
- Preview ASR
- Translation
- Summarization
- Speaker diarization
- Qwen3 ASR preview

注意：

**不要把 SessionManager 整个重写。**

这是最容易制造并发、队列、停止流程 Bug 的地方。

---

## 9.9 本地数据库 / 防崩溃

核心文件：

`app/backend/meetingbro/storage/db.py`

MeetingBro 使用 SQLite 保存：
- meeting
- transcript_segments
- summaries
- notes 等

LocalLecture 应继续使用 SQLite 作为“中间保险”。

原因：

如果只在内存里保存 90 分钟文字：

```text
程序崩溃
↓
整堂课全部消失
```

正确：

```text
Whisper 得到一个正式 segment
↓
立刻写 SQLite
↓
前端只负责显示
```

即使软件崩溃，已经识别的文字还在。

### LocalLecture 可以简化数据

建议保留：

`courses`
- id
- title
- started_at
- ended_at
- source_type
- language
- whisper_model

`transcript_segments`
- id
- course_id
- start_time
- end_time
- text
- confidence
- created_at

但是：

V1 不要直接删除原数据库表。

更安全的做法：

1. 先继续复用 `meetings`。
2. 最小增量增加 `title` / course metadata。
3. UI 把“Meeting”显示成“课程”。
4. 等 V1 稳定以后再做数据库重构。

---

## 9.10 Markdown 导出

核心文件：

`app/backend/meetingbro/exporter.py`

MeetingBro 已经有：

`_write_transcript()`

和：

`export_meeting()`

LocalLecture 需要修改这里。

目标：

原来可能生成：

```text
transcript.md
summary.md
metadata.json
```

LocalLecture V1 对用户只输出：

```text
课程名称_日期.md
```

内容：
- 课程名称
- 日期
- 开始时间
- 结束时间 / 时长
- 来源
- Whisper 模型
- 完整逐字稿
- 时间戳

必须使用 UTF-8。

### 文件名清洗

需要处理 Windows 禁止的字符：

`\ / : * ? " < > |`

例如：

用户输入：

`C++/网络编程：Socket 第1课`

文件名不能直接使用。

应转换为：

`C++_网络编程_Socket_第1课_2026-09-10.md`

---

## 9.11 后端 HTTP / WebSocket

核心文件：

`app/backend/meetingbro/main.py`

知识点：

- FastAPI
- REST
- WebSocket
- start session
- stop session
- export
- history

LocalLecture 不需要推倒这一层。

继续使用：

```text
Electron/React
↓ HTTP
创建课程

Electron/React
↓ WebSocket
接收转录状态/最新文字

结束课程
↓ HTTP/WS
停止
↓
导出 Markdown
```

WebSocket 在这里不是联网到互联网。

它通常只是：

`localhost`

即：

```text
你的桌面界面
↕
你电脑上的 Python 后端
```

所以仍然属于本地运行。

---

## 9.12 数据结构

核心文件：

`app/backend/meetingbro/schemas.py`

知识点：

- Pydantic
- 前后端协议
- transcript segment
- session state
- export response

如果新增：
- course title
- source type
- transcript-only mode

需要同步检查这里。

不要只修改前端 TypeScript 类型而不改后端 Pydantic，反之亦然。

---

## 9.13 前端类型

核心文件：

`app/frontend/src/types.ts`

它与：

`app/backend/meetingbro/schemas.py`

需要保持对应。

这是典型 Bug 来源：

```text
后端字段叫 course_title
前端以为叫 title
↓
页面 undefined
```

每次接口变更必须同时核对两边。

---

## 9.14 前端和后端通信

核心文件：

`app/frontend/src/session/useSessionSocket.ts`

用途：

- 建立 WebSocket
- 收 transcript segment
- 收 session state
- 更新前端状态

不要另写第二个 WebSocket 管理器。

复用现有 hook。

---

## 9.15 LocalLecture 新 UI

原文件：

`app/frontend/src/App.tsx`

原 App 很大。

**不建议让 Codex 在原 App.tsx 中进行大规模“边删边改”。**

建议新建：

```text
app/frontend/src/locallecture/
    LocalLectureApp.tsx
    NewCourseView.tsx
    RecordingView.tsx
    FinishedView.tsx
    HistoryView.tsx
    locallecture.css
```

然后：

`app/frontend/src/main.tsx`

只做最小入口切换：

```text
旧：
<App />

新：
<LocalLectureApp />
```

这样：
- 原 UI 还保留；
- 出问题容易回退；
- diff 清晰；
- Codex 不需要在 9 万字节 App.tsx 中冒险删除大量逻辑。

等 LocalLecture UI 完全稳定，再清理旧 UI。

---

## 9.16 Electron 桌面壳

核心文件：

`app/frontend/electron/main.cjs`

`app/frontend/electron/backend.cjs`

`app/frontend/electron/preload.cjs`

用途：
- 创建 Windows 桌面窗口
- 启动 Python backend
- 前端与 Electron 交互

V1 尽量不要改。

只允许以后修改：
- 窗口标题
- 应用名称
- 图标
- 默认窗口大小

不要为了改名字去重构 Electron 启动机制。

---

## 9.17 Python 依赖

核心文件：

`app/backend/pyproject.toml`

现有核心依赖包括：
- FastAPI
- Uvicorn
- Pydantic
- WebSockets
- faster-whisper
- silero-vad
- sounddevice
- soundfile
- numpy
- scipy

Windows 系统音频还使用：

`soundcard`

LocalLecture V1：

不要新增不必要 AI SDK。

特别是最终安装环境没有必要要求：
- anthropic
- openai

如果保留上游 optional dependency 可以不动，但 LocalLecture 正常运行绝不能要求用户配置 API Key。

---

## 9.18 前端依赖

核心文件：

`app/frontend/package.json`

当前：

- Electron
- React
- TypeScript
- Vite

V1 不需要换技术栈。

不要改成 Vue。
不要改成 Tauri。
不要重写成 Python GUI。

换技术栈不会让项目更稳定，只会增加 Bug。

---

# 10. 需要保留的测试与诊断工具

## 必须运行

### `scripts/dep_check.py`
检查依赖是否正确。

### `scripts/list_audio_devices.py`
检查音频设备。

### `scripts/e2e_loopback.py`
这是系统声音功能的关键验证脚本。

必须在真正改 UI 前先证明：

```text
B站播放声音
↓
loopback 抓得到
```

### `scripts/e2e_vertical_slice.py`
验证核心纵向链路。

### `scripts/verify_export_meeting.py`
用于验证导出。

### `tests/test_faster_whisper_words.py`
Whisper 相关测试。

---

# 11. 建议新增测试

Codex 必须新增而不是只“肉眼看页面”。

建议：

```text
tests/test_locallecture_transcript_only.py
tests/test_locallecture_export.py
tests/test_locallecture_filename.py
tests/test_locallecture_no_audio_persistence.py
```

### `test_locallecture_transcript_only.py`

验证：
- transcript-only 模式能启动；
- 不启动 summarizer；
- 不启动 translator；
- 不启动 diarization；
- formal Whisper 仍工作。

### `test_locallecture_export.py`

验证：
输入三段 transcript segment 后，能够得到一个 Markdown 文件。

### `test_locallecture_filename.py`

输入：

`C++/网络编程：Socket?`

不能生成非法 Windows 文件名。

### `test_locallecture_no_audio_persistence.py`

一次测试会话结束后搜索：
- `.wav`
- `.mp3`
- `.m4a`
- `.flac`

LocalLecture 自己不应生成课堂原始音频文件。

注意：
仓库原本的测试 fixture / sample 音频不能算失败。

---

# 12. 性能策略

V1 默认：

```text
Whisper size = small
Language = zh
Device = cpu
Compute = int8
Diarization = off
Translation = off
Summarization = off
Preview ASR = off
```

### 为什么关闭 Preview ASR

MeetingBro 为实时字幕可以同时运行正式 ASR 和预览 ASR。

LocalLecture 用户不需要低延迟字幕。

所以：

```text
一段声音
↓
只跑 Formal Whisper 一次
```

不要：

```text
一段声音
├→ Preview Whisper / Qwen
└→ Formal Whisper
```

这可以显著降低持续上课时的计算压力。

---

# 13. 自动保存与崩溃恢复

这是 V1 的 P0。

每一个“正式 Whisper segment”产生后：

1. 立即写 SQLite。
2. 再通知 UI。
3. UI 不作为唯一数据源。

禁止：

```text
90 分钟文字全部在 React state
↓
最后一次性保存
```

如果电脑蓝屏、Electron 崩溃或程序被关：

用户最多丢失当前正在 Whisper 处理的短窗口，不应该丢失此前几十分钟内容。

### 启动恢复

启动 LocalLecture 时：

若发现：

```text
started_at 有值
ended_at 为空
```

则显示：

```text
发现上次未正常结束的课程：

计算机网络 第5课
已保存 00:46:21 的逐字稿

[恢复并导出]
[查看已有文字]
[删除记录]
```

V1 如果时间有限，可以至少做“查看并导出已有文字”。

---

# 14. 隐私和离线要求

P0：

1. Whisper 在本机运行。
2. 转录正文不自动上传任何服务器。
3. 不要求 OpenAI API Key。
4. 不要求 Claude API Key。
5. 不要求 DeepSeek API Key。
6. 不要求登录账号。
7. 不持久化课堂原始音频。
8. 所有 transcript 默认只写本机 SQLite / Markdown。

第一次下载 Whisper 模型可以联网。

模型下载完成后：

现实课堂的：

`麦克风 → Whisper → Markdown`

应能断网使用。

B站/学习通视频本身是否联网，与 LocalLecture 的 ASR 是否联网是两回事。

---

# 15. 暂停功能定义

“暂停”不是把程序关掉。

点击暂停：

```text
停止把新音频送入 transcript pipeline
```

恢复：

```text
从当前时间继续
```

Markdown 时间戳应保持课程时间线。

例如：

```text
[00:34:20]
老师讲话

暂停 10 分钟

[00:44:25]
老师继续讲话
```

不要为了删除课间时间而复杂重写时间轴。

V1 保留真实会话时间最简单。

---

# 16. 使用教程——开发完成后的普通用户

## 16.1 第一次使用

第一次必须联网，因为需要：
- 安装程序依赖；
- 下载 Whisper Small 模型。

模型下载完成后，之后的识别不需要按次购买 Token。

---

## 16.2 B站 / 学习通

### 第 1 步：打开 LocalLecture

双击应用。

### 第 2 步：填写课程名称

例如：

`数据库原理 第8课`

### 第 3 步：声音来源选择

选：

`电脑系统声音`

解释：

LocalLecture 抓的是 Windows 正在播放的声音。

你可以：
- 用电脑扬声器；
- 戴耳机；

只要课程声音走 Windows 默认播放设备即可。

### 第 4 步：开始转录

先点：

`开始转录`

看到：

`● 正在转录`

再开始播放课程。

### 第 5 步：确认一次

看“最近识别”是否出现老师讲话。

如果 20～30 秒都没有文字：
1. 先不要继续上整堂课；
2. 检查声音来源；
3. 检查默认播放设备；
4. 使用音频设备诊断。

### 第 6 步：正常看课

LocalLecture 放后台即可。

不需要一直盯字幕。

### 第 7 步：下课

点击：

`结束课程`

等待最后一个 Whisper 音频窗口处理完。

### 第 8 步：打开逐字稿

得到：

`数据库原理_第8课_2026-09-10.md`

---

# 17. 使用教程——现实课堂

### 第 1 步

将电脑放在尽量靠近老师的位置。

### 第 2 步

声音来源选：

`麦克风`

### 第 3 步

确认 Windows：

设置 → 隐私和安全性 → 麦克风

允许桌面应用使用麦克风。

### 第 4 步

点击：

`开始转录`

### 第 5 步

说一句测试话：

“这是 LocalLecture 麦克风测试。”

确认最近识别有文字。

### 第 6 步

开始正式上课。

### 第 7 步

课间可以点暂停。

### 第 8 步

下课点结束，生成 Markdown。

---

# 18. 怎么把逐字稿交给 ChatGPT 网页版

LocalLecture 不负责总结。

下课后：

1. 打开 ChatGPT 网页版。
2. 上传 `.md`。
3. 使用例如以下指令：

```text
这是我的课堂完整逐字稿。

请不要遗漏老师明确强调的内容。

帮我整理为：
1. 课程标题
2. 章节结构
3. 老师重要原话
4. 核心知识点
5. 概念解释
6. 老师举例
7. 重点
8. 难点
9. 易错点
10. 公式
11. 代码
12. 复习题
13. 本节总结

如果逐字稿中出现程序代码、API、函数、命令或算法，
请单独提取，并以零基础方式解释：
- 这段代码是什么；
- 每一部分干什么；
- 输入是什么；
- 输出是什么；
- 怎么运行；
- 给一个具体例子。

如果某段转录明显可能识别错误，不要擅自编造，请标注“疑似转录错误”。
```

---

# 19. 开发顺序——Codex 必须按阶段执行

这是为了减少 Bug。

## 阶段 0：建立基线

Codex 只能：
- clone；
- 安装；
- 运行原版；
- 跑测试。

不修改源码。

验收：
- 原版可以启动；
- 麦克风可用；
- Windows 系统声音可用；
- Whisper 可以转中文；
- 原版可以导出 transcript。

如果阶段 0 都没通过，不允许进入阶段 1。

---

## 阶段 1：Transcript-only 后端

只改：
- 配置；
- `session/manager.py`；
- 必要的 schema。

目标：
- formal Whisper 工作；
- preview off；
- translation off；
- summary off；
- diarization off。

暂时不改 UI。

验收：
- e2e 转录通过；
- CPU 使用明显比双 ASR 路径更合理；
- 转录仍写数据库。

提交一次 Git：

`feat: add transcript-only session mode`

---

## 阶段 2：LocalLecture Markdown 导出

只改：
- `exporter.py`
- 必要 schema / API

目标：
- 导出单一课堂 Markdown；
- 文件名合法；
- UTF-8；
- 有时间戳。

提交：

`feat: add LocalLecture transcript export`

---

## 阶段 3：课程名称与元数据

只改：
- schema；
- storage；
- API；
- 对应测试。

不要同时改 UI。

提交：

`feat: add course metadata`

---

## 阶段 4：新建 LocalLecture UI

新建：
- `LocalLectureApp.tsx`
- LocalLecture components
- CSS

尽量复用：
- `backendApi.ts`
- `useSessionSocket.ts`

不要删除原 App。

提交：

`feat: add LocalLecture desktop UI`

---

## 阶段 5：崩溃恢复

实现：
- 未结束课程检测；
- 已保存 segment 的恢复导出。

提交：

`feat: recover interrupted transcript sessions`

---

## 阶段 6：打包和完整验收

真实跑：
- B站 30 分钟；
- 学习通 30 分钟；
- 麦克风 30 分钟；
- 暂停/恢复；
- 耳机；
- 程序异常退出；
- Markdown 导出。

通过后再考虑清理 MeetingBro 原 UI 和无关代码。

---

# 20. Codex 禁止事项

把下面一段原样给 Codex：

```text
禁止事项：

1. 不允许在没有运行原项目的情况下直接重写。
2. 不允许一次性重构整个 MeetingBro。
3. 不允许把 Buzz 源码直接拼接进 MeetingBro。
4. 不允许更换 Electron/React/FastAPI 技术栈。
5. 不允许新增 OpenAI、Claude、DeepSeek、Groq API。
6. 不允许新增 Ollama。
7. 不允许保存完整课堂 WAV/MP3/M4A。
8. 不允许为了 UI 修改 audio/loopback.py。
9. 不允许删除现有测试后声称测试通过。
10. 不允许只检查“能编译”，必须真实跑系统声音和麦克风。
11. 不允许把所有 transcript 只存在前端内存。
12. 不允许一次修改几十个无关文件。
13. 每个阶段先测试再 Git commit。
14. 遇到现有 API/类型不确定时，先搜索调用方，不得猜字段名。
15. 修改 schemas.py 时必须同步检查 frontend/src/types.ts。
16. 修改后端接口时必须搜索所有前端调用点。
17. 修改 SessionManager 时必须保留 stop/finalize/queue 清理逻辑。
18. V1 不追求 Intel Arc/NPU 加速，不引入第二套 ASR 推理框架。
```

---

# 21. 可以直接发给 Codex 的总提示词

```text
你现在要基于 MeetingBro 开源项目开发 LocalLecture V1.0。

项目目标：
一个 Windows 本地课堂语音转文字工具。

核心需求：
- B站/学习通/浏览器：捕获 Windows 系统声音。
- 现实课堂：捕获麦克风。
- 本地 faster-whisper。
- 中文课程为主。
- Whisper Small。
- 优先 CPU int8。
- 上课时持续转录。
- 不需要实时低延迟字幕。
- 不做 AI 总结。
- 不做翻译。
- 不做说话人识别。
- 不调用 OpenAI/Claude/DeepSeek/Groq。
- 不要求 API Key。
- 不保存原始课堂音频。
- 正式 transcript segment 产生后立即写 SQLite。
- 下课后导出一个 Markdown 完整逐字稿。
- Markdown 必须有时间戳。
- 支持课程标题。
- 支持暂停/继续/结束。
- 支持异常退出后恢复已经保存的文字。

在任何修改前，先完整阅读：
README.md
README.zh-CN.md
docs/architecture.md
docs/platform-support.md
docs/troubleshooting.md

然后重点阅读：
app/backend/meetingbro/audio/capture.py
app/backend/meetingbro/audio/loopback.py
app/backend/meetingbro/audio/devices.py
app/backend/meetingbro/audio/vad.py
app/backend/meetingbro/audio/enhancement.py
app/backend/meetingbro/asr/base.py
app/backend/meetingbro/asr/faster_whisper_adapter.py
app/backend/meetingbro/session/manager.py
app/backend/meetingbro/storage/db.py
app/backend/meetingbro/exporter.py
app/backend/meetingbro/schemas.py
app/backend/meetingbro/main.py
app/frontend/src/types.ts
app/frontend/src/session/useSessionSocket.ts
app/frontend/src/system/backendApi.ts
app/frontend/electron/main.cjs
app/frontend/electron/backend.cjs
app/backend/pyproject.toml
app/frontend/package.json

先不要修改。

第一阶段必须先建立 baseline：
1. 安装依赖。
2. 启动原版。
3. 运行 dep_check。
4. 运行 list_audio_devices。
5. 运行 e2e_loopback。
6. 验证麦克风。
7. 验证中文 Whisper。
8. 跑已有 tests。
9. 记录通过/失败项。

只有 baseline 通过后才开始修改。

实现时严格按小阶段：
A. transcript-only backend
B. LocalLecture markdown export
C. course metadata
D. 新 LocalLecture UI
E. crash recovery
F. full E2E

不要把原 App.tsx 大规模边删边改。
优先新建：
app/frontend/src/locallecture/LocalLectureApp.tsx
以及拆分组件，再在 main.tsx 做最小入口切换。

不要重写 SystemAudioLoopbackSource。
优先复用 MeetingBro 现有 Windows WASAPI loopback。

不要重写 MicrophoneSource。
优先复用现有 sounddevice 麦克风链路。

SessionManager 是高风险文件。
不要整体重写。
只通过显式 transcript-only 模式关闭：
preview ASR
summarization
translation
diarization

保留：
audio capture
VAD
formal Whisper
SQLite
transcript segment
WebSocket state
stop/finalize
export

每完成一个阶段：
1. 列出修改文件。
2. 解释每个文件为什么修改。
3. 运行对应测试。
4. 给出测试结果。
5. git diff 自查。
6. 再提交 commit。
如果测试失败，不进入下一阶段。

最终必须真实验收：
- B站系统声音至少 30 分钟；
- 学习通系统声音至少 30 分钟；
- 麦克风至少 30 分钟；
- 戴耳机；
- 暂停继续；
- 正常结束；
- 异常关闭恢复；
- 输出只有需要的 Markdown，不持久化课堂录音。

不要擅自扩展功能。
```

---

# 22. 开发环境第一次安装教程

以下以 MeetingBro 原仓库为例。

## 22.1 安装 Git

用于下载代码和保存每次修改版本。

验证：

```powershell
git --version
```

看到版本号就说明可用。

---

## 22.2 安装 Python 3.12+

验证：

```powershell
python --version
```

目的：

后端、Whisper、音频处理都运行在 Python。

---

## 22.3 安装 Node.js

验证：

```powershell
node --version
npm --version
```

目的：

Electron + React 前端需要 Node.js。

---

## 22.4 下载仓库

PowerShell：

```powershell
cd D:\
git clone https://github.com/armpro24-blip/MeetingBro.git LocalLecture
cd D:\LocalLecture
```

解释：

`cd D:\`
进入 D 盘根目录。

`git clone ... LocalLecture`
把 MeetingBro 源码下载到一个叫 `LocalLecture` 的本地文件夹。

`cd D:\LocalLecture`
进入项目。

---

## 22.5 建自己的开发分支

```powershell
git checkout -b locallecture-v1
```

作用：

不要直接在原来的 `main` 分支乱改。

以后出问题可以回退。

---

## 22.6 安装

先按上游原项目方式运行：

```powershell
.\scripts\install.ps1
```

作用：
- 检查环境；
- 创建 Python 虚拟环境；
- 安装 Python 依赖；
- 安装前端 npm 依赖。

第一次可能比较久。

---

## 22.7 启动

```powershell
.\scripts\start.ps1
```

作用：

启动：
- Python backend
- React/Vite
- Electron 桌面程序

---

## 22.8 依赖检查

```powershell
python .\scripts\dep_check.py
```

如果这个 Python 不是项目虚拟环境，需要按上游脚本激活方式执行。

---

## 22.9 列声音设备

```powershell
python .\scripts\list_audio_devices.py
```

用途：

确认：
- 麦克风存在；
- Windows 播放设备存在；
- Loopback 可以找到。

---

# 23. 给 Codex 的验收标准

V1.0 不能以“代码写完”为完成。

必须满足：

### 系统声音

播放一个 B站中文视频。

软件开启“系统声音”。

即使：
- 麦克风静音；
- 用户戴耳机；

仍然能产生转录文字。

### 麦克风

关闭 B站。

选择麦克风。

用户对电脑说话。

能产生转录。

### 不联网 API

断开互联网后，已下载好 Whisper 模型的情况下：

现实课堂麦克风转录仍然工作。

### 不保存录音

完成会话后检查输出和缓存：

不应有 LocalLecture 产生的完整课堂音频。

### 崩溃保护

转录 10 分钟后强制关闭。

重新打开。

前面已确认写入 SQLite 的文字能够恢复/导出。

### Markdown

文件：
- UTF-8；
- 中文正常；
- 时间戳正确；
- 内容顺序正确；
- 没有 summary；
- 没有 AI 编造文本。

---

# 24. V1.1 / V2.0 暂缓需求

只有 V1 稳定后才考虑：

### V1.1
- 专业词汇表
- 课程词典
- Whisper initial prompt
- 更好的现实课堂降噪
- 自动章节书签
- 快捷键
- 托盘运行
- Whisper.cpp Vulkan / Intel Arc 性能实验

### V2.0
- 课堂 PPT OCR
- 同步课程幻灯片
- ChatGPT 一键整理
- 本地 Qwen 总结
- 多课程知识库
- 搜索所有历史课堂
- 代码块自动识别

V1 不做这些。

---

# 25. 一句话技术架构

```text
B站 / 学习通 ── Windows WASAPI Loopback ┐
                                       ├→ VAD → Whisper Small CPU int8
现实课堂 ─────── sounddevice 麦克风 ────┘
                                                ↓
                                        Transcript Segment
                                                ↓
                                             SQLite
                                                ↓
                                          Electron UI
                                                ↓
                                      结束课程时 Markdown
```

LocalLecture 的核心原则：

> 音频是临时数据，文字才是长期数据。

以及：

> 先复用 MeetingBro 已经稳定的声音和 Whisper 链路，只删掉不需要的计算，不重新发明整套架构。

---

# 26. 上游项目与二次开发说明

推荐上游：

MeetingBro  
https://github.com/armpro24-blip/MeetingBro

MeetingBro 当前采用 MIT License。

二次开发可以修改和分发，但发布 LocalLecture 时应保留原 MIT License 要求的版权和许可声明。

建议仓库保留：

`LICENSE`

并新增：

`NOTICE.md`

说明 LocalLecture 基于 MeetingBro 修改。

---

# 27. 最终交付物

Codex 最终应交付：

```text
LocalLecture/
├── app/
│   ├── backend/
│   └── frontend/
├── tests/
├── scripts/
├── docs/
│   ├── LOCALLECTURE_PRD.md
│   └── LOCALLECTURE_USER_GUIDE.md
├── LICENSE
├── NOTICE.md
└── README.md
```

最终用户应能做到：

```text
双击 LocalLecture
↓
输入课程名称
↓
选择系统声音 / 麦克风
↓
点击开始
↓
正常上课
↓
点击结束
↓
得到一个 .md 完整逐字稿
↓
上传 ChatGPT 网页版总结
```

这就是 LocalLecture V1.0 的完整边界。
