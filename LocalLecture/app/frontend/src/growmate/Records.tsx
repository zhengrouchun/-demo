import { useEffect, useRef, useState } from "react";
import { api, dateTime } from "./api";
import { Card, Empty, Markdown } from "./components";
import { VoiceRecorder } from "./Voice";
import { numberedTaskConversion, setMarkdownTask } from "./markdownTasks";
import { reconcileTasks, loadTaskView, taskProgress, presentTasks, type TaskView } from "./noteTaskData";
import { NoteTaskRow } from "./NoteTaskRow";
import type { HealthLog, ViewProps, Note, NoteTask } from "./types";

const MOODS = [["happy", "😄", "很开心"], ["good", "🙂", "不错"], ["normal", "😐", "一般"], ["sad", "😞", "难过"], ["tired", "😣", "很累"], ["angry", "😡", "生气"]];
const HEALTH_FIELDS = [["breakfast", "早餐"], ["lunch", "午餐"], ["dinner", "晚餐"], ["snacks", "零食与饮品"], ["stomach_note", "今日养胃记录"], ["general_note", "身体感受"]] as const;

export function Records(props: ViewProps) {
  const [tab, setTab] = useState("voice");
  return <><div className="gm-heading"><div><p className="gm-eyebrow">留住声音，也留住今天的自己</p><h1>我的记录</h1></div></div><div className="gm-tabs">{[["voice", "🎙️ 实时转文字"], ["notes", "📝 备忘录"], ["health", "🥣 养胃记录"], ["mood", "💚 心情日记"]].map(([key, label]) => <button key={key} className={tab === key ? "selected" : ""} onClick={() => setTab(key)}>{label}</button>)}</div>{tab === "voice" ? <VoiceRecorder {...props} /> : tab === "notes" ? <Notes {...props} /> : tab === "health" ? <Health {...props} /> : <Mood {...props} />}</>;
}

function Notes({ state, run, navigate }: ViewProps) {
  type Draft = { id?: string; title: string; markdown: string; tasks: NoteTask[]; updated_at?: string };
  const draftKey = "growmate.note-draft";
  const empty = (): Draft => ({ title: "", markdown: "", tasks: [] });
  const fromNote = (note: Note): Draft => ({ id: note.id, title: note.title, markdown: note.markdown, tasks: note.tasks ?? [], updated_at: note.updated_at });
  const [draft, setDraft] = useState<Draft>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(draftKey) ?? "null");
      if (!stored || typeof stored.title !== "string" || typeof stored.markdown !== "string") return empty();
      const saved = state.notes.find(note => note.id === stored.id);
      if (saved && (stored.unsaved === false || (stored.markdown === saved.markdown && stored.title === saved.title))) return fromNote(saved);
      return { id: stored.id, title: stored.title, markdown: stored.markdown, updated_at: stored.updated_at ?? saved?.updated_at, tasks: reconcileTasks(stored.markdown, Array.isArray(stored.tasks) ? stored.tasks : saved?.tasks ?? []) };
    } catch { return empty(); }
  });
  const [dirty, setDirty] = useState(() => draft.id
    ? !state.notes.some(n => n.id === draft.id && n.title === draft.title && n.markdown === draft.markdown)
    : !!(draft.title || draft.markdown));
  const [saving, setSaving] = useState(false), [view, setView] = useState<TaskView>(loadTaskView);
  const savingRef = useRef(false), input = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null), preview = useRef<HTMLHeadingElement>(null);
  const numbered = numberedTaskConversion(draft.markdown);
  const [settled, setSettled] = useState<Record<string, boolean>>(() => Object.fromEntries(draft.tasks.map(task => [task.id, task.completed])));
  const completionKey = draft.tasks.map(task => task.id + Number(task.completed)).join(",");
  useEffect(() => { const id = window.setTimeout(() => setSettled(Object.fromEntries(draft.tasks.map(task => [task.id, task.completed]))), 250); return () => window.clearTimeout(id); }, [completionKey]);
  useEffect(() => { try { localStorage.setItem(draftKey, JSON.stringify({ ...draft, unsaved: dirty })); } catch { /* SQLite remains available without localStorage. */ } }, [draft, dirty]);
  useEffect(() => { try { localStorage.setItem("growmate.note-task-view", JSON.stringify(view)); } catch { /* View options can remain session-only. */ } }, [view]);
  const tags = [...new Set(draft.tasks.flatMap(task => task.tags))].sort();
  useEffect(() => { if (view.tag && !tags.includes(view.tag)) setView(v => ({ ...v, tag: "" })); }, [tags.join("\u0000"), view.tag]);
  const progress = taskProgress(draft.tasks);
  const visibleTasks = presentTasks(draft.markdown, draft.tasks, view, settled);
  const taskByLine = new Map(draft.tasks.map(task => [task.line_index, task]));
  const savedTasks = new Map(state.notes.find(note => note.id === draft.id)?.tasks?.map(task => [task.id, task]) ?? []);
  function edit(field: "title" | "markdown", value: string) {
    if (savingRef.current) return;
    setDraft(d => ({ ...d, [field]: value, ...(field === "markdown" ? { tasks: reconcileTasks(value, d.tasks) } : {}) })); setDirty(true);
  }
  function adopt(note: Note, snapshot = draft) {
    const next = fromNote(note);
    try {
      const stored = JSON.parse(localStorage.getItem(draftKey) ?? "null");
      if (stored?.id === snapshot.id && stored?.title === snapshot.title && stored?.markdown === snapshot.markdown)
        localStorage.setItem(draftKey, JSON.stringify({ ...next, unsaved: false }));
    } catch { /* Saved to SQLite even if browser storage is unavailable. */ }
    setDraft(next); setDirty(false);
  }
  async function save(snapshot = draft) {
    const result = await api<{ id: string; note: Note }>("/notes", {
      id: snapshot.id, title: snapshot.title, markdown: snapshot.markdown, base_updated_at: snapshot.updated_at,
      task_links: snapshot.tasks.map(task => ({ id: task.id, line_index: task.line_index })),
    });
    adopt(result.note, snapshot);
    return result.note;
  }
  async function withSaving(operation: () => Promise<unknown>, success: string) {
    if (savingRef.current) return;
    savingRef.current = true; setSaving(true);
    try { return await run(operation, success); }
    finally { savingRef.current = false; setSaving(false); }
  }
  async function toggleTask(lineIndex: number, completed: boolean) {
    if (savingRef.current) return;
    const markdown = setMarkdownTask(draft.markdown, lineIndex, completed);
    if (markdown === draft.markdown) return;
    const next = { ...draft, markdown, tasks: reconcileTasks(markdown, draft.tasks) };
    setDraft(next); setDirty(true);
    await withSaving(() => save(next), "任务状态已保存。");
  }
  async function saveTaskInfo(taskId: string, taskTags: string[], due: string | null) {
    return withSaving(async () => {
      const note = await save();
      const updated = await api<Note>(`/notes/${note.id}/tasks/${taskId}`, { tags: taskTags, due_date: due }, "PATCH");
      adopt(updated, fromNote(note));
    }, "任务标签和日期已保存。");
  }
  async function focusTask(task: NoteTask) {
    if (state.timer?.task_id === task.id) { navigate("focus"); return; }
    if (state.timer) return;
    const ok = await withSaving(async () => {
      await save();
      await api("/focus/start", { mode: "normal", minutes: view.minutes, rest: 5, cycles: 1, task_id: task.id });
    }, "任务专注开始了。");
    if (ok) navigate("focus");
  }
  function showPreview() {
    window.requestAnimationFrame(() => {
      preview.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
      preview.current?.focus({ preventScroll: true });
    });
  }
  async function convertNumbered() {
    if (savingRef.current || !numbered.count) return;
    const next = { ...draft, markdown: numbered.markdown, tasks: reconcileTasks(numbered.markdown, draft.tasks) };
    setDraft(next); setDirty(true);
    const ok = await withSaving(() => save(next), `${numbered.count} 条编号内容已转为学习任务并保存。`);
    if (ok) showPreview();
  }
  function addTask() {
    if (savingRef.current) return;
    const prefix = draft.markdown + (draft.markdown && !draft.markdown.endsWith("\n") ? "\n" : "") + "- [ ] ";
    edit("markdown", prefix + "新任务\n");
    window.requestAnimationFrame(() => { editor.current?.focus(); editor.current?.setSelectionRange(prefix.length, prefix.length + 3); });
  }
  return <div className="gm-note-grid">
    <Card title="备忘录">
      <button className="gm-secondary" disabled={saving} onClick={() => { if (!savingRef.current && (!dirty || window.confirm("当前草稿尚未保存，确定新建？"))) { setDraft(empty()); setDirty(false); } }}>新建备忘录</button>
      <div className="gm-note-list">{state.notes.map(n => <button key={n.id} disabled={saving} className={draft.id === n.id ? "selected" : ""} onClick={() => { if (!savingRef.current && (!dirty || window.confirm("当前草稿尚未保存，确定切换？"))) { setDraft(fromNote(n)); setDirty(false); } }}><strong>{n.title}</strong><small>{dateTime(n.updated_at)}</small></button>)}</div>
      {!state.notes.length && <Empty>任务、学习笔记和临时想法，都可以写在这里。</Empty>}
    </Card>
    <Card>
      <label>标题<input maxLength={200} disabled={saving} placeholder="今天想记下什么？" value={draft.title} onChange={e => edit("title", e.target.value)} /></label>
      <div className="gm-inline-actions gm-note-task-tools">
        <button className="gm-secondary" disabled={saving} onClick={addTask}>＋ 添加任务</button>
        {!!numbered.count && <button className="gm-secondary gm-convert-tasks" disabled={saving} onClick={convertNumbered}>编号列表转为任务（{numbered.count}）</button>}
        <button className="gm-secondary gm-show-note-preview" disabled={saving} aria-controls="gm-note-preview" onClick={showPreview}>{progress.total ? `查看任务（${progress.total}）` : "查看预览"}</button>
      </div>
      {!!numbered.count && <p className="gm-muted gm-numbered-task-hint">检测到 {numbered.count} 条编号内容。点击“编号列表转为任务”即可变成可勾选清单，并保存当前备忘录；内容会保留。</p>}
      <label>Markdown 正文<textarea ref={editor} rows={14} disabled={saving} placeholder={"# 今天的任务\n\n- [ ] 完成作业\n- [ ] 给小树浇水"} value={draft.markdown} onChange={e => edit("markdown", e.target.value)} /></label>
      <p className="gm-muted">任务格式：<code>- [ ] 未完成</code> / <code>- [x] 已完成</code>。勾选、保存任务信息或开始专注时，会保存当前备忘录及正文修改。</p>
      <div className="gm-inline-actions">
        <button disabled={saving} onClick={() => withSaving(() => save(), "备忘录已保存到电脑。")}>{saving ? "正在保存…" : "保存备忘录"}</button>
        <button className="gm-secondary" disabled={saving} onClick={() => input.current?.click()}>添加图片</button>
        {draft.id && <><a className="gm-button gm-secondary" href={`/api/notes/${draft.id}/download`} download>导出 Markdown＋图片</a><button className="gm-text-button gm-delete" disabled={saving} onClick={() => { if (window.confirm("确定删除这份备忘录？")) withSaving(async () => { await api(`/notes/${draft.id}`, undefined, "DELETE"); setDraft(empty()); setDirty(false); }, "备忘录已删除。"); }}>删除</button></>}
      </div>
      <input ref={input} hidden type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={async e => {
        const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
        await withSaving(async () => {
          if (file.size > 5 * 1024 * 1024) throw new Error("每张图片最多 5 MB。");
          const note = await save();
          const response = await fetch(`/api/notes/${note.id}/images`, { method: "POST", headers: { "X-GrowMate-Request": "1" }, body: file });
          if (!response.ok) throw new Error("图片保存失败，请检查图片格式和大小。");
          const { uri } = await response.json();
          const markdown = `${note.markdown}\n\n![记录图片](${uri})\n`;
          await save({ ...fromNote(note), markdown, tasks: reconcileTasks(markdown, note.tasks) });
        }, "图片和备忘录已保存。");
      }} />
      <p className="gm-muted" role="status">{saving ? "正在保存到电脑…" : dirty ? "草稿未保存，请点击保存。" : "支持标题、粗体、列表、任务清单、代码与图片。"}图片保存在电脑文件夹中，数据库只记录路径。</p>
      <h3 id="gm-note-preview" ref={preview} tabIndex={-1}>任务与正文预览</h3>
      {!!progress.total && <div className="gm-task-overview">
        <div className="gm-task-progress-label"><strong>已完成 {progress.completed} / {progress.total}</strong><span>{progress.percent}%</span></div>
        <progress max={progress.total} value={progress.completed} aria-label="当前备忘录任务进度" />
        <div className="gm-task-filters">
          <label className="gm-checkbox"><input type="checkbox" checked={view.showCompleted} onChange={e => setView(v => ({ ...v, showCompleted: e.target.checked }))} />显示已完成</label>
          <label>任务顺序<select value={view.order} onChange={e => setView(v => ({ ...v, order: e.target.value as TaskView["order"] }))}><option value="original">原始顺序</option><option value="incomplete">未完成优先</option></select></label>
          <label>按标签筛选<select value={view.tag} onChange={e => setView(v => ({ ...v, tag: e.target.value }))}><option value="">全部标签</option>{tags.map(tag => <option key={tag}>{tag}</option>)}</select></label>
          <label>任务专注（分钟）<input type="number" min={1} max={180} value={view.minutes} onChange={e => { const minutes = Number(e.target.value); if (Number.isInteger(minutes) && minutes >= 1 && minutes <= 180) setView(v => ({ ...v, minutes })); }} /></label>
        </div>
        <p className="gm-task-hint">任务首次完成 +1 💧；有效任务专注额外 +1 💧。已获得 {state.water_balance} 滴，可去森林浇水。</p>
      </div>}
      <Markdown text={draft.markdown} onTaskToggle={toggleTask} tasksDisabled={saving} taskLines={visibleTasks} renderTask={line => {
        const task = taskByLine.get(line.index); if (!task) return null;
        const saved = savedTasks.get(task.id);
        return <NoteTaskRow key={task.id} task={{ ...task, focus_seconds: Math.max(task.focus_seconds, saved?.focus_seconds ?? 0), reward_awarded: task.reward_awarded || !!saved?.reward_awarded }} today={state.today} disabled={saving} activeTaskId={state.timer?.task_id} hasTimer={!!state.timer} onToggle={toggleTask} onFocus={focusTask} onSave={saveTaskInfo} />;
      }} />
      {!!progress.total && !visibleTasks.length && <Empty>当前筛选下没有任务，正文与任务数据仍保留。</Empty>}
    </Card>
  </div>;
}

function Health({ state, run }: ViewProps) {
  const [day, setDay] = useState(state.today);
  const empty = (date: string): HealthLog => ({ date, breakfast: "", lunch: "", dinner: "", snacks: "", stomach_note: "", general_note: "" });
  const [form, setForm] = useState<HealthLog>(state.health_logs.find(h => h.date === day) ?? empty(day));
  const [saving, setSaving] = useState(false);
  function chooseDate(date: string) { setDay(date); setForm(state.health_logs.find(h => h.date === date) ?? empty(date)); }
  return <div className="gm-two-columns"><Card title="今天有好好吃饭吗"><form onSubmit={async e => { e.preventDefault(); setSaving(true); await run(() => api("/health-log", { date: day, ...Object.fromEntries(HEALTH_FIELDS.map(([field]) => [field, form[field]])) }), "这一天的饮食与感受已保存。"); setSaving(false); }}><label>记录日期<input type="date" required value={day} onChange={e => chooseDate(e.target.value)} /></label><div className="gm-form-grid">{HEALTH_FIELDS.map(([field, label]) => <label key={field}>{label}<textarea rows={field === "stomach_note" || field === "general_note" ? 4 : 2} value={form[field]} onChange={e => setForm({ ...form, [field]: e.target.value })} /></label>)}</div><button disabled={saving}>{saving ? "正在保存…" : "保存养胃记录"}</button></form><p className="gm-muted">记录食物和身体感受，帮助你观察自己的生活习惯。</p></Card><Card title="过去的记录">{state.health_logs.map(h => <button className="gm-record-button" key={h.date} onClick={() => chooseDate(h.date)}><strong>{h.date}</strong><small>{h.stomach_note || h.general_note || h.breakfast || "已记录这一天"}</small></button>)}{!state.health_logs.length && <Empty>不用写得完美，记下真实的今天就好。</Empty>}</Card></div>;
}

function Mood({ state, run, navigate }: ViewProps) {
  const [mood, setMood] = useState("normal");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  return <div className="gm-two-columns"><Card title="今天过得怎么样"><div className="gm-moods">{MOODS.map(([key, emoji, label]) => <button key={key} className={mood === key ? "selected" : ""} onClick={() => setMood(key)}><span>{emoji}</span>{label}</button>)}</div><label>写几句话<textarea rows={8} value={content} onChange={e => setContent(e.target.value)} placeholder="发生了什么？现在是什么感受？" /></label><div className="gm-inline-actions"><button disabled={saving} onClick={async () => { setSaving(true); if (await run(() => api("/mood", { mood, content }), "今天的心情已记下。")) setContent(""); setSaving(false); }}>保存心情</button><button className="gm-secondary" onClick={() => navigate("companion")}>和小狗聊聊</button></div></Card><Card title="心情足迹">{state.mood_logs.map(m => <article className="gm-mood-entry" key={m.id}><strong>{MOODS.find(([key]) => key === m.mood)?.[1]} {MOODS.find(([key]) => key === m.mood)?.[2]}</strong><time>{dateTime(m.created_at)}</time><p>{m.content}</p></article>)}{!state.mood_logs.length && <Empty>每一种心情，都可以留在这里。</Empty>}</Card></div>;
}
