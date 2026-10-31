import { useState } from "react";
import { inline } from "./components";
import { dateOffset, dueLabel } from "./noteTaskData";
import type { NoteTask } from "./types";

const SUGGESTED = ["STM32", "Proteus", "ClearChain", "比赛", "Java"];
const splitTags = (text: string) => [...new Set(text.split(/[,，]/).map(tag => tag.trim()).filter(Boolean))];

export function NoteTaskRow({ task, today, disabled, activeTaskId, hasTimer, onToggle, onFocus, onSave }: {
  task: NoteTask; today: string; disabled: boolean; activeTaskId?: string | null; hasTimer: boolean;
  onToggle: (lineIndex: number, completed: boolean) => void;
  onFocus: (task: NoteTask) => void;
  onSave: (taskId: string, tags: string[], due: string | null) => Promise<boolean | undefined>;
}) {
  const [editing, setEditing] = useState(false), [tags, setTags] = useState(""), [due, setDue] = useState("");
  function open() { setTags(task.tags.join(", ")); setDue(task.due_date ?? ""); setEditing(true); }
  const overdue = !!task.due_date && task.due_date < today && !task.completed;
  return <div className="gm-learning-task" data-task-id={task.id}>
    <div className="gm-learning-task-main">
      <input type="checkbox" checked={task.completed} disabled={disabled} aria-label={task.text || "未命名任务"} onChange={e => onToggle(task.line_index, e.target.checked)} />
      <span className={`gm-task-text${task.completed ? " completed" : ""}`}>{inline(task.text)}</span>
      <button type="button" className="gm-text-button gm-task-focus" disabled={disabled || (hasTimer && activeTaskId !== task.id)} onClick={() => onFocus(task)}>{activeTaskId === task.id && hasTimer ? "查看专注" : "▶ 开始专注"}</button>
    </div>
    <div className="gm-task-details">
      {task.tags.map(tag => <span className="gm-task-tag" key={tag}>{tag}</span>)}
      {task.due_date && <span className={`gm-task-due${overdue ? " overdue" : ""}`} title={task.due_date}>{dueLabel(task.due_date, today, task.completed)}</span>}
      {task.focus_seconds > 0 && <span className="gm-task-time">⏱ 累计专注 {task.focus_seconds < 60 ? "不足 1" : Math.floor(task.focus_seconds / 60)} min</span>}
      {task.reward_awarded && <span className="gm-task-reward" title="同一任务首次完成的奖励已发放，再次勾选不重复发放">💧 已获 1 滴</span>}
      <button type="button" className="gm-text-button gm-task-edit" disabled={disabled} aria-label={`设置任务：${task.text}`} onClick={() => editing ? setEditing(false) : open()}>标签 / 日期</button>
    </div>
    {editing && <form className="gm-task-editor" onSubmit={async e => { e.preventDefault(); if (await onSave(task.id, splitTags(tags), due || null)) setEditing(false); }}>
      <label>任务标签<input value={tags} disabled={disabled} maxLength={400} placeholder="例如 STM32, Proteus，可用逗号分隔" onChange={e => setTags(e.target.value)} /></label>
      <div className="gm-task-tag-options">{SUGGESTED.map(tag => <button type="button" key={tag} disabled={disabled} className={`gm-secondary${splitTags(tags).includes(tag) ? " selected" : ""}`} onClick={() => { const current = splitTags(tags); setTags((current.includes(tag) ? current.filter(t => t !== tag) : [...current, tag]).join(", ")); }}>{tag}</button>)}</div>
      <label>截止日期<input type="date" disabled={disabled} value={due} onChange={e => setDue(e.target.value)} /></label>
      <div className="gm-inline-actions">{[["今天", today], ["明天", dateOffset(today, 1)], ["无日期", ""]].map(([label, value]) => <button type="button" key={label} disabled={disabled} className="gm-secondary" onClick={() => setDue(value)}>{label}</button>)}</div>
      <div className="gm-inline-actions"><button disabled={disabled}>保存任务信息</button><button type="button" disabled={disabled} className="gm-secondary" onClick={() => setEditing(false)}>取消</button></div>
    </form>}
  </div>;
}
