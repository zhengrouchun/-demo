import { useCallback, useEffect, useState } from "react";
import {
  deleteMeeting,
  exportMeetingById,
  fetchMeetings,
  fetchMeetingNotes,
  fetchMeetingSummaries,
  fetchMeetingTranscript,
  type MeetingListItem,
} from "../system/backendApi";
import type { Note, SummarySnapshot, TranscriptSegment } from "../types";

interface HistoryModalProps {
  open: boolean;
  onClose: () => void;
  currentMeetingId?: string | null;
}

interface MeetingDetail {
  transcript: TranscriptSegment[];
  summaries: SummarySnapshot[];
  notes: Note[];
}

// Most-useful cumulative summary to show as the meeting overview, best first.
const OVERVIEW_PRIORITY: SummarySnapshot["summary_type"][] = [
  "final_summary",
  "cumulative_meeting_summary",
  "rolling_summary",
];

function formatStartedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(startedAt: string, endedAt: string | null): string | null {
  if (!endedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(endedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return null;
  const totalSeconds = Math.round((end - start) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

function pickOverview(summaries: SummarySnapshot[]): SummarySnapshot | null {
  for (const type of OVERVIEW_PRIORITY) {
    const match = summaries.filter((s) => s.summary_type === type).at(-1);
    if (match) return match;
  }
  return summaries.at(-1) ?? null;
}

export function HistoryModal({ open, onClose, currentMeetingId }: HistoryModalProps) {
  const [meetings, setMeetings] = useState<MeetingListItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(() => {
    setListError(null);
    fetchMeetings()
      .then(setMeetings)
      .catch((err) => {
        setMeetings([]);
        setListError((err as Error).message);
      });
  }, []);

  useEffect(() => {
    if (!open) return;
    setSelectedId(null);
    setDetail(null);
    setActionNote(null);
    loadList();
  }, [open, loadList]);

  const openDetail = useCallback((id: string) => {
    setSelectedId(id);
    setDetail(null);
    setActionNote(null);
    setDetailLoading(true);
    Promise.all([fetchMeetingTranscript(id), fetchMeetingSummaries(id), fetchMeetingNotes(id)])
      .then(([transcript, summaries, notes]) => setDetail({ transcript, summaries, notes }))
      .catch((err) => setActionNote(`无法加载录音：${(err as Error).message}`))
      .finally(() => setDetailLoading(false));
  }, []);

  const onExport = useCallback(async (id: string) => {
    setBusy(true);
    setActionNote(null);
    try {
      const result = await exportMeetingById(id);
      setActionNote(`已导出到 ${result.export_dir}`);
    } catch (err) {
      setActionNote(`导出失败：${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const onDelete = useCallback(
    async (id: string) => {
      if (!window.confirm("删除这条录音及其所有逐字稿、摘要和笔记？删除后无法恢复。")) {
        return;
      }
      setBusy(true);
      setActionNote(null);
      try {
        await deleteMeeting(id);
        if (selectedId === id) {
          setSelectedId(null);
          setDetail(null);
        }
        loadList();
      } catch (err) {
        setActionNote(`删除失败：${(err as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [selectedId, loadList],
  );

  if (!open) return null;

  const overview = detail ? pickOverview(detail.summaries) : null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="录音历史" onClick={onClose}>
      <div className="modal modal--history" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h2>录音历史</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="modal__body history__body">
          <div className="history__list">
            {meetings === null && <p className="history__empty">加载中…</p>}
            {meetings !== null && meetings.length === 0 && (
              <p className="history__empty">
                {listError ? `无法加载历史记录：${listError}` : "暂无历史录音。"}
              </p>
            )}
            {meetings?.map((m) => {
              const duration = formatDuration(m.started_at, m.ended_at);
              const isCurrent = currentMeetingId === m.id;
              return (
                <button
                  key={m.id}
                  type="button"
                  className={`history__item${selectedId === m.id ? " selected" : ""}`}
                  onClick={() => openDetail(m.id)}
                >
                  <span className="history__item-title">{m.title || "（暂无逐字稿）"}</span>
                  <span className="history__item-meta">
                    {formatStartedAt(m.started_at)}
                    {" · "}
                    {m.segment_count} 条转录
                    {duration ? ` · ${duration}` : isCurrent ? " · 进行中" : ""}
                    {isCurrent ? " · 当前录音" : ""}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="history__detail">
            {selectedId === null && <p className="history__empty">选择一条录音，查看逐字稿和摘要。</p>}
            {selectedId !== null && detailLoading && <p className="history__empty">正在加载录音…</p>}
            {selectedId !== null && !detailLoading && detail && (
              <>
                <div className="history__detail-actions">
                  <button type="button" onClick={() => onExport(selectedId)} disabled={busy}>导出</button>
                  <button type="button" className="history__delete" onClick={() => onDelete(selectedId)} disabled={busy}>删除</button>
                </div>
                {overview && (
                  <section className="history__section">
                    <h3>摘要</h3>
                    <p className="history__summary">{overview.content}</p>
                  </section>
                )}
                {detail.notes.length > 0 && (
                  <section className="history__section">
                    <h3>笔记</h3>
                    <ul className="history__notes">
                      {detail.notes.map((n) => <li key={n.id}>{n.content || `（${n.source_type ?? "笔记"}）`}</li>)}
                    </ul>
                  </section>
                )}
                <section className="history__section">
                  <h3>逐字稿</h3>
                  {detail.transcript.length === 0 ? (
                    <p className="history__empty">这条录音暂无逐字稿。</p>
                  ) : (
                    <div className="history__transcript">
                      {detail.transcript.map((seg) => <p key={seg.id}>{seg.text}</p>)}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
        {actionNote && <div className="modal__footer"><span className="history__note">{actionNote}</span></div>}
      </div>
    </div>
  );
}
