import type { BackendState } from "../meetingbro-bridge";

interface BackendGateProps {
  state: BackendState;
  detail: string | null;
  logTail: string[];
  onRetry: () => void;
  onOpenLog: () => void;
}

const TITLES: Partial<Record<BackendState, string>> = {
  locating: "正在启动 MeetingBro…",
  starting: "正在启动 MeetingBro…",
  "downloading-model": "正在准备语音识别模型",
  failed: "MeetingBro 启动失败",
  stopped: "后端已停止",
};

const SUBTITLES: Partial<Record<BackendState, string>> = {
  "downloading-model": "首次运行需要下载语音模型（约 460 MB），可能需要几分钟。",
};

// Full-screen overlay shown until the backend is ready, so a non-technical user
// never faces a silent dead connection. Returns null when ready (App renders).
export function BackendGate({ state, detail, logTail, onRetry, onOpenLog }: BackendGateProps) {
  const isError = state === "failed" || state === "stopped";
  const isWorking = state === "locating" || state === "starting" || state === "downloading-model";
  const title = TITLES[state] ?? "正在连接…";
  const subtitle = SUBTITLES[state];

  return (
    <div className="backend-gate" role="alertdialog" aria-busy={isWorking} aria-label={title}>
      <div className="backend-gate__card">
        {isWorking && <div className="backend-gate__spinner" aria-hidden="true" />}
        {isError && <div className="backend-gate__icon" aria-hidden="true">⚠️</div>}
        <h1 className="backend-gate__title">{title}</h1>
        {subtitle && <p className="backend-gate__subtitle">{subtitle}</p>}
        {detail && <p className="backend-gate__detail">{detail}</p>}

        {isError && (
          <div className="backend-gate__actions">
            <button type="button" className="backend-gate__btn backend-gate__btn--primary" onClick={onRetry}>
              重试
            </button>
            <button type="button" className="backend-gate__btn" onClick={onOpenLog}>
              查看日志
            </button>
          </div>
        )}

        {isError && logTail.length > 0 && (
          <pre className="backend-gate__log">{logTail.slice(-12).join("\n")}</pre>
        )}
      </div>
    </div>
  );
}
