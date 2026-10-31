# GrowMate 本地网页版

在项目外层目录双击 `启动GrowMate网页版.cmd`，启动后浏览器打开 `http://127.0.0.1:8876`。

保留启动窗口；实时转文字位于 **记录 → 实时转写**。结束转写并看到资源已释放后，在启动窗口按 Ctrl+C，或双击外层的 `停止GrowMate网页版.cmd` 关闭服务。

完整说明见 [GrowMate网页版操作手册](../GrowMate网页版操作手册.md)。下方保留原 MeetingBro 桌面版的启动说明。

# Start MeetingBro

**Start the backend first, then the frontend.**

## Backend

```bash
conda activate MeetingBro
cd app/backend
meetingbro-backend
```

## Frontend (new terminal)

```bash
cd app/frontend
npm run dev
```

The Electron window will open automatically.

---

# 启动 MeetingBro

**先开后端，再开前端。**

## 后端

```bash
conda activate MeetingBro
cd app/backend
meetingbro-backend
```

## 前端（新终端）

```bash
cd app/frontend
npm run dev
```

Electron 窗口会自动弹出。
