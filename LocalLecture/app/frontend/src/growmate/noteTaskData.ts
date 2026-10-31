import { markdownLines, type MarkdownLine } from "./markdownTasks";
import type { NoteTask } from "./types";

export interface TaskView { showCompleted: boolean; order: "original" | "incomplete"; tag: string; minutes: number }
export const defaultTaskView: TaskView = { showCompleted: true, order: "original", tag: "", minutes: 25 };
export function loadTaskView(): TaskView {
  try {
    const saved = JSON.parse(localStorage.getItem("growmate.note-task-view") ?? "null");
    return { showCompleted: typeof saved?.showCompleted === "boolean" ? saved.showCompleted : true, order: saved?.order === "incomplete" ? "incomplete" : "original", tag: typeof saved?.tag === "string" ? saved.tag : "", minutes: Number.isInteger(saved?.minutes) && saved.minutes >= 1 && saved.minutes <= 180 ? saved.minutes : 25 };
  } catch { return { ...defaultTaskView }; }
}
export function reconcileTasks(markdown: string, previous: NoteTask[], makeId = () => crypto.randomUUID().replace(/-/g, "")): NoteTask[] {
  const lines = markdownLines(markdown).filter(line => line.task);
  const assigned = new Map<number, NoteTask>(), used = new Set<string>();
  if (lines.length === previous.length) lines.forEach((line, index) => {
    if (line.task!.text === previous[index].text) { assigned.set(line.index, previous[index]); used.add(previous[index].id); }
  });
  lines.forEach(line => {
    if (assigned.has(line.index)) return;
    const old = previous.find(task => !used.has(task.id) && task.text === line.task!.text);
    if (old) { assigned.set(line.index, old); used.add(old.id); }
  });
  const leftLines = lines.filter(line => !assigned.has(line.index)), leftTasks = previous.filter(task => !used.has(task.id));
  if (leftLines.length === leftTasks.length) leftLines.forEach((line, index) => assigned.set(line.index, leftTasks[index]));
  return lines.map(line => ({
    ...(assigned.get(line.index) ?? { id: makeId(), tags: [], due_date: null, focus_seconds: 0, reward_awarded: false }),
    line_index: line.index, text: line.task!.text, completed: line.task!.completed,
  }));
}
export function taskProgress(tasks: NoteTask[]) {
  const completed = tasks.filter(task => task.completed).length;
  return { completed, total: tasks.length, percent: tasks.length ? Math.round(completed / tasks.length * 100) : 0 };
}
export function presentTasks(markdown: string, tasks: NoteTask[], view: TaskView, settled: Record<string, boolean>): MarkdownLine[] {
  const byLine = new Map(tasks.map(task => [task.line_index, task]));
  const completed = (line: MarkdownLine) => { const task = byLine.get(line.index); return task ? settled[task.id] ?? task.completed : line.task!.completed; };
  const lines = markdownLines(markdown).filter(line => line.task && (view.showCompleted || !completed(line)) && (!view.tag || byLine.get(line.index)?.tags.includes(view.tag)));
  if (view.order === "incomplete") lines.sort((a, b) => Number(completed(a)) - Number(completed(b)));
  return lines;
}
export function dateOffset(today: string, days: number) {
  const [year, month, day] = today.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}
export function dueLabel(due: string | null, today: string, completed: boolean) {
  if (!due) return "";
  if (!completed && due < today) return "已逾期";
  if (due === today) return "今天";
  if (due === dateOffset(today, 1)) return "明天";
  const [year, month, day] = due.split("-").map(Number);
  return (due.slice(0, 4) !== today.slice(0, 4) ? year + "年" : "") + month + "月" + day + "日";
}
