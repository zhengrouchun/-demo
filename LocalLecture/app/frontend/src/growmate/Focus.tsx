import { useEffect, useState } from "react";
import { api, dateTime, time } from "./api";
import { Card, Empty } from "./components";
import type { ViewProps } from "./types";

export function Focus({ state, run, navigate }: ViewProps) {
  const [mode, setMode] = useState("normal"), [minutes, setMinutes] = useState(25), [rest, setRest] = useState(5), [cycles, setCycles] = useState(3);
  const [taskId, setTaskId] = useState(""), [now, setNow] = useState(Date.now());
  const [starting, setStarting] = useState(false), [deciding, setDeciding] = useState(false);
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 250); return () => window.clearInterval(id); }, []);
  const timer = state.timer, result = state.focus_result;
  const effectiveMode = timer?.mode ?? mode;
  const resultTask = state.notes.flatMap(note => note.tasks ?? []).find(task => task.id === result?.task_id);
  const choices = state.notes.flatMap(note => (note.tasks ?? []).map((task, index) => ({ id: task.id, label: note.title + " · " + task.text + "（第 " + (index + 1) + " 条）" })));
  useEffect(() => { if (taskId && !choices.some(task => task.id === taskId)) setTaskId(""); }, [choices.map(task => task.id).join(","), taskId]);
  const remaining = timer ? Math.max(0, (Date.parse(timer.deadline) - now) / 1000) : minutes * 60;
  const duration = timer ? (timer.phase === "rest" ? timer.rest : timer.minutes) * 60 : minutes * 60;
  async function decide(completed: boolean) {
    if (!result || deciding) return;
    setDeciding(true);
    try { await run(() => api(`/focus/${result.id}/task-decision`, { completed }), completed ? "学习任务已完成，首次奖励已按记录结算。" : "已保留任务当前状态。"); }
    finally { setDeciding(false); }
  }
  return <>
    <div className="gm-heading"><div><p className="gm-eyebrow">给自己一段不被打扰的时间</p><h1>专注一会儿</h1></div><span className="gm-water">💧 {state.water_balance}</span></div>
    <div className="gm-two-columns">
      <Card className="gm-timer-card">
        <div className="gm-mode-label">{timer ? timer.phase === "rest" ? "休息时间" : timer.mode === "strict" ? "严格专注" : timer.mode === "pomodoro" ? "番茄钟" : "普通专注" : "小狗准备陪你学习"}</div>
        {timer?.task_id && <p className="gm-muted">正在专注：{timer.task_text}</p>}
        <div className="gm-timer-ring" style={{ background: `conic-gradient(var(--gm-green) ${100 * (1 - remaining / duration)}%, #e8ecdf 0)` }}><div><span>🐶</span><strong aria-live="off">{time(remaining)}</strong><small>{timer ? `第 ${timer.cycle} / ${timer.cycles} 轮` : "准备开始"}</small></div></div>
        {timer ? <><p className="gm-muted">{timer.phase === "rest" ? "休息结束后会开始下一轮。" : "倒计时完成后自动记入专注记录，水滴进入库存。"}</p><button className="gm-secondary" onClick={() => { if (window.confirm(timer.mode === "strict" ? "离开专注会导致小树生命值减一，确定结束？" : "提前结束本轮不会获得水滴，确定结束？")) run(() => api("/focus/interrupt", {})); }}>结束本次专注</button></> : <button disabled={starting} onClick={async () => {
          setStarting(true);
          try {
            if (mode === "strict") { try { await document.documentElement.requestFullscreen(); } catch { /* Existing visibility/heartbeat checks remain active. */ } }
            await run(() => api("/focus/start", { mode, minutes, rest, cycles, task_id: taskId || null }), "专注开始了，小狗会陪着你。");
          } finally { setStarting(false); }
        }}>{starting ? "正在开始…" : "开始专注"}</button>}
      </Card>
      <div className="gm-stack">
        <Card title="按自己的节奏">
          <div className="gm-segmented">{[["normal", "普通倒计时"], ["pomodoro", "番茄钟"], ["strict", "严格模式"]].map(([key, label]) => <button disabled={!!timer} key={key} className={effectiveMode === key ? "selected" : ""} onClick={() => setMode(key)}>{label}</button>)}</div>
          <label>绑定学习任务<select value={timer?.task_id ?? taskId} disabled={!!timer} onChange={e => setTaskId(e.target.value)}><option value="">不绑定任务</option>{timer?.task_id && !choices.some(task => task.id === timer.task_id) && <option value={timer.task_id}>{timer.task_text}（任务已移除）</option>}{choices.map(task => <option value={task.id} key={task.id}>{task.label}</option>)}</select></label>
          <label>专注时间（分钟）<input type="number" min="1" max="180" disabled={!!timer} value={timer?.minutes ?? minutes} onChange={e => setMinutes(Number(e.target.value))} /></label>
          {effectiveMode === "pomodoro" && <div className="gm-form-grid"><label>休息时间（分钟）<input type="number" min="1" max="60" disabled={!!timer} value={timer?.rest ?? rest} onChange={e => setRest(Number(e.target.value))} /></label><label>循环次数<input type="number" min="1" max="12" disabled={!!timer} value={timer?.cycles ?? cycles} onChange={e => setCycles(Number(e.target.value))} /></label></div>}
          <p className="gm-muted">少于 10 分钟不给水滴。10 / 25 / 45 / 60 / 90 分钟分别获得 2 / 6 / 12 / 18 / 30 滴，其他时间按比例计算。绑定学习任务的有效专注额外 +1 滴，每轮仅发放一次。</p>
          {effectiveMode === "strict" && <p className="gm-strict-notice">严格模式会检测切换标签页、关闭页面及离开全屏。中断后不给水滴，当前小树生命值减一。请先处理好其他事情。</p>}
        </Card>
        {result && <Card title="最近一次专注">
          <p>{result.message}</p>
          {result.task_id && !result.task_decision && <div className="gm-task-focus-result"><strong>{result.task_text}</strong><p>本次专注完成 {result.minutes} 分钟。专注结束不会自动勾选任务。</p><div className="gm-inline-actions"><button disabled={deciding} onClick={() => decide(true)}>完成任务</button><button className="gm-secondary" disabled={deciding} onClick={() => decide(false)}>{resultTask?.completed ? "保持当前状态" : "继续保持未完成"}</button></div></div>}
          {result.task_decision && <p className="gm-muted">{result.task_decision === "complete" ? "已确认完成学习任务。" : "已保留任务当前状态。"}</p>}
          <button className="gm-secondary" onClick={() => navigate("forest")}>去看小树</button>
        </Card>}
      </div>
    </div>
    <Card title="专注足迹">{state.focus_sessions.length ? <div className="gm-ledger">{state.focus_sessions.slice(0, 10).map(s => <div key={s.id}><span>{s.mode === "strict" ? "严格专注" : s.mode === "pomodoro" ? "番茄钟" : "普通专注"}{s.task_text && <small>学习任务：{s.task_text}</small>}<small>{dateTime(s.started_at)} · {Math.floor(s.actual_seconds / 60)} 分钟</small></span><strong>{s.completed ? `完成 · +${s.water_earned} 💧` : s.interrupted ? "已中断" : state.timer?.session_id === s.id ? "进行中" : "提前结束"}</strong></div>)}</div> : <Empty>第一次专注，会成为这里的第一段足迹。</Empty>}</Card>
  </>;
}
