# Spec Delta

## Purpose

让用户在现有 Windows 本地课堂转写入口，使用电脑麦克风持续记录现实课堂老师的讲话，获得自动保存、可恢复、带时间戳的 Markdown 逐字稿，并通过独立的真实课堂评测验证采音完整性和识别质量。

## ADDED Requirements

### Requirement: Classroom source selection

专用课堂入口 SHALL 提供系统声音与现实课堂麦克风两种场景，并默认保留系统声音。麦克风场景 SHALL 允许选择默认或指定麦克风。活动课程及麦克风检查期间 SHALL 禁止并发占用输入设备或改变本次设备选择。

#### Scenario: Start an in-person class
- **WHEN** 用户选择现实课堂、指定可用麦克风并开始课程
- **THEN** 系统持续采集该麦克风，并显示本次真实声音来源和识别模型
- **AND** 不采集电脑播放设备的回环声音

#### Scenario: Protect an active session
- **WHEN** 用户在录音、暂停、模型加载、结束收尾或课前麦克风检查期间尝试另开采音任务或更换活动设备
- **THEN** 系统拒绝冲突操作并提示先结束当前任务

#### Scenario: Preserve existing system-audio behavior
- **WHEN** 用户从原启动脚本打开专用入口并使用默认选项
- **THEN** 仍可按原方式启动系统声音课程，旧历史仍可查看、下载和删除

### Requirement: Explicit microphone readiness check

系统 SHALL 提供用户主动触发的 5 秒麦克风检查，显示输入电平及无输入、低音量、削波或设备不可用提示。检查 SHALL 不创建正式课程、不输出识别文字、不保存音频，并在完成、取消或超时后释放设备；检查信息 SHALL 不被描述为识别准确率证明。

#### Scenario: Check before class
- **WHEN** 用户点击检查麦克风并试讲
- **THEN** 系统显示输入电平和检查结果，5 秒采集结束或最迟 10 秒超时后释放设备
- **AND** 不向历史列表添加课程

#### Scenario: Missing or unavailable microphone
- **WHEN** 选定麦克风不存在、被禁用、无输入声道或无法打开
- **THEN** 系统报告设备检查失败并提供检查 Windows 权限和设备的操作提示
- **AND** 不静默改用另一麦克风或系统声音，也不把不确定的驱动或权限问题认定为根因

### Requirement: Visible live input health

麦克风课程 SHALL 在运行中显示输入电平、待处理音频时长及采集状态。连续 10 秒低输入 SHALL 提醒检查距离或静音，但不得自动结束课程。缓冲溢出、音频丢块和采集失败 SHALL 明确告警，发生完整性问题的课程在历史和导出中 SHALL 保留提示。

#### Scenario: Silence or quiet input
- **WHEN** 运行中的麦克风连续 10 秒低于配置的低输入阈值
- **THEN** 页面提醒检查老师距离、麦克风和音量，继续采集并允许自然课堂停顿

#### Scenario: Capture failure during class
- **WHEN** 麦克风采集报告溢出、丢块或异常终止
- **THEN** 页面显示可见告警；终止时退出运行状态并保存已确认文字
- **AND** 历史和 Markdown 保留可能漏录的提示，不显示“完整成功”，不自动切换设备

### Requirement: Continuous session controls and final drain

系统 SHALL 支持开始、暂停、继续和结束麦克风课程。采集真正就绪前 SHALL 显示准备状态。暂停期间的输入 SHALL 不进入识别和保存链路，继续后不得重复已保存内容；用户正常结束时 SHALL 处理已采集的尾段和待识别音频后再标记完成并释放资源。

#### Scenario: Pause and resume
- **WHEN** 用户暂停后继续一节麦克风课程
- **THEN** 暂停期间讲话不进入逐字稿，继续后新增段落按有效采音时间递增，且不重复暂停前内容

#### Scenario: End with pending audio
- **WHEN** 用户在仍有积压或不足一个识别窗口的尾段时点击结束
- **THEN** 页面显示正在保存，已采集尾段完成识别落库和导出后才显示完成及资源释放

### Requirement: Durable transcript and recovery

确认的麦克风转写文字 SHALL 自动保存到现有本地历史，支持 UTF-8 Markdown 下载、单条删除和重启恢复。导出 SHALL 包含真实来源、模型、课程信息及有序段落时间戳。强退恢复 SHALL 明示只恢复已保存文字，内存尾段可能缺失，不得补写未识别的讲话。

#### Scenario: Recover after interruption
- **WHEN** 已转写十分钟的程序被强退并重新打开
- **THEN** 可查到此前已保存文字及中断提示，页面明确尚未处理的尾段可能缺失
- **AND** 只预览但尚未保存的文字不得冒充已恢复正文

#### Scenario: Export and delete a completed class
- **WHEN** 用户下载一节已结束的麦克风课程后删除该课程
- **THEN** 下载文件包含全部已保存正文与来源模型信息，删除只清除对应数据库文字和 Markdown
- **AND** 其他课程保持可用，并提示旧备份 ZIP 不随单条删除改变

### Requirement: Free offline processing and audio lifecycle

完成模型及运行依赖准备后，麦克风转写 SHALL 无需联网、API Key、订阅或按量付费。系统 SHALL 不上传课堂音频或正文，不调用总结或翻译服务，不保存整堂课录音。识别所需短窗临时音频 SHALL 在处理结束后删除；重启时 SHALL 清理本应用上次异常退出遗留的临时音频。

#### Scenario: Transcribe without a network
- **WHEN** 目标电脑已准备模型与依赖且用户断开网络开始麦克风课程
- **THEN** 可以完成采音、识别、保存与导出，不要求付费凭据

#### Scenario: Missing local assets
- **WHEN** 离线启动所需模型或运行文件缺失
- **THEN** 系统说明缺失内容并拒绝误报就绪，不切换云端服务或静默下载

#### Scenario: Temporary audio cleanup
- **WHEN** 课程正常结束或在异常退出后重启
- **THEN** 本应用已处理或遗留的短窗临时音频被清理，其他文件保持不变
- **AND** 没有生成整堂课原始录音文件

### Requirement: Independent classroom accuracy acceptance

正式交付 SHALL 使用不少于 10 分钟、覆盖实际摆放距离与典型噪声的真实课堂麦克风音频及对应人工逐字稿，独立报告字错率、整句漏录和专业术语错误。系统声音分数、文件链路测试或公开模型成绩 SHALL 不代替该验收；不得承诺任意课堂零错字。

#### Scenario: Score representative classroom audio
- **WHEN** 对真实麦克风样本完成识别和人工核对
- **THEN** 以统一的全半角、大小写、标点及空白归一化规则计算字错率，并独立报告麦克风分数
- **AND** 报告样本时长、距离、噪声、模型、漏句数、术语错误数及人工校对依据

### Requirement: Measurable quality gate

本变更拟定的交付门槛 SHALL 为麦克风样本字错率不高于 10%，且不高于同样本现有麦克风基线的 90%；基线为零时要求候选也为零。整句漏录和专业术语错误次数 SHALL 不高于基线。上述门槛在方案确认后作为实现验收标准；未通过时 SHALL 报告待验收或不达标，不以软件功能可运行代替识别达标。

#### Scenario: Candidate passes all quality measures
- **WHEN** 候选模型满足绝对字错率、相对基线、漏句及术语四项门槛
- **THEN** 才将该模型的麦克风样本识别质量标为通过
- **AND** 仍须完成独立的离线、长时和故障验收才能声明整体交付完成

#### Scenario: Missing samples or no passing model
- **WHEN** 缺少人工校对样本，或现有本地候选没有全部满足门槛
- **THEN** 保留现有可用链路，报告缺失证据或失败指标，并与用户讨论后续处理
- **AND** 不虚报准确率，不擅自添加付费服务、新硬件、其他引擎或 AI 润色

### Requirement: Real microphone long-session acceptance

正式交付 SHALL 在目标电脑实际麦克风上完成连续 60 分钟采音，无采集异常或丢块，正常结束后 10 分钟内完成尾段识别及 Markdown 导出。测试 SHALL 记录采集时长、丢块和溢出计数、积压峰值、结束耗时与资源释放；文件回放不能代替真实设备测试。

#### Scenario: Complete an hour-long classroom session
- **WHEN** 在目标电脑真实麦克风上运行满 60 分钟并点击结束
- **THEN** 在 10 分钟内完成导出，正文段落有序、设备与识别进程释放，记录显示无采集异常、溢出或丢块

#### Scenario: Long test fails
- **WHEN** 采集提前终止、出现丢块或结束超时
- **THEN** 记录实际结果并将长时验收标为未通过，不用短样本或系统声音成绩覆盖该结论
