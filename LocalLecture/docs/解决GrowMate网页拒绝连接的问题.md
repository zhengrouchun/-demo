# 解决 GrowMate 网页拒绝连接的问题

日期：2026-10-02。

## 问题与原因

浏览器访问 `http://127.0.0.1:8876/` 显示 `ERR_CONNECTION_REFUSED`。检查发现 8876 端口没有程序监听，服务日志显示上次验证调用了 `/api/shutdown` 并正常退出。当前网页构建存在，但本地服务没有运行；只访问地址不会自动启动它。

## 解决流程与方法

1. 用 `Get-NetTCPConnection -LocalPort 8876 -State Listen` 检查服务是否监听，结果为空。
2. 阅读 `data/growmate-web.err.log` 的生命周期日志，以及 `growmate-web.log` 中的 `/api/shutdown` 请求，确认是正常退出，没有把它当成网页构建错误。
3. 阅读 `scripts/start-growmate.ps1` 与外层 `启动GrowMate网页版.cmd`，确认地址、端口、虚拟环境与前端位置。
4. 用 `Start-Process powershell.exe ... -WindowStyle Hidden` 运行现有启动脚本并加 `-NoBrowser`，保持后台服务运行，避免另开浏览器。
5. 访问 `/health`、首页和 `/api/state`，确认应用名 GrowMate、首页 HTTP 200、录音闲置且未加载识别模型。
6. 新增 `scripts/stop-growmate.ps1` 和外层 `停止GrowMate网页版.cmd`。先识别 GrowMate，再调用退出接口并等待服务进程退出，不强行杀进程，以便后台运行时也能正常停止。
7. 更新 `GrowMate网页版操作手册.md` 的启动故障与退出步骤。

## 涉及文件与使用位置

- `scripts/start-growmate.ps1`：已有健康检查、启动 Python 服务和保持运行的循环。
- `data/growmate-web.err.log`、`growmate-web.log`：退出状态和触发退出的接口请求。
- `app/backend/meetingbro/growmate/web.py`：`/health`、静态网页挂载、`/api/shutdown` 以及生命周期结束时保存/关闭识别的流程。
- `scripts/stop-growmate.ps1`：新建正常停止入口，识别应用并等待退出。
- `停止GrowMate网页版.cmd`：给用户双击使用的入口。
- 外层 `GrowMate网页版操作手册.md`：补充后台停止与拒绝连接的处理方法。

## 实际使用的指令

```powershell
Get-NetTCPConnection -LocalPort 8876 -State Listen -ErrorAction SilentlyContinue
Get-Content data/growmate-web.err.log -Tail 40
Get-Content data/growmate-web.log -Tail 20
Invoke-RestMethod -Uri 'http://127.0.0.1:8876/health'
Invoke-WebRequest -Uri 'http://127.0.0.1:8876/' -UseBasicParsing
```

启动使用 `Start-Process`、`-File scripts/start-growmate.ps1`、`-NoBrowser` 和 `-WindowStyle Hidden`。停止使用 `Invoke-RestMethod -Method Post` 请求 `/api/shutdown`，带 `X-GrowMate-Request: 1` 请求头；通过进程对象等待退出。

## 结果与使用方式

服务启动后健康检查成功，首页返回 200。用户刷新现有页面即可访问。日后电脑重启或正常停止后，先双击“启动GrowMate网页版.cmd”；退出时先保存，再双击“一键停止”或在启动窗口按 Ctrl+C。后台运行不表示录音已开始，识别模型仍按用户开始转写时加载。
