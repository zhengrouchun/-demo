import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { ExportMeetingResponse, SummarySnapshot, TranscriptSegment } from "./types";
import { useSessionSocket } from "./session/useSessionSocket";
import type { ExportMeetingInput } from "./session/useSessionSocket";
import { useBackendStatus } from "./system/useBackendStatus";
import { BackendGate } from "./components/BackendGate";
import { SettingsModal } from "./components/SettingsModal";
import { HistoryModal } from "./components/HistoryModal";
import { fetchAudioDevices } from "./system/backendApi";
import type { AudioDevices } from "./system/backendApi";

const VOCABULARY_STORAGE_KEY = "meetingbro.vocabulary";
const AUDIO_DEVICE_KEY = "meetingbro.audioDevice";
const LOOPBACK_DEVICE_KEY = "meetingbro.loopbackDevice";
const PREVIEW_HANDOFF_TOLERANCE_SECONDS = 0.35;
const FORMAL_SEGMENT_STAGGER_MS = 75;
const FORMAL_CELL_STAGGER_MS = 55;
const PREVIEW_ROW_STAGGER_MS = 45;
const PREVIEW_CELL_STAGGER_MS = 45;

type StaggerStyle = CSSProperties & {
  "--segment-delay"?: string;
  "--segment-text-delay"?: string;
  "--preview-status-delay"?: string;
  "--preview-text-delay"?: string;
};

function hasPreviewHandoff(segment: TranscriptSegment, previews: readonly TranscriptSegment[]): boolean {
  return previews.some((preview) => (
    preview.end_time <= segment.end_time + PREVIEW_HANDOFF_TOLERANCE_SECONDS &&
    preview.end_time >= segment.start_time - PREVIEW_HANDOFF_TOLERANCE_SECONDS
  ));
}


function formatRange(start: number, end: number): string {
  const fmt = (s: number) => {
    const m = Math.floor(s / 60).toString().padStart(2, "0");
    const sec = Math.floor(s % 60).toString().padStart(2, "0");
    return `${m}:${sec}`;
  };
  return `${fmt(start)} – ${fmt(end)}`;
}

function formatApproxClock(iso: string | null, seconds: number): string {
  if (!iso) return formatRange(seconds, seconds).slice(0, 5);
  const dt = new Date(new Date(iso).getTime() + seconds * 1000);
  return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatApproxClockRange(iso: string | null, start: number, end: number): string {
  return `${formatApproxClock(iso, start)} – ${formatApproxClock(iso, end)}`;
}

function formatCreatedAt(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatLagSeconds(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
}

function getDelayTone(seconds: number | null): "ok" | "warn" | "danger" | "unknown" {
  if (seconds == null) return "unknown";
  if (seconds < 1.2) return "ok";
  if (seconds < 2.8) return "warn";
  return "danger";
}

type AdviceSeverity = "ok" | "warn" | "danger";

interface SystemAdvice {
  severity: AdviceSeverity;
  title: string;
  detail: string;
  action?: string;
}

function getConfidenceTone(confidence: number): "stable" | "soft" | "uncertain" {
  if (confidence < 0.48) return "uncertain";
  if (confidence < 0.67) return "soft";
  return "stable";
}

function getConfidenceLabel(confidence: number): string | null {
  const tone = getConfidenceTone(confidence);
  if (tone === "uncertain") return "待核对";
  if (tone === "soft") return "低置信度";
  return null;
}

function isSystemHealthOnlyMessage(message: string | null): boolean {
  if (!message) return false;
  const normalized = message.toLowerCase();
  return (
    normalized.includes("asr is close to falling behind") ||
    normalized.includes("temporarily skipping retry") ||
    normalized.includes("asr has been processing") ||
    normalized.includes("audio input is buffered") ||
    normalized.includes("backlog")
  );
}

function formatSessionError(code: string | null, message: string): string {
  if (code === "audio_all_silent") {
    return "持续未检测到声音。网课请确认正在播放，且 Windows 声音输出设备与上方选择的设备一致；课堂请检查麦克风选择和权限。录音不会在此时自动停止。";
  }
  if (code === "audio_input_queue_backlog" || code === "audio_input_queue_dropped") {
    return "语音识别速度暂时跟不上录音。请继续录制，停止后等待“正在整理逐字稿”完成；如仍持续积压，可改用更小的 Whisper 模型。";
  }
  return message;
}

function formatElapsedSeconds(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60).toString().padStart(2, "0");
  const s = Math.floor(total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function formatGain(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}x`;
}

function formatRtf(value: number | null | undefined): string {
  if (value == null) return "???";
  return `${value.toFixed(2)}x`;
}

function getGainTone(
  effectiveMicrophoneGain: number | null | undefined,
  baseMicrophoneGain: number | null | undefined,
  activeSource: string | null | undefined,
): "ok" | "warn" | "danger" | "unknown" {
  if (activeSource !== "mixed") return "unknown";
  if (effectiveMicrophoneGain == null || baseMicrophoneGain == null || baseMicrophoneGain <= 0) {
    return "unknown";
  }
  const boostRatio = effectiveMicrophoneGain / baseMicrophoneGain;
  if (boostRatio < 1.15) return "ok";
  if (boostRatio < 1.45) return "warn";
  return "danger";
}

function formatSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "mic":
      return "麦克风";
    case "loopback":
    case "system":
      return "系统声音";
    case "mixed":
      return "系统声音 + 麦克风";
    case "sample":
      return "示例音频";
    default:
      return source ?? "—";
  }
}

function formatLanguageLabel(language: "zh" | "en" | "de" | null | undefined): string {
  switch (language) {
    case "zh":
      return "中文";
    case "en":
      return "英语";
    case "de":
      return "德语";
    default:
      return "关闭";
  }
}

function formatRuntimeProfileLabel(profile: string | null | undefined): string {
  switch (profile) {
    case "summary_only":
      return "仅生成摘要";
    case "performance":
    case "robust":
      return "高性能";
    case "balanced":
      return "均衡";
    default:
      return profile ?? "均衡";
  }
}

function defaultExportFolderName(): string {
  const now = new Date();
  const pad = (value: number, width = 2) => value.toString().padStart(width, "0");
  const timestamp = [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
  ].join("-") + "_" + [
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join("-") + `-${pad(now.getMilliseconds(), 3)}`;
  return `${timestamp}_meetingbro`;
}

function parseSnapshotList(content: string): Array<Record<string, unknown>> {
  try {
    const value = JSON.parse(content);
    return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object") : [];
  } catch {
    return [];
  }
}

function getMixedGainHint(
  tone: "ok" | "warn" | "danger" | "unknown",
  activeSource: string | null | undefined,
): string {
  if (activeSource !== "mixed") {
    return "选择“系统声音 + 麦克风”后显示混合音量诊断";
  }
  if (tone === "danger") {
    return "麦克风音量偏低，可考虑调高 MEETINGBRO_MIXED_MIC_GAIN";
  }
  if (tone === "warn") {
    return "正在补偿麦克风音量，请留意人声是否清晰";
  }
  if (tone === "ok") {
    return "麦克风与系统声音音量较均衡";
  }
  return "等待混合音量数据";
}

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 120;
}

interface SummaryPanelProps {
  title: string;
  subtitle: string;
  snapshot: SummarySnapshot | undefined;
  history: SummarySnapshot[];
  sessionStartedAt: string | null;
  accent: string;
  className?: string;
  compact?: boolean;
  onSaveToNotes: (snapshot: SummarySnapshot) => Promise<void>;
  onRefresh?: () => void;
  refreshDisabled?: boolean;
  refreshBusy?: boolean;
}

function SummaryPanel({ title, subtitle, snapshot, history, sessionStartedAt, accent, className, compact = false, onSaveToNotes, onRefresh, refreshDisabled = false, refreshBusy = false }: SummaryPanelProps) {
  const displayedHistory = history.length > 0 ? history : snapshot ? [snapshot] : [];
  const latestSnapshot = displayedHistory.at(-1) ?? snapshot;
  const range = latestSnapshot
    ? formatApproxClockRange(sessionStartedAt, latestSnapshot.time_start, latestSnapshot.time_end)
    : "—";
  const relativeRange = latestSnapshot
    ? formatRange(latestSnapshot.time_start, latestSnapshot.time_end)
    : "—";
  const createdAt = latestSnapshot
    ? new Date(latestSnapshot.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";

  const bodyRef = useRef<HTMLDivElement>(null);
  const autoFollowRef = useRef(true);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (autoFollowRef.current && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [displayedHistory.length, latestSnapshot?.id]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const onCopy = async () => {
    if (!latestSnapshot) return;
    await navigator.clipboard.writeText(latestSnapshot.content);
  };
  const onExpand = () => {
    if (!latestSnapshot) return;
    setExpanded(true);
  };
  const onSave = async () => {
    if (!latestSnapshot) return;
    await onSaveToNotes(latestSnapshot);
  };

  const bodyJSX = (
    <div
      ref={bodyRef}
      className="panel-body summary-history"
      onScroll={(e) => {
        autoFollowRef.current = isNearBottom(e.currentTarget);
      }}
    >
      {displayedHistory.length === 0 ? (
        "等待第一份摘要…"
      ) : (
        displayedHistory.map((item, idx) => {
          const itemRange = formatApproxClockRange(sessionStartedAt, item.time_start, item.time_end);
          const itemRelativeRange = formatRange(item.time_start, item.time_end);
          const itemCreatedAt = new Date(item.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          const isLatest = idx === displayedHistory.length - 1;
          return (
            <article key={item.id} className={`summary-history-item ${isLatest ? "latest" : ""}`.trim()}>
              <div className="summary-history-meta">
                <span>{itemRange}</span>
                <span>{itemRelativeRange}</span>
                <span>{itemCreatedAt}</span>
              </div>
              <div>{item.content}</div>
            </article>
          );
        })
      )}
    </div>
  );

  const footerJSX = (
    <footer>
      <button onClick={onRefresh} disabled={!onRefresh || refreshDisabled} className={refreshBusy ? "button-busy" : ""} aria-busy={refreshBusy}>
        {refreshBusy ? "更新中…" : "更新"}
      </button>
      <button onClick={onCopy} disabled={!latestSnapshot}>复制最新</button>
      <button onClick={onExpand} disabled={!latestSnapshot}>展开</button>
      <button onClick={onSave} disabled={!latestSnapshot}>保存最新内容</button>
    </footer>
  );

  const modalJSX = expanded ? (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={`${title} history`} onClick={() => setExpanded(false)}>
      <div className="modal modal--summary" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h2>{title} <span className="modal__range">{range}</span></h2>
          <button type="button" className="modal__close" onClick={() => setExpanded(false)} aria-label="关闭">×</button>
        </div>
        <div className="modal__body summary-history">
          {displayedHistory.length === 0 ? (
            "暂无摘要。"
          ) : (
            displayedHistory.map((item, idx) => (
              <article key={item.id} className="summary-history-item">
                <div className="summary-history-meta">
                  <span>#{idx + 1}</span>
                  <span>{formatApproxClockRange(sessionStartedAt, item.time_start, item.time_end)}</span>
                  <span>{formatRange(item.time_start, item.time_end)}</span>
                </div>
                <div>{item.content}</div>
              </article>
            ))
          )}
        </div>
      </div>
    </div>
  ) : null;

  if (compact) {
    return (
      <div className="workspace-tab-panel">
        <div className="workspace-tab-meta">
          <span className="summary-meta">覆盖 {relativeRange} · 更新于 {createdAt}</span>
          <span className="range">{range}</span>
        </div>
        {bodyJSX}
        {footerJSX}
        {modalJSX}
      </div>
    );
  }

  return (
    <section className={`panel ${className ?? ""}`.trim()} style={{ borderTop: `3px solid ${accent}` }}>
      <header>
        <div>
          <h2>{title}</h2>
          <p className="subtitle">{subtitle}</p>
          <p className="summary-meta">覆盖 {relativeRange} · 更新于 {createdAt}</p>
        </div>
        <div className="range">{range}</div>
      </header>
      {bodyJSX}
      {footerJSX}
      {modalJSX}
    </section>
  );
}

export default function App() {
  const [source, setSource] = useState("mixed");
  const [speechLanguage, setSpeechLanguage] = useState("auto");
  const [summaryLanguage, setSummaryLanguage] = useState("zh");
  const [subtitleLanguage, setSubtitleLanguage] = useState("off");
  const [runtimeProfile, setRuntimeProfile] = useState("balanced");
  const [vocabulary, setVocabulary] = useState("");
  const [sessionEnabled, setSessionEnabled] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [lastExport, setLastExport] = useState<ExportMeetingResponse | null>(null);
  const [exportRoot, setExportRoot] = useState<string>("");
  const [exporting, setExporting] = useState(false);
  const [exportIntent, setExportIntent] = useState<"manual" | "restart" | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [bookmarkFeedback, setBookmarkFeedback] = useState<string | null>(null);
  const [refreshingSummary, setRefreshingSummary] = useState<"rolling_summary" | "cumulative_meeting_summary" | "refined_transcript" | null>(null);
  const [refreshBaselineId, setRefreshBaselineId] = useState<string | null>(null);
  const [bilingualExport, setBilingualExport] = useState(false);
  const [restartPromptOpen, setRestartPromptOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnosticsMode, setDiagnosticsMode] = useState<"simple" | "advanced">(
    () => (window.localStorage.getItem("meetingbro.diagnosticsMode") === "advanced" ? "advanced" : "simple"),
  );
  const [computeActivityHold, setComputeActivityHold] = useState({ cpu: false, gpu: false });
  const [vocabularyOpen, setVocabularyOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"summary" | "clean" | "board" | "notes">("summary");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [audioDevice, setAudioDevice] = useState("");
  const [loopbackDevice, setLoopbackDevice] = useState("");
  const [audioDevices, setAudioDevices] = useState<AudioDevices | null>(null);
  const { connected, state, meetingId, sessionStartedAt, elapsedSeconds, sessionStats, segments, previewSegment, previewSegments, isExperimentalPreview, previewDisplayText, previewIsStreaming, departingPreviewSegments, latestByType, historyByType, notes, lastError, lastErrorCode, saveNote, saveBookmark, applyVocabulary, exportMeeting, requestSummary, pauseSession, resumeSession, stopSession } =
    useSessionSocket({ enabled: sessionEnabled, source, speechLanguage, summaryLanguage, subtitleLanguage, runtimeProfile, audioDevice, loopbackDevice });

  const backend = useBackendStatus();

  // Keep the socket open while the backend transcribes buffered audio and sends
  // final segments. Closing it immediately would turn Stop into an abrupt abort.
  useEffect(() => {
    if (stopRequested && state === "disconnected") {
      setSessionEnabled(false);
      setStopRequested(false);
    }
  }, [stopRequested, state]);

  // Load persisted device choices once, and fetch the device list when the
  // backend becomes ready.
  useEffect(() => {
    setAudioDevice(window.localStorage.getItem(AUDIO_DEVICE_KEY) ?? "");
    setLoopbackDevice(window.localStorage.getItem(LOOPBACK_DEVICE_KEY) ?? "");
  }, []);
  useEffect(() => {
    if (!backend.isReady) return;
    fetchAudioDevices().then(setAudioDevices).catch(() => setAudioDevices(null));
  }, [backend.isReady]);
  // First run: open Settings once so a new user lands on configuration instead
  // of guessing. Marking firstRunComplete touches no startup keys, so it won't
  // restart the backend.
  useEffect(() => {
    const bridge = window.meetingbro;
    if (!bridge?.getSettings || !backend.isReady) return;
    bridge.getSettings().then((s) => {
      if (!s.firstRunComplete) {
        setSettingsOpen(true);
        bridge.saveSettings?.({ firstRunComplete: true }).catch(() => {});
      }
    }).catch(() => {});
  }, [backend.isReady]);
  useEffect(() => {
    window.localStorage.setItem(AUDIO_DEVICE_KEY, audioDevice);
  }, [audioDevice]);
  useEffect(() => {
    window.localStorage.setItem(LOOPBACK_DEVICE_KEY, loopbackDevice);
  }, [loopbackDevice]);
  useEffect(() => {
    window.localStorage.setItem("meetingbro.diagnosticsMode", diagnosticsMode);
  }, [diagnosticsMode]);

  // Tell the Electron supervisor when a session is live so it won't restart the
  // backend (e.g. after a settings change) mid-recording.
  useEffect(() => {
    window.meetingbro?.setSessionActive?.(sessionEnabled);
  }, [sessionEnabled]);

  const rolling = latestByType.rolling_summary;
  const refined = latestByType.refined_transcript;
  const cumulative = latestByType.cumulative_meeting_summary;
  const chapterSnapshot = latestByType.chapter_list;
  const actionItemSnapshot = latestByType.action_item_list;
  const hasRetainedMeetingData = !sessionEnabled && !!meetingId && (
    segments.length > 0 ||
    notes.length > 0 ||
    Object.keys(latestByType).length > 0
  );

  useEffect(() => {
    setVocabulary(window.localStorage.getItem(VOCABULARY_STORAGE_KEY) ?? "");
  }, []);

  useEffect(() => {
    if (!actionFeedback) {
      return;
    }
    const timer = window.setTimeout(() => setActionFeedback(null), 3200);
    return () => window.clearTimeout(timer);
  }, [actionFeedback]);

  useEffect(() => {
    if (!bookmarkFeedback) {
      return;
    }
    const timer = window.setTimeout(() => setBookmarkFeedback(null), 2200);
    return () => window.clearTimeout(timer);
  }, [bookmarkFeedback]);

  useEffect(() => {
    if (!refreshingSummary) {
      return;
    }
    const latest = latestByType[refreshingSummary];
    if (!latest || latest.id === refreshBaselineId) {
      return;
    }
    setRefreshingSummary((current) => current === refreshingSummary ? null : current);
    setRefreshBaselineId(null);
  }, [latestByType, refreshBaselineId, refreshingSummary]);

  const visibleSegments = useMemo(() => segments.slice(-200), [segments]);
  const visibleBookmarks = useMemo(() => {
    if (visibleSegments.length === 0) {
      return [];
    }
    const firstVisibleStart = visibleSegments[0].start_time;
    const lastVisibleEnd = visibleSegments[visibleSegments.length - 1].end_time;
    const latestTimelineSeconds = Math.max(lastVisibleEnd, elapsedSeconds || 0);
    return notes
      .filter((note) => note.source_type === "bookmark" && note.time_seconds != null)
      .filter((note) => (note.time_seconds ?? 0) >= firstVisibleStart && (note.time_seconds ?? 0) <= latestTimelineSeconds)
      .sort((left, right) => (left.time_seconds ?? 0) - (right.time_seconds ?? 0));
  }, [elapsedSeconds, notes, visibleSegments]);
  const transcriptTimelineItems = useMemo(() => {
    const items: Array<
      | { type: "segment"; segment: typeof visibleSegments[number] }
      | { type: "bookmark"; note: typeof notes[number] }
    > = [];
    let bookmarkIndex = 0;

    for (const segment of visibleSegments) {
      while (
        bookmarkIndex < visibleBookmarks.length &&
        (visibleBookmarks[bookmarkIndex].time_seconds ?? 0) <= segment.end_time
      ) {
        items.push({ type: "bookmark", note: visibleBookmarks[bookmarkIndex] });
        bookmarkIndex += 1;
      }
      items.push({ type: "segment", segment });
    }

    while (bookmarkIndex < visibleBookmarks.length) {
      items.push({ type: "bookmark", note: visibleBookmarks[bookmarkIndex] });
      bookmarkIndex += 1;
    }

    return items;
  }, [notes, visibleBookmarks, visibleSegments]);
  const chapters = useMemo(() => chapterSnapshot ? parseSnapshotList(chapterSnapshot.content) : [], [chapterSnapshot]);
  const actionItems = useMemo(() => actionItemSnapshot ? parseSnapshotList(actionItemSnapshot.content) : [], [actionItemSnapshot]);
  const latestSegment = segments.at(-1);
  const [newSegmentOrders, setNewSegmentOrders] = useState<Record<string, number>>({});
  const segmentAnimationKnownIdsRef = useRef<Set<string>>(new Set());
  const latestVisualSegment = previewSegment ?? latestSegment;
  const handoffPreviewSegments = useMemo(
    () => [...departingPreviewSegments, ...previewSegments],
    [departingPreviewSegments, previewSegments],
  );
  const shouldShowPreviewStack = state === "running" || departingPreviewSegments.length > 0 || previewSegments.length > 0;
  const previewStackRevision = useMemo(
    () => handoffPreviewSegments.map((segment) => `${segment.id}:${segment.text}`).join("|"),
    [handoffPreviewSegments],
  );
  const latestSegmentRevision = latestSegment ? `${latestSegment.id}:${latestSegment.text}` : "";
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const knownIds = segmentAnimationKnownIdsRef.current;

    if (segments.length === 0) {
      knownIds.clear();
      setNewSegmentOrders({});
      return;
    }

    const newlyAdded = segments.filter((segment) => !knownIds.has(segment.id));
    segments.forEach((segment) => knownIds.add(segment.id));

    if (newlyAdded.length === 0) {
      return;
    }

    const addedOrders = Object.fromEntries(
      newlyAdded.map((segment, index) => [segment.id, index]),
    ) as Record<string, number>;
    const addedIds = new Set(newlyAdded.map((segment) => segment.id));
    setNewSegmentOrders((prev) => ({ ...prev, ...addedOrders }));
    const timer = window.setTimeout(() => {
      setNewSegmentOrders((prev) => {
        const next = { ...prev };
        addedIds.forEach((id) => {
          delete next[id];
        });
        return next;
      });
    }, 1100);
    return () => window.clearTimeout(timer);
  }, [segments]);

  useEffect(() => {
    if (!sessionEnabled) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [sessionEnabled]);

  const audioClockSeconds = useMemo(() => {
    if (elapsedSeconds > 0) {
      return elapsedSeconds;
    }
    if (!sessionStartedAt) {
      return null;
    }
    const sessionStartMs = new Date(sessionStartedAt).getTime();
    if (Number.isNaN(sessionStartMs)) {
      return null;
    }
    return Math.max(0, (nowMs - sessionStartMs) / 1000);
  }, [elapsedSeconds, nowMs, sessionStartedAt]);

  const committedLagSeconds = useMemo(() => {
    if (!latestSegment || state !== "running" || audioClockSeconds == null) {
      return null;
    }
    const committedAt = latestSegment.emitted_at_elapsed_seconds;
    if (committedAt != null) {
      return Math.max(0, committedAt - latestSegment.end_time);
    }
    return Math.max(0, audioClockSeconds - latestSegment.end_time);
  }, [audioClockSeconds, latestSegment, state]);

  const liveGapSeconds = useMemo(() => {
    if (!latestVisualSegment || state !== "running" || audioClockSeconds == null) {
      return null;
    }
    return Math.max(0, audioClockSeconds - latestVisualSegment.end_time);
  }, [audioClockSeconds, latestVisualSegment, state]);

  const transcriptLagSeconds = liveGapSeconds ?? committedLagSeconds;

  const visibleTranscriptSeconds = latestSegment?.end_time ?? null;
  const backpressureAgeSeconds = useMemo(() => {
    const lastBackpressure = sessionStats?.last_backpressure_elapsed_seconds;
    if (lastBackpressure == null || elapsedSeconds <= 0) {
      return null;
    }
    return Math.max(0, elapsedSeconds - lastBackpressure);
  }, [elapsedSeconds, sessionStats?.last_backpressure_elapsed_seconds]);
  const retryTotal = sessionStats?.retry_windows_total ?? 0;
  const retryImproved = sessionStats?.retry_windows_improved ?? 0;
  const retryUnchanged = sessionStats?.retry_windows_unchanged ?? 0;
  const retryDiverged = sessionStats?.retry_windows_diverged ?? 0;
  const asrRealtimeFactor = sessionStats?.asr_realtime_factor ?? null;
  const asrWallSeconds = sessionStats?.asr_last_wall_seconds ?? null;
  const asrAudioSeconds = sessionStats?.asr_last_audio_seconds ?? null;
  const asrSafeguardActive = sessionStats?.asr_safeguard_active ?? false;
  const asrSafeguardEvents = sessionStats?.asr_safeguard_events ?? 0;
  const resourcePressureLevel = sessionStats?.resource_pressure_level ?? "normal";
  const resourceGovernorPolicy = sessionStats?.resource_governor_policy ?? "balanced";
  const resourceGovernorReason = sessionStats?.resource_governor_reason ?? null;
  const resourceGovernorSkips = sessionStats?.resource_governor_skips ?? 0;
  const activeRuntimeProfile = sessionStats?.runtime_profile ?? runtimeProfile;
  const summaryOnlyMode = activeRuntimeProfile === "summary_only";
  const activeHardwareProfile = sessionStats?.hardware_profile ?? "auto";
  const activeHardwareSummary = sessionStats?.hardware_summary ?? "正在检测本机 CPU/GPU";
  const computeCpuActive = sessionStats?.compute_cpu_active ?? false;
  const computeCpuAvailable = sessionStats?.compute_cpu_available ?? true;
  const computeCpuConfigured = sessionStats?.compute_cpu_configured ?? false;
  const computeGpuActive = sessionStats?.compute_gpu_active ?? false;
  const computeGpuAvailable = sessionStats?.compute_gpu_available ?? false;
  const computeGpuConfigured = sessionStats?.compute_gpu_configured ?? false;
  const computeActivityLabel = sessionStats?.compute_activity_label ?? "idle";
  const cpuChipTitle = computeCpuActive
    ? computeActivityLabel
    : computeCpuConfigured
      ? "已配置 CPU，等待识别任务"
      : computeCpuAvailable
        ? "CPU 可用，当前没有分配识别任务"
        : "CPU 不可用";
  const gpuChipTitle = computeGpuActive
    ? computeActivityLabel
    : computeGpuConfigured
      ? "已配置 GPU，等待 Whisper 任务"
      : computeGpuAvailable
        ? "GPU 可用，但当前配置使用 CPU"
        : "当前语音识别环境无法使用 GPU";
  const displayCpuActive = computeCpuActive || computeActivityHold.cpu;
  const displayGpuActive = computeGpuActive || computeActivityHold.gpu;
  const activeChunkSeconds = sessionStats?.audio_chunk_seconds ?? null;
  const activeAccumSeconds = sessionStats?.asr_accumulation_seconds ?? null;
  const languageLockEnabled = sessionStats?.language_lock_enabled ?? false;
  const weakRescueAttempts = sessionStats?.weak_rescue_attempts ?? 0;
  const weakRescueEmitted = sessionStats?.weak_rescue_emitted ?? 0;
  const weakRescueBufferSeconds = sessionStats?.weak_rescue_buffer_seconds ?? 0;
  const translationPendingCount = sessionStats?.translation_pending_count ?? 0;
  const summaryPendingCount = sessionStats?.summary_pending_count ?? 0;
  const translationTrimTotal = sessionStats?.translation_backlog_trim_total ?? 0;
  const audioDropTotal = sessionStats?.audio_drop_total ?? 0;
  const audioInputBacklogSeconds = sessionStats?.audio_input_backlog_seconds ?? 0;
  const audioInputQueueDropTotal = sessionStats?.audio_input_queue_drop_total ?? 0;
  const audioQueueWaitSeconds = sessionStats?.audio_queue_wait_seconds ?? null;
  const eventQueueDepth = sessionStats?.event_queue_depth ?? 0;
  const fastPreviewEnabled = sessionStats?.fast_preview_enabled ?? false;
  const fastPreviewAttempts = sessionStats?.fast_preview_attempts ?? 0;
  const fastPreviewEmitted = sessionStats?.fast_preview_emitted ?? 0;
  const fastPreviewSkipped = sessionStats?.fast_preview_skipped ?? 0;
  const fastPreviewRtf = sessionStats?.fast_preview_realtime_factor ?? null;
  const fastPreviewScheduleDelay = sessionStats?.fast_preview_schedule_delay_seconds ?? null;
  const snapshotConcatWall = sessionStats?.snapshot_concat_wall_seconds ?? null;
  const previewContinuedDuringFormal = sessionStats?.preview_continued_during_formal ?? 0;
  const previewStaleSuppressed = sessionStats?.preview_stale_suppressed ?? 0;
  const previewAlignmentCompared = sessionStats?.preview_alignment_compared ?? 0;
  const previewAlignmentSimilarityAvg = sessionStats?.preview_alignment_similarity_avg ?? null;
  const previewAlignmentSimilarityLast = sessionStats?.preview_alignment_similarity_last ?? null;
  const previewUnconfirmedAfterFormal = sessionStats?.preview_unconfirmed_after_formal ?? 0;
  const previewUnconfirmedLastText = sessionStats?.preview_unconfirmed_last_text ?? null;
  const qwenTargetedRetryAttempts = sessionStats?.qwen_targeted_retry_attempts ?? 0;
  const qwenTargetedRetryRecovered = sessionStats?.qwen_targeted_retry_recovered ?? 0;
  const qwenTargetedRetryFailed = sessionStats?.qwen_targeted_retry_failed ?? 0;
  const qwenTargetedRetrySkipped = sessionStats?.qwen_targeted_retry_skipped ?? 0;
  const qwenTargetedRetryLastReason = sessionStats?.qwen_targeted_retry_last_reason ?? null;
  const delayTone = getDelayTone(transcriptLagSeconds);
  const activeSource = sessionStats?.source ?? source;
  const mixedMicGain = sessionStats?.mixed_microphone_gain ?? null;
  const mixedSystemGain = sessionStats?.mixed_system_gain ?? null;
  const mixedEffectiveMicGain = sessionStats?.mixed_effective_microphone_gain ?? null;
  const mixedAutoBalanceEnabled = sessionStats?.mixed_auto_balance_enabled ?? null;
  const mixedGainTone = getGainTone(mixedEffectiveMicGain, mixedMicGain, activeSource);
  const mixedGainRatio =
    activeSource === "mixed"
      ? `麦克风 ${formatGain(mixedEffectiveMicGain)} / 系统 ${formatGain(mixedSystemGain)}`
      : "—";
  const mixedGainHint = getMixedGainHint(mixedGainTone, activeSource);
  const activeSubtitleLanguage: "zh" | "en" | "de" | null = summaryOnlyMode || subtitleLanguage === "off"
    ? null
    : ((sessionStats?.live_translation_language ?? subtitleLanguage) as "zh" | "en" | "de");
  const visibleSubtitleRevision = useMemo(() => {
    if (activeSubtitleLanguage == null) {
      return 0;
    }
    return visibleSegments.reduce((revision, segment, index) => {
      const text = segment.translations[activeSubtitleLanguage]?.trim();
      if (!text) {
        return revision;
      }
      return revision + text.length + index + 1;
    }, 0);
  }, [activeSubtitleLanguage, visibleSegments]);
  const recentSpeechLanguages = useMemo(() => {
    const languages = new Set<string>();
    for (const segment of visibleSegments.slice(-24)) {
      if (segment.original_language !== "unknown") {
        languages.add(segment.original_language);
      }
    }
    return languages;
  }, [visibleSegments]);
  const latestSubtitleText = activeSubtitleLanguage && latestSegment
    ? latestSegment.translations[activeSubtitleLanguage]
    : null;
  const subtitleStatus = activeSubtitleLanguage == null
    ? "关闭"
    : !latestSegment
      ? "等待中"
      : latestSegment.original_language === activeSubtitleLanguage
        ? "语言相同"
        : latestSubtitleText && latestSubtitleText.trim()
          ? "已翻译"
          : "翻译中";
  const subtitleStatusDetail = activeSubtitleLanguage == null
    ? "翻译字幕已关闭"
    : !latestSegment
      ? `目标语言：${formatLanguageLabel(activeSubtitleLanguage)} · 等待逐字稿`
      : latestSegment.original_language === activeSubtitleLanguage
        ? `最新内容已经是${formatLanguageLabel(activeSubtitleLanguage)}`
        : latestSubtitleText && latestSubtitleText.trim()
          ? `最新${formatLanguageLabel(activeSubtitleLanguage)}字幕已就绪`
          : `目标语言：${formatLanguageLabel(activeSubtitleLanguage)} · 等待翻译`;

  const systemAdvice = useMemo<SystemAdvice[]>(() => {
    if (!sessionEnabled || state !== "running") {
      return [{
        severity: "ok",
        title: "等待录音",
        detail: "开始录音后，这里会显示稳定性、准确率和延迟提示。",
      }];
    }

    const advice: SystemAdvice[] = [];
    const realtimeGap = transcriptLagSeconds ?? 0;
    const rtf = asrRealtimeFactor ?? 0;
    const asrBusy = lastError?.includes("ASR has been processing") ?? false;

    if (asrBusy) {
      advice.push({
        severity: "warn",
        title: "语音识别正在忙碌",
        detail: "后端仍在处理当前音频片段。",
        action: "如持续延迟，可切换较小的 Whisper 模型或关闭翻译字幕；停止后请等待整理完成。",
      });
    } else if (asrSafeguardActive || rtf >= 1.0 || backpressureAgeSeconds != null) {
      advice.push({
        severity: asrSafeguardActive || rtf >= 1.2 ? "danger" : "warn",
        title: "语音识别速度落后于录音",
        detail: asrSafeguardActive
          ? "后端已启用实时保护。"
          : `最近一次识别耗时与音频时长之比：${formatRtf(asrRealtimeFactor)}。`,
        action: "停止后请等待积压音频处理完；若长期延迟，可换更小模型或关闭翻译字幕。",
      });
    } else if (realtimeGap >= 4.0 && activeRuntimeProfile !== "summary_only") {
      advice.push({
        severity: "warn",
        title: "逐字稿落后于音频",
        detail: `当前显示的文字比音频进度慢 ${formatLagSeconds(realtimeGap)}。`,
        action: "可关闭翻译字幕以减轻负担；停止后继续等待后端整理。",
      });
    }

    if (weakRescueAttempts >= 2 || weakRescueBufferSeconds >= 2.0) {
      advice.push({
        severity: weakRescueEmitted > 0 ? "warn" : "ok",
        title: "检测到声音偏小",
        detail: `弱语音补救尝试 ${weakRescueAttempts} 次，输出 ${weakRescueEmitted} 次。`,
        action: "请提高播放音量，或靠近麦克风。",
      });
    }

    if (mixedGainTone === "warn" || mixedGainTone === "danger") {
      advice.push({
        severity: mixedGainTone,
        title: "系统声音与麦克风音量可能不均衡",
        detail: mixedGainHint,
        action: "请调整麦克风或系统音量，并保持自动平衡开启。",
      });
    }

    if (translationPendingCount >= 4 || translationTrimTotal > 0) {
      advice.push({
        severity: translationTrimTotal > 0 ? "warn" : "ok",
        title: "字幕翻译繁忙",
        detail: `待翻译 ${translationPendingCount} 条，略过 ${translationTrimTotal} 条。`,
        action: "如电脑运行缓慢，可关闭翻译字幕。",
      });
    }

    if (audioDropTotal > 0) {
      advice.push({
        severity: audioDropTotal >= 5 ? "danger" : "warn",
        title: "有音频片段丢失",
        detail: `采集队列已丢失 ${audioDropTotal} 个片段。`,
        action: "请关闭占用音频设备或 CPU 的其他程序，并检查录音来源。",
      });
    }

    if (audioInputBacklogSeconds >= 2.0 || audioInputQueueDropTotal > 0) {
      advice.push({
        severity: audioInputBacklogSeconds >= 5.0 || audioInputQueueDropTotal > 0 ? "warn" : "ok",
        title: "音频正在等待识别",
        detail: `等待时长 ${formatLagSeconds(audioInputBacklogSeconds)}，队列丢失 ${audioInputQueueDropTotal} 个片段。`,
        action: "停止后请等整理完成；若积压持续增长，可换较小的 Whisper 模型。",
      });
    }

    if (fastPreviewEnabled && fastPreviewAttempts > 0 && fastPreviewEmitted === 0) {
      advice.push({
        severity: "warn",
        title: "实时预览尚未显示文字",
        detail: `尝试 ${fastPreviewAttempts} 次，跳过 ${fastPreviewSkipped} 次。`,
        action: "静音或识别忙碌时可能出现；请先确认音频来源有声音。",
      });
    }

    if (speechLanguage !== "auto" && recentSpeechLanguages.size >= 2) {
      advice.push({
        severity: "warn",
        title: "检测到多种语音语言",
        detail: `最近文字包含 ${Array.from(recentSpeechLanguages).join("、")}。`,
        action: "如网课中切换语言，请将“语音语言”设为“自动识别”。",
      });
    }

    if (advice.length === 0) {
      advice.push({
        severity: "ok",
        title: "录音链路状态正常",
        detail: "当前没有稳定性、延迟或准确率警告。",
        action: activeRuntimeProfile === "balanced"
          ? "一般保持“均衡”模式即可。"
          : `当前模式：${formatRuntimeProfileLabel(activeRuntimeProfile)}。`,
      });
    }

    return advice.slice(0, 4);
  }, [
    activeRuntimeProfile,
    asrRealtimeFactor,
    asrSafeguardActive,
    audioDropTotal,
    audioInputBacklogSeconds,
    audioInputQueueDropTotal,
    backpressureAgeSeconds,
    fastPreviewAttempts,
    fastPreviewEmitted,
    fastPreviewEnabled,
    fastPreviewSkipped,
    languageLockEnabled,
    lastError,
    mixedGainHint,
    mixedGainTone,
    recentSpeechLanguages,
    sessionEnabled,
    sessionStats?.asr_safeguard_reason,
    speechLanguage,
    state,
    transcriptLagSeconds,
    translationPendingCount,
    translationTrimTotal,
    weakRescueAttempts,
    weakRescueBufferSeconds,
    weakRescueEmitted,
  ]);
  const systemAdviceTone = systemAdvice.some((item) => item.severity === "danger")
    ? "danger"
    : systemAdvice.some((item) => item.severity === "warn")
      ? "warn"
      : "ok";

  const transcriptBodyRef = useRef<HTMLDivElement>(null);
  const transcriptBottomRef = useRef<HTMLDivElement>(null);
  const transcriptAutoFollowRef = useRef(true);
  const transcriptProgrammaticScrollRef = useRef(false);
  const transcriptFollowFrameRef = useRef<number | null>(null);
  const [transcriptAutoFollow, setTranscriptAutoFollow] = useState(true);

  const scrollTranscriptToBottom = (behavior: ScrollBehavior = "auto") => {
    if (transcriptFollowFrameRef.current !== null) {
      window.cancelAnimationFrame(transcriptFollowFrameRef.current);
    }
    transcriptFollowFrameRef.current = window.requestAnimationFrame(() => {
      transcriptFollowFrameRef.current = null;
      const body = transcriptBodyRef.current;
      if (!body) return;
      transcriptProgrammaticScrollRef.current = true;
      if (behavior === "smooth") {
        body.scrollTo({ top: body.scrollHeight, behavior });
      } else {
        body.scrollTop = body.scrollHeight;
      }
      window.setTimeout(() => {
        const latestBody = transcriptBodyRef.current;
        if (latestBody && transcriptAutoFollowRef.current) {
          latestBody.scrollTop = latestBody.scrollHeight;
        }
        transcriptProgrammaticScrollRef.current = false;
      }, behavior === "smooth" ? 420 : 60);
    });
  };

  useLayoutEffect(() => {
    if (transcriptAutoFollowRef.current) {
      scrollTranscriptToBottom("auto");
    }
  }, [
    visibleSegments.length,
    latestSegmentRevision,
    visibleSubtitleRevision,
    previewSegment?.id,
    previewStackRevision,
    previewSegments.length,
    departingPreviewSegments.length,
    latestSegment?.id,
    latestSubtitleText,
    activeSubtitleLanguage,
  ]);

  useEffect(() => {
    return () => {
      if (transcriptFollowFrameRef.current !== null) {
        window.cancelAnimationFrame(transcriptFollowFrameRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!computeCpuActive && !computeGpuActive) {
      return;
    }
    setComputeActivityHold((prev) => ({
      cpu: prev.cpu || computeCpuActive,
      gpu: prev.gpu || computeGpuActive,
    }));
    const timer = window.setTimeout(() => {
      setComputeActivityHold({ cpu: false, gpu: false });
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [computeCpuActive, computeGpuActive]);

  const notesBodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notesBodyRef.current) {
      notesBodyRef.current.scrollTop = notesBodyRef.current.scrollHeight;
    }
  }, [notes]);

  const handleSaveToNotes = async (snapshot: SummarySnapshot) => {
    await saveNote({
      content: snapshot.content,
      source_type: snapshot.summary_type,
      source_id: snapshot.id,
    });
  };

  const currentExportInput = (): ExportMeetingInput => ({
    source: activeSource,
    runtime_profile: activeRuntimeProfile,
    summary_language: summaryLanguage,
    subtitle_language: summaryOnlyMode ? "off" : subtitleLanguage,
    export_dir: exportRoot.trim() || undefined,
    bilingual: bilingualExport,
    target_language: bilingualExport ? ((summaryLanguage === "zh" || summaryLanguage === "en" || summaryLanguage === "de") ? summaryLanguage : undefined) : undefined,
  });

  const handleExportMeeting = async () => {
    setExportIntent("manual");
    setActionFeedback(null);
    setExporting(true);
    try {
      const result = await exportMeeting(currentExportInput());
      if (result) {
        setLastExport(result);
        setActionFeedback(`已导出到 ${result.export_dir}`);
      }
    } finally {
      setExporting(false);
      setExportIntent(null);
    }
  };

  const handleChooseExportFolder = async () => {
    const chooser = window.meetingbro?.selectExportDirectory;
    if (!chooser) {
      return;
    }
    const selected = await chooser(defaultExportFolderName());
    if (selected) {
      setExportRoot(selected);
    }
  };

  const handleRuntimeProfileChange = (value: string) => {
    setRuntimeProfile(value);
    if (value === "summary_only") {
      setSubtitleLanguage("off");
      setActiveTab("summary");
    }
  };

  const handleSaveVocabulary = () => {
    window.localStorage.setItem(VOCABULARY_STORAGE_KEY, vocabulary);
    applyVocabulary(vocabulary);
  };

  const handleStartSession = () => {
    if (hasRetainedMeetingData) {
      setRestartPromptOpen(true);
      return;
    }
    setLastExport(null);
    setStopRequested(false);
    setSessionEnabled(true);
  };

  const handleTrySample = () => {
    // One-click demo: replay the bundled clip so a first-time user / tester sees
    // the full pipeline without configuring any audio device.
    setSource("sample");
    if (hasRetainedMeetingData) {
      setRestartPromptOpen(true);
      return;
    }
    setLastExport(null);
    setStopRequested(false);
    setSessionEnabled(true);
  };

  const handleRestartWithoutSave = () => {
    setRestartPromptOpen(false);
    setLastExport(null);
    setActionFeedback(null);
    setStopRequested(false);
    setSessionEnabled(true);
  };

  const handleSaveAndRestart = async () => {
    setExportIntent("restart");
    setActionFeedback(null);
    setExporting(true);
    try {
      const result = await exportMeeting(currentExportInput());
      if (!result) {
        return;
      }
      setLastExport(result);
      setActionFeedback(`已保存到 ${result.export_dir}，正在开始新录音…`);
      setRestartPromptOpen(false);
      setStopRequested(false);
      setSessionEnabled(true);
    } finally {
      setExporting(false);
      setExportIntent(null);
    }
  };

  const handleBookmark = async () => {
    const label = window.prompt("书签名称（可选）", "");
    if (label === null) {
      return;
    }
    await saveBookmark(label);
    setBookmarkFeedback(
      label.trim()
        ? `已在 ${formatElapsedSeconds(audioClockSeconds ?? elapsedSeconds)} 保存书签 · ${label.trim()}`
        : `已在 ${formatElapsedSeconds(audioClockSeconds ?? elapsedSeconds)} 保存书签`,
    );
  };
  const handleRefreshSummary = (summaryType: "rolling_summary" | "cumulative_meeting_summary" | "refined_transcript") => {
    setRefreshBaselineId(latestByType[summaryType]?.id ?? null);
    setRefreshingSummary(summaryType);
    requestSummary(summaryType);
  };
  const vocabularyHint = sessionEnabled
    ? "添加专有名词可提升识别效果，录音中也可保存。"
    : "添加专有名词可提升识别效果，录音前或录音中均可保存。";
  const vocabularyTermCount = useMemo(() => {
    return vocabulary
      .split(/[\n,，;；]+/)
      .map((term) => term.trim())
      .filter(Boolean).length;
  }, [vocabulary]);

  const transcriptEmptyMessage = !sessionEnabled
    ? "录音已停止，点击“开始录音”即可继续"
    : state === "starting"
      ? "正在连接录音会话…"
      : state === "paused"
        ? "录音已暂停，点击“继续”恢复"
      : activeSource === "loopback" || activeSource === "system"
        ? "正在监听系统声音，请播放网课；若要同时录老师讲话，请切换到“系统声音 + 麦克风”"
        : activeSource === "mic"
          ? "正在监听麦克风，请讲话以开始转录"
          : "正在监听系统声音与麦克风，请讲话或播放音频";

  return (
    <div className="app">
      {!backend.isReady && (
        <BackendGate
          state={backend.state}
          detail={backend.detail}
          logTail={backend.logTail}
          onRetry={backend.retry}
          onOpenLog={backend.openLog}
        />
      )}
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} sessionActive={sessionEnabled} />
      <HistoryModal open={historyOpen} onClose={() => setHistoryOpen(false)} currentMeetingId={meetingId} />
      <header className="app-header">
        <div className="brand-block">
          <div className="brand-row">
            <strong>MeetingBro</strong>
            <span className={`session-state state-${state}`}>{{ disconnected: "未连接", starting: "启动中", running: "录音中", paused: "已暂停", ended: "已结束" }[state] ?? state}</span>
            {meetingId && <span className="meeting-id-pill">#{meetingId.slice(0, 8)}</span>}
            <span className={`compute-chip ${displayCpuActive ? "active" : computeCpuConfigured ? "configured" : computeCpuAvailable ? "available" : "idle"}`} title={cpuChipTitle}>
              <span className="compute-dot" aria-hidden="true" /> CPU
            </span>
            <span className={`compute-chip ${displayGpuActive ? "active" : computeGpuConfigured ? "configured" : computeGpuAvailable ? "available" : "idle"}`} title={gpuChipTitle}>
              <span className="compute-dot" aria-hidden="true" /> GPU
            </span>
          </div>
          <span className="app-tagline">实时字幕 · 自动笔记 · 完整逐字稿</span>
        </div>
        <div className="header-controls" aria-label="录音控制">
          <div className="settings-controls" aria-label="录音来源和语言设置">
            <label className="control-pill">
              <span>录音来源</span>
              <select value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="mic">麦克风（现实课堂）</option>
                <option value="loopback">系统声音（网课）</option>
                <option value="mixed">系统声音 + 麦克风</option>
                <option value="sample">示例音频（演示）</option>
              </select>
            </label>
            {(source === "mic" || source === "mixed") && audioDevices && audioDevices.mics.length > 0 && (
              <label className="control-pill">
                <span>麦克风设备</span>
                <select value={audioDevice} onChange={(e) => setAudioDevice(e.target.value)}>
                  <option value="">默认设备</option>
                  {audioDevices.mics.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
            )}
            {(source === "loopback" || source === "system") && audioDevices && audioDevices.loopbacks.length > 0 && (
              <label className="control-pill">
                <span>系统输出设备</span>
                <select value={loopbackDevice} onChange={(e) => setLoopbackDevice(e.target.value)}>
                  <option value="">默认设备</option>
                  {audioDevices.loopbacks.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
            )}
            <label className="control-pill">
              <span>运行模式</span>
              <select value={runtimeProfile} onChange={(e) => handleRuntimeProfileChange(e.target.value)}>
                <option value="balanced">均衡</option>
                <option value="performance">高性能</option>
                <option value="summary_only">仅生成摘要</option>
              </select>
            </label>
            <label className="control-pill">
              <span>语音语言</span>
              <select value={speechLanguage} onChange={(e) => setSpeechLanguage(e.target.value)}>
                <option value="auto">自动识别</option>
                <option value="en">英语</option>
                <option value="zh">中文</option>
                <option value="de">德语</option>
              </select>
            </label>
            <label className="control-pill">
              <span>笔记语言</span>
              <select value={summaryLanguage} onChange={(e) => setSummaryLanguage(e.target.value)}>
                <option value="en">英语</option>
                <option value="zh">中文</option>
                <option value="de">德语</option>
              </select>
            </label>
            <label className="control-pill">
              <span>翻译字幕</span>
              <select value={summaryOnlyMode ? "off" : subtitleLanguage} onChange={(e) => setSubtitleLanguage(e.target.value)} disabled={summaryOnlyMode}>
                <option value="off">关闭</option>
                <option value="en">英语</option>
                <option value="zh">中文</option>
                <option value="de">德语</option>
              </select>
            </label>
            <button type="button" className="settings-gear" onClick={() => setHistoryOpen(true)} title="录音历史" aria-label="录音历史">
              🕘
            </button>
            <button type="button" className="settings-gear" onClick={() => setSettingsOpen(true)} title="设置" aria-label="设置">
              ⚙
            </button>
          </div>
          <div className="session-controls" aria-label="录音操作">
            {!sessionEnabled ? (
              <>
                <button
                  className="sample-btn"
                  onClick={handleTrySample}
                  disabled={!backend.isReady}
                  title="播放内置示例音频，无需麦克风或网课"
                >
                  ▶ 试用示例
                </button>
                <button className="start-btn" onClick={handleStartSession} disabled={!backend.isReady}>开始录音</button>
              </>
            ) : (
              <>
                {state === "paused" ? (
                  <button className="resume-btn" onClick={resumeSession} disabled={stopRequested}>继续</button>
                ) : (
                  <button className="pause-btn" onClick={pauseSession} disabled={state !== "running" || stopRequested}>
                    暂停
                  </button>
                )}
                <button
                  className="stop-btn"
                  onClick={() => {
                    setStopRequested(true);
                    stopSession();
                  }}
                  disabled={stopRequested}
                >
                  {stopRequested ? "正在整理逐字稿…" : "停止录音"}
                </button>
              </>
            )}
            <span className={`connection-pill ${connected ? "connected" : "disconnected"}`}>
              <span className={connected ? "dot ok" : "dot bad"} />
              {connected ? "已连接" : "未连接"}
            </span>
          </div>
        </div>
      </header>

      {lastError && !isSystemHealthOnlyMessage(lastError) && (
        lastErrorCode === "llm_unavailable" || lastErrorCode === "translation_unavailable" ? (
          <div className="error error--actionable">
            <span>{formatSessionError(lastErrorCode, lastError)}</span>
            <button type="button" className="settings-btn" onClick={() => setSettingsOpen(true)}>打开设置</button>
          </div>
        ) : (
          <div className="error">{formatSessionError(lastErrorCode, lastError)}</div>
        )
      )}

      <section className={`startup-settings vocabulary-dock${vocabularyOpen ? " open" : ""}`} aria-label="专有名词设置">
        <button
          type="button"
          className="vocabulary-toggle"
          aria-expanded={vocabularyOpen}
          onClick={() => setVocabularyOpen((open) => !open)}
        >
          <span className="vocabulary-toggle-main">
          <strong>专有名词</strong>
            <span className="vocabulary-toggle-note">提高人名、缩写和课程术语的识别准确率</span>
          </span>
          <span className="vocabulary-count">
            {vocabularyTermCount === 0 ? "暂无词条" : `${vocabularyTermCount} 个词条`}
          </span>
          <span className={`toggle-caret${vocabularyOpen ? " open" : ""}`} aria-hidden="true">▼</span>
        </button>
        {vocabularyOpen && (
          <div className="startup-settings-panel">
            <p className="muted">{vocabularyHint}</p>
            <div className="startup-settings-controls">
              <textarea
                value={vocabulary}
                onChange={(e) => setVocabulary(e.target.value)}
                placeholder="Anthropic, MeetingBro, Libin Mao, faster-whisper, pyannote"
                rows={2}
                aria-label="人名、缩写或课程术语"
              />
              <button type="button" className="secondary-action-btn" onClick={handleSaveVocabulary}>保存词条</button>
            </div>
          </div>
        )}
      </section>

      <main className="grid">
        {summaryOnlyMode ? (
          <section className="panel transcript summary-only-panel">
            <header>
              <div>
                <h2>
                  仅生成摘要
                  {state === "running" && <span className="live-dot" aria-label="录音中" />}
                </h2>
                <p className="subtitle">后台录音 · 不显示实时字幕</p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button type="button" className="secondary-action-btn" onClick={handleBookmark} disabled={!connected || state !== "running"}>
                  添加书签
                </button>
                <div className="range">{segments.length} 条转录</div>
              </div>
            </header>
            <div className="panel-body summary-only-body">
              <div className="summary-only-banner">
                <strong>此模式下实时字幕会隐藏。</strong>
                <p>
                  MeetingBro 仍会持续录音和转录，并定期更新摘要、整理笔记及看板。
                </p>
              </div>
              <div className="summary-only-stats">
                <div className="summary-only-stat">
                  <span>已转录</span>
                  <strong>{segments.length} 条</strong>
                </div>
                <div className="summary-only-stat">
                  <span>已录制</span>
                  <strong>{formatElapsedSeconds(audioClockSeconds ?? elapsedSeconds)}</strong>
                </div>
                <div className="summary-only-stat">
                  <span>最近摘要</span>
                  <strong>{rolling?.created_at ? formatCreatedAt(rolling.created_at) : "等待中"}</strong>
                </div>
              </div>
              <p className="muted summary-only-tip">
                提示：如需立即更新，请点击摘要或整理笔记中的“更新”。
              </p>
            </div>
          </section>
        ) : <section className="panel transcript">
          <header>
            <div>
              <h2>
                实时逐字稿
                {state === "running" && <span className="live-dot" aria-label="录音中" />}
              </h2>
              <p className="subtitle">已确认 · 带时间戳</p>
              <p className="transcript-lag-meta">
                <span className={`delay-pill delay-${delayTone}`}>延迟 {formatLagSeconds(transcriptLagSeconds)}</span>
                {committedLagSeconds != null ? ` · 确认耗时 ${formatLagSeconds(committedLagSeconds)}` : ""}
                {previewSegment ? " · 预览中" : ""}
              </p>
              {bookmarkFeedback && <p className="bookmark-feedback">{bookmarkFeedback}</p>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button type="button" className="secondary-action-btn" onClick={handleBookmark} disabled={!connected || state !== "running"}>
                添加书签
              </button>
              <div className="range">{segments.length} 条转录</div>
            </div>
          </header>
          <div
            ref={transcriptBodyRef}
            className="panel-body transcript-body"
            onScroll={(e) => {
              if (transcriptProgrammaticScrollRef.current) {
                return;
              }
              const follow = isNearBottom(e.currentTarget);
              transcriptAutoFollowRef.current = follow;
              setTranscriptAutoFollow(follow);
            }}
          >
            {visibleSegments.length === 0 && (
              <div className="muted">{transcriptEmptyMessage}</div>
            )}
            {transcriptTimelineItems.map((item) => {
              if (item.type === "bookmark") {
                return (
                  <div key={item.note.id} className="segment bookmark-marker">
                    <span className="ts">书签 · {formatElapsedSeconds(item.note.time_seconds)}</span>
                    <div className="segment-text">
                      <span>{item.note.content.trim() || "重要时刻"}</span>
                    </div>
                  </div>
                );
              }

              const s = item.segment;
              const confidenceTone = getConfidenceTone(s.confidence);
              const confidenceLabel = getConfidenceLabel(s.confidence);
              const qualityStyle: CSSProperties | undefined = s.quality === "low"
                ? { opacity: 0.55, fontStyle: "italic" }
                : s.quality === "uncertain"
                  ? { opacity: 0.7 }
                  : undefined;
              const subtitleText = activeSubtitleLanguage ? s.translations[activeSubtitleLanguage] : null;
              const showSubtitlePlaceholder =
                activeSubtitleLanguage != null &&
                s.original_language !== activeSubtitleLanguage &&
                !(subtitleText && subtitleText.trim());
              const segmentOrder = newSegmentOrders[s.id];
              const isNewSegment = segmentOrder !== undefined;
              const segmentDelayMs = isNewSegment ? segmentOrder * FORMAL_SEGMENT_STAGGER_MS : 0;
              const segmentStyle: StaggerStyle | undefined = isNewSegment
                ? {
                  ...qualityStyle,
                  "--segment-delay": `${segmentDelayMs}ms`,
                  "--segment-text-delay": `${segmentDelayMs + FORMAL_CELL_STAGGER_MS}ms`,
                }
                : qualityStyle;
              const segmentClassName = [
                "segment",
                isNewSegment ? "segment-new" : "",
                isNewSegment && hasPreviewHandoff(s, handoffPreviewSegments) ? "segment-promoted" : "",
                confidenceTone !== "stable" ? `segment-${confidenceTone}` : "",
              ].filter(Boolean).join(" ");
              return (
                <div key={s.id} className={segmentClassName} style={segmentStyle}>
                  <span className="ts">
                    {formatCreatedAt(s.created_at)}
                    {confidenceLabel && <em className={`confidence-flag confidence-${confidenceTone}`}>{confidenceLabel}</em>}
                  </span>
                  <div className="segment-text">
                    <span>{s.text}</span>
                    {subtitleText && subtitleText.trim() && subtitleText.trim() !== s.text.trim() && (
                      <span className="segment-subtitle">{subtitleText}</span>
                    )}
                    {showSubtitlePlaceholder && (
                      <span className="segment-subtitle segment-subtitle-pending" aria-label="translating subtitle">
                        <span className="subtitle-loading-dot" />
                        <span className="subtitle-loading-dot" />
                        <span className="subtitle-loading-dot" />
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
            {shouldShowPreviewStack && (
              <div className="preview-stack" aria-live="polite" aria-label="实时预览逐字稿">
                {departingPreviewSegments.map((segment, index) => {
                  const previewDelayMs = index * PREVIEW_ROW_STAGGER_MS;
                  const previewStyle: StaggerStyle = {
                    "--preview-status-delay": `${previewDelayMs}ms`,
                    "--preview-text-delay": `${previewDelayMs + PREVIEW_CELL_STAGGER_MS}ms`,
                  };
                  return (
                  <div key={`leaving-${segment.id}`} className="segment preview-segment preview-age-0 preview-leaving" style={previewStyle} aria-hidden="true">
                    <span className="preview-status">
                      <span className="preview-hearing">
                        <span className="preview-pulse-dot" aria-hidden="true" />
                        Listening
                      </span>
                    </span>
                    <span className="preview-segment-text">{segment.text}</span>
                  </div>
                  );
                })}
                {previewSegments.length > 0 && previewSegments.map((segment, index) => {
                  const isNewest = index === previewSegments.length - 1;
                  const age = previewSegments.length - index - 1;
                  const displayText = isNewest
                    ? previewDisplayText ?? (previewIsStreaming ? "" : segment.text)
                    : segment.text;
                  const showCursor = isNewest && !previewIsStreaming && previewDisplayText !== null;
                  const previewDelayMs = (departingPreviewSegments.length + index) * PREVIEW_ROW_STAGGER_MS;
                  const previewStyle: StaggerStyle = {
                    "--preview-status-delay": `${previewDelayMs}ms`,
                    "--preview-text-delay": `${previewDelayMs + PREVIEW_CELL_STAGGER_MS}ms`,
                  };
                  return (
                    <div key={segment.id} className={`segment preview-segment preview-age-${Math.min(age, 4)}`} style={previewStyle}>
                      <span className="preview-status">
                        <span className="preview-hearing">
                          <span className="preview-pulse-dot" aria-hidden="true" />
                          Listening
                        </span>
                        {isExperimentalPreview && (
                          <span
                            className="preview-experimental-badge"
                            title="Qwen3 fast preview · text is live and may still change"
                          >
                            Qwen · Live
                          </span>
                        )}
                      </span>
                      <span className="preview-segment-text">
                        {displayText}
                        {showCursor && <span className="preview-cursor" aria-hidden="true" />}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            <div ref={transcriptBottomRef} className="transcript-bottom-anchor" />
            {!transcriptAutoFollow && (
              <button
                type="button"
                className="jump-latest-btn"
                onClick={() => {
                  transcriptAutoFollowRef.current = true;
                  setTranscriptAutoFollow(true);
                  scrollTranscriptToBottom("smooth");
                }}
              >
                跳到最新
              </button>
            )}
          </div>
        </section>}

        <section className="panel workspace">
          <div className="workspace-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "summary"}
              className={`workspace-tab-btn${activeTab === "summary" ? " active" : ""}`}
              onClick={() => setActiveTab("summary")}
            >
              摘要
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "clean"}
              className={`workspace-tab-btn${activeTab === "clean" ? " active" : ""}`}
              onClick={() => setActiveTab("clean")}
            >
              整理笔记
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "board"}
              className={`workspace-tab-btn${activeTab === "board" ? " active" : ""}`}
              onClick={() => setActiveTab("board")}
            >
              看板
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "notes"}
              className={`workspace-tab-btn${activeTab === "notes" ? " active" : ""}`}
              onClick={() => setActiveTab("notes")}
            >
              笔记与导出
            </button>
          </div>
          <div className="workspace-content">
            {activeTab === "summary" && (
              <SummaryPanel
                compact
                title="自动摘要"
                subtitle="定期整理最近几分钟内容；不是完整逐字稿"
                snapshot={rolling}
                history={historyByType.rolling_summary ?? []}
                sessionStartedAt={sessionStartedAt}
                accent="#2563eb"
                onSaveToNotes={handleSaveToNotes}
                onRefresh={() => handleRefreshSummary("rolling_summary")}
                refreshDisabled={!connected || state !== "running" || segments.length === 0}
                refreshBusy={refreshingSummary === "rolling_summary"}
              />
            )}
            {activeTab === "clean" && (
              <SummaryPanel
                compact
                title="整理笔记"
                subtitle="根据已识别文字整理；完整内容请看左侧逐字稿"
                snapshot={refined}
                history={historyByType.refined_transcript ?? []}
                sessionStartedAt={sessionStartedAt}
                accent="#7c3aed"
                onSaveToNotes={handleSaveToNotes}
                onRefresh={() => handleRefreshSummary("refined_transcript")}
                refreshDisabled={!connected || state !== "running" || segments.length === 0}
                refreshBusy={refreshingSummary === "refined_transcript"}
              />
            )}
            {activeTab === "board" && (
              <SummaryPanel
                compact
                title="内容看板"
                subtitle="主题 · 决定 · 待办 · 待解问题"
                snapshot={cumulative}
                history={historyByType.cumulative_meeting_summary ?? []}
                sessionStartedAt={sessionStartedAt}
                accent="#0f766e"
                onSaveToNotes={handleSaveToNotes}
                onRefresh={() => handleRefreshSummary("cumulative_meeting_summary")}
                refreshDisabled={!connected || state !== "running" || segments.length === 0}
                refreshBusy={refreshingSummary === "cumulative_meeting_summary"}
              />
            )}
            {activeTab === "notes" && (
              <div className="workspace-tab-panel">
                <div ref={notesBodyRef} className="panel-body">
                  <div className="export-box">
                    <div>
                      <strong>导出录音文件</strong>
                      <p className="muted">在选定文件夹中生成完整逐字稿 transcript.md、摘要 summary.md 和元数据 metadata.json。</p>
                      <div className="export-target-row">
                        <input
                          type="text"
                          value={exportRoot}
                          onChange={(e) => setExportRoot(e.target.value)}
                          placeholder="默认：项目 exports 文件夹中的时间戳目录"
                          aria-label="导出文件夹"
                        />
                        {window.meetingbro?.selectExportDirectory && (
                          <button type="button" className="secondary-export-btn" onClick={handleChooseExportFolder} disabled={exporting}>
                            浏览…
                          </button>
                        )}
                      </div>
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 12 }}>
                        <input
                          type="checkbox"
                          checked={bilingualExport}
                          onChange={(e) => setBilingualExport(e.target.checked)}
                        />
                        双语逐字稿（原文 + 翻译）
                      </label>
                      {lastExport && (
                        <p className="export-path">
                          最近导出：<code>{lastExport.export_dir}</code>
                        </p>
                      )}
                      {(exporting || actionFeedback) && exportIntent !== "restart" && (
                        <p className={`action-feedback ${exporting ? "is-busy" : "is-success"}`}>
                          {exporting ? "正在准备逐字稿、摘要和元数据…" : actionFeedback}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      className={`primary-export-btn ${exporting && exportIntent === "manual" ? "button-busy" : ""}`.trim()}
                      onClick={handleExportMeeting}
                      disabled={!meetingId || exporting}
                      aria-busy={exporting && exportIntent === "manual"}
                    >
                      {exporting ? "正在导出…" : "导出 Markdown"}
                    </button>
                  </div>
                  {chapterSnapshot && (
                    <div>
                      <strong>章节</strong>
                      {chapters.length === 0 ? (
                        <p className="muted">暂无章节。</p>
                      ) : (
                        <ul className="notes-list">
                          {chapters.map((chapter, index) => (
                            <li key={`chapter-${index}`}>
                              <div className="note-meta">
                                <span>{formatRange(Number(chapter.time_start ?? 0), Number(chapter.time_end ?? 0))}</span>
                              <span>{String(chapter.title ?? "未命名章节")}</span>
                              </div>
                              <div>{String(chapter.summary ?? "")}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {actionItemSnapshot && (
                    <div>
                      <strong>待办事项</strong>
                      {actionItems.length === 0 ? (
                        <p className="muted">暂无待办事项。</p>
                      ) : (
                        <ul className="notes-list">
                          {actionItems.map((item, index) => (
                            <li key={`action-${index}`}>
                              <div>{String(item.text ?? "")}</div>
                              <div className="note-meta">
                                <span>{item.assignee ? `负责人：${String(item.assignee)}` : "未分配"}</span>
                                <span>{item.due ? `截止：${String(item.due)}` : "无截止日期"}</span>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {notes.length === 0 ? (
                    <p className="muted">暂无已保存笔记。可在摘要面板点击“保存最新内容”。</p>
                  ) : (
                    <ul className="notes-list">
                      {notes.map((n) => (
                        <li key={n.id}>
                          <div className="note-meta">
                            <span>{n.source_type ?? "笔记"}</span>
                            <span className="muted">
                              {new Date(n.created_at).toLocaleTimeString()}
                            </span>
                          </div>
                          <div>{n.content}</div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
      </main>

      <div className="diagnostics-section">
        <button
          type="button"
          className="diagnostics-toggle"
          onClick={() => setDiagnosticsOpen((o) => !o)}
          aria-expanded={diagnosticsOpen}
          aria-controls="diagnostics-drawer"
        >
          <span className="diagnostics-toggle-label">系统状态</span>
          <span className={`health-badge health-${systemAdviceTone}`}>
            {systemAdviceTone === "ok" ? "正常" : systemAdviceTone === "warn" ? "请检查" : "警报"}
          </span>
          {elapsedSeconds > 0 && (
            <span className="diagnostics-toggle-elapsed">{formatElapsedSeconds(elapsedSeconds)}</span>
          )}
          <span className={`toggle-caret${diagnosticsOpen ? " open" : ""}`} aria-hidden="true">▼</span>
        </button>
        {diagnosticsOpen && (
          <div id="diagnostics-drawer" className="diagnostics-drawer">
            <div className="diagnostics-body">
              <div className={`diagnostic-card advice-card advice-${systemAdviceTone}`}>
                <span className="diagnostic-label">系统建议</span>
                <div className="advice-list">
                  {systemAdvice.map((item) => (
                    <div key={`${item.title}-${item.detail}`} className={`advice-item advice-${item.severity}`}>
                      <strong>{item.title}</strong>
                      <span>{item.detail}</span>
                      {item.action && <em>{item.action}</em>}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  className="diagnostics-mode-toggle"
                  onClick={() => setDiagnosticsMode((m) => (m === "simple" ? "advanced" : "simple"))}
                >
                  {diagnosticsMode === "simple" ? "显示详细状态" : "隐藏详细状态"}
                </button>
              </div>
              {diagnosticsMode === "advanced" && (<>
              <div className="diagnostic-card">
                <span className="diagnostic-label">当前录音来源</span>
                <strong className="diagnostic-value">{formatSourceLabel(activeSource)}</strong>
                <span className="diagnostic-note">
                  {activeSource === "mixed"
                    ? "同时采集系统声音和麦克风"
                    : activeSource === "loopback" || activeSource === "system"
                      ? "仅采集系统声音"
                      : "仅采集麦克风"}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">运行模式</span>
                <strong className="diagnostic-value">{formatRuntimeProfileLabel(activeRuntimeProfile)}</strong>
                <span className="diagnostic-note">
                  音频块 {formatLagSeconds(activeChunkSeconds)} · 识别窗口 {formatLagSeconds(activeAccumSeconds)} · 语言锁定 {languageLockEnabled ? "开" : "关"}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">硬件配置</span>
                <strong className="diagnostic-value">{activeHardwareProfile}</strong>
                <span className="diagnostic-note">{activeHardwareSummary}</span>
                {computeGpuAvailable && !computeGpuConfigured && (
                  <span className="diagnostic-note diagnostic-hint">GPU 可用，但未用于语音识别</span>
                )}
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">计算任务</span>
                <strong className="diagnostic-value">{computeCpuActive || computeGpuActive ? "运行中" : "空闲"}</strong>
                <span className="diagnostic-note">{computeActivityLabel}</span>
              </div>
              <div className={`diagnostic-card delay-card delay-${resourcePressureLevel === "critical" ? "danger" : resourcePressureLevel === "pressure" ? "warn" : "ok"}`}>
                <span className="diagnostic-label">资源调节</span>
                <strong className="diagnostic-value">{resourcePressureLevel}</strong>
                <span className="diagnostic-note">
                  {resourceGovernorPolicy} ? skips {resourceGovernorSkips}
                  {resourceGovernorReason ? ` ? ${resourceGovernorReason}` : ""}
                </span>
              </div>
              <div className={`diagnostic-card gain-card gain-${mixedGainTone}`}>
                <span className="diagnostic-label">混合音量</span>
                <strong className="diagnostic-value">{mixedGainRatio}</strong>
                <span className="diagnostic-note">
                  {activeSource === "mixed"
                    ? `mic effective ${formatGain(mixedEffectiveMicGain)} · base ${formatGain(mixedMicGain)} · auto ${mixedAutoBalanceEnabled ? "on" : "off"}`
                    : mixedGainHint}
                </span>
                {activeSource === "mixed" && (
                  <span className="diagnostic-note diagnostic-hint">{mixedGainHint}</span>
                )}
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">翻译字幕</span>
                <strong className="diagnostic-value">{subtitleStatus}</strong>
                <span className="diagnostic-note">{subtitleStatusDetail}</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">音频进度</span>
                <strong className="diagnostic-value">{formatElapsedSeconds(audioClockSeconds)}</strong>
                <span className="diagnostic-note">{elapsedSeconds > 0 ? "后端进度" : "前端估计"}</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">已确认逐字稿</span>
                <strong className="diagnostic-value">{formatElapsedSeconds(visibleTranscriptSeconds)}</strong>
                <span className="diagnostic-note">{latestSegment ? `最近确认 · ${formatRange(latestSegment.start_time, latestSegment.end_time)}` : "等待识别文字"}</span>
              </div>
              <div className={`diagnostic-card delay-card delay-${delayTone}`}>
                <span className="diagnostic-label">实时延迟</span>
                <strong className="diagnostic-value">{formatLagSeconds(transcriptLagSeconds)}</strong>
                <span className="diagnostic-note">音频进度与最新文字的时间差</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">确认耗时</span>
                <strong className="diagnostic-value">{formatLagSeconds(committedLagSeconds)}</strong>
                <span className="diagnostic-note">
                  {committedLagSeconds != null
                    ? "参考值：确认时间减去片段结束时间"
                    : "等待识别文字"}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">重试统计</span>
                <strong className="diagnostic-value">{retryTotal}</strong>
                <span className="diagnostic-note">改善 {retryImproved} · 不变 {retryUnchanged} · 偏离 {retryDiverged}</span>
              </div>
              <div className={`diagnostic-card delay-card delay-${asrSafeguardActive ? "danger" : (asrRealtimeFactor != null && asrRealtimeFactor > 0.8 ? "warn" : "ok")}`}>
                <span className="diagnostic-label">识别速度</span>
                <strong className="diagnostic-value">{formatRtf(asrRealtimeFactor)}</strong>
                <span className="diagnostic-note">
                  音频 {formatLagSeconds(asrAudioSeconds)} · 识别耗时 {formatLagSeconds(asrWallSeconds)}
                </span>
              </div>
              <div className={`diagnostic-card delay-card delay-${fastPreviewRtf != null && fastPreviewRtf > 0.8 ? "warn" : "ok"}`}>
                <span className="diagnostic-label">快速预览</span>
                <strong className="diagnostic-value">{fastPreviewEnabled ? formatRtf(fastPreviewRtf) : "关闭"}</strong>
                <span className="diagnostic-note">
                  已显示 {fastPreviewEmitted} · 已跳过 {fastPreviewSkipped}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">实时处理状态</span>
                <strong className="diagnostic-value">q {eventQueueDepth}</strong>
                <span className="diagnostic-note">
                  audio wait {formatLagSeconds(audioQueueWaitSeconds)} · preview wake {formatLagSeconds(fastPreviewScheduleDelay)} · concat {formatLagSeconds(snapshotConcatWall)}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">预览持续更新</span>
                <strong className="diagnostic-value">{previewContinuedDuringFormal}</strong>
                <span className="diagnostic-note">等待正式文字时 Qwen 的预览更新次数</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">过期预览已抑制</span>
                <strong className="diagnostic-value">{previewStaleSuppressed}</strong>
                <span className="diagnostic-note">已被正式文字覆盖的预览数</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">预览对齐</span>
                <strong className="diagnostic-value">
                  {previewAlignmentCompared > 0
                    ? `平均 ${(previewAlignmentSimilarityAvg ?? 0).toFixed(2)}`
                    : "—"}
                </strong>
                <span className="diagnostic-note">
                  对比 {previewAlignmentCompared} 次 · 最近 {previewAlignmentSimilarityLast != null ? previewAlignmentSimilarityLast.toFixed(2) : "—"}
                </span>
              </div>
              <div className={`diagnostic-card delay-card delay-${previewUnconfirmedAfterFormal > 0 ? "warn" : "ok"}`}>
                <span className="diagnostic-label">未确认预览</span>
                <strong className="diagnostic-value">{previewUnconfirmedAfterFormal}</strong>
                <span className="diagnostic-note">
                  {previewUnconfirmedLastText ? `最近：${previewUnconfirmedLastText}` : "没有未被正式文字覆盖的预览"}
                </span>
              </div>
              <div className={`diagnostic-card delay-card delay-${qwenTargetedRetryFailed > 0 ? "warn" : "ok"}`}>
                <span className="diagnostic-label">Qwen 补救</span>
                <strong className="diagnostic-value">{qwenTargetedRetryRecovered}</strong>
                <span className="diagnostic-note">
                  尝试 {qwenTargetedRetryAttempts} · 失败 {qwenTargetedRetryFailed} · 跳过 {qwenTargetedRetrySkipped}
                  {qwenTargetedRetryLastReason ? ` · ${qwenTargetedRetryLastReason}` : ""}
                </span>
              </div>
              <div className={`diagnostic-card delay-card delay-${asrSafeguardActive ? "danger" : "ok"}`}>
                <span className="diagnostic-label">实时保护</span>
                <strong className="diagnostic-value">{asrSafeguardActive ? "已启用" : "未启用"}</strong>
                <span className="diagnostic-note">
                  {asrSafeguardActive
                    ? "正在保护实时处理链路"
                    : `事件 ${asrSafeguardEvents} 次`}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">弱语音补救</span>
                <strong className="diagnostic-value">{weakRescueAttempts}</strong>
                <span className="diagnostic-note">
                  已输出 {weakRescueEmitted} · 缓冲 {formatLagSeconds(weakRescueBufferSeconds)}
                </span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">后台任务队列</span>
                <strong className="diagnostic-value">{translationPendingCount + summaryPendingCount}</strong>
                <span className="diagnostic-note">
                  翻译 {translationPendingCount} · 摘要 {summaryPendingCount} · 略过 {translationTrimTotal}
                </span>
              </div>
              <div className={`diagnostic-card delay-card delay-${audioInputBacklogSeconds >= 5 ? "warn" : "ok"}`}>
                <span className="diagnostic-label">等待识别的音频</span>
                <strong className="diagnostic-value">{formatLagSeconds(audioInputBacklogSeconds)}</strong>
                <span className="diagnostic-note">输入队列丢失 {audioInputQueueDropTotal} 个片段</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">采集丢失</span>
                <strong className="diagnostic-value">{audioDropTotal}</strong>
                <span className="diagnostic-note">采集队列丢失的音频片段</span>
              </div>
              <div className="diagnostic-card">
                <span className="diagnostic-label">处理压力</span>
                <strong className="diagnostic-value">{backpressureAgeSeconds != null ? "最近出现" : "正常"}</strong>
                <span className="diagnostic-note">
                  {backpressureAgeSeconds != null
                    ? `${formatLagSeconds(backpressureAgeSeconds)} 前出现，录音进度 ${formatElapsedSeconds(sessionStats?.last_backpressure_elapsed_seconds)}`
                    : "最近没有识别过慢事件"}
                </span>
              </div>
              </>)}
            </div>
          </div>
        )}
      </div>

      {restartPromptOpen && (
        <div className="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="restart-dialog-title">
          <div className="confirm-dialog">
            <h3 id="restart-dialog-title">开始新录音？</h3>
            <p>
              开始新录音会清空当前页面显示的逐字稿、摘要、书签和笔记。
            </p>
            <p className="muted">
              如果需要保留文件，请先导出当前录音。
            </p>
            <div className="confirm-actions">
              <button type="button" className="secondary-action-btn" onClick={() => setRestartPromptOpen(false)} disabled={exporting}>
                取消
              </button>
              <button type="button" className="danger-action-btn" onClick={handleRestartWithoutSave} disabled={exporting}>
                不保存，直接开始
              </button>
              <button type="button" className={`primary-export-btn ${exporting && exportIntent === "restart" ? "button-busy" : ""}`.trim()} onClick={handleSaveAndRestart} disabled={exporting} aria-busy={exporting && exportIntent === "restart"}>
                {exporting ? "保存中…" : "保存并开始新录音"}
              </button>
            </div>
            {(exporting || actionFeedback) && (
              <p className={`confirm-status ${exporting ? "is-busy" : "is-success"}`}>
                {exporting ? "正在导出当前录音，随后开始新录音…" : actionFeedback}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
