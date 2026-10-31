import type { ReactNode } from "react";
import type { AppState, Tree } from "./types";
import { markdownLines, type MarkdownLine } from "./markdownTasks";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return <section className={`gm-card ${className}`}>{title && <h2>{title}</h2>}{children}</section>;
}
export function Empty({ children }: { children: ReactNode }) { return <p className="gm-empty">{children}</p>; }
export function TreeScene({ tree, state, focusing = false }: { tree?: Tree; state: AppState; focusing?: boolean }) {
  const species = state.species.find(s => s.id === tree?.species_id);
  const symbol = !tree ? "🌰" : tree.status === "dead" ? "🍂" : tree.growth < 20 ? "🌰" : tree.growth < 150 ? "🌱" : tree.growth < 300 ? "🌳" : species?.emoji;
  return <div className={`gm-tree-scene ${tree?.status === "dead" ? "dead" : ""}`}><span className="gm-tree-symbol" role="img" aria-label={tree ? `${species?.name} ${tree.stage}` : "等待种植"}>{symbol}</span><span className="gm-dog" role="img" aria-label={focusing ? "小狗陪你专注" : "陪伴的小狗"}>{focusing ? "🐶📖" : "🐕"}</span><div className="gm-ground" /></div>;
}
export function TreeInfo({ tree, state }: { tree: Tree; state: AppState }) {
  return <><h2>{state.species.find(s => s.id === tree.species_id)?.name} · {tree.stage}</h2><p className="gm-hearts" aria-label={`生命值 ${tree.health} / 3`}>{"❤️".repeat(tree.health)}{"🖤".repeat(3 - tree.health)}</p><div className="gm-progress"><div style={{ width: `${tree.growth / 5}%` }} /></div><p className="gm-muted">成长 {tree.growth} / 500 · 累计浇水 {tree.total_water} 滴</p></>;
}

export function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => part.startsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part.startsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : part);
}
export function Markdown({ text, onTaskToggle, tasksDisabled = false, taskLines, renderTask }: { text: string; onTaskToggle?: (lineIndex: number, completed: boolean) => void; tasksDisabled?: boolean; taskLines?: MarkdownLine[]; renderTask?: (line: MarkdownLine) => ReactNode }) {
  // React escapes every text node. Raw HTML and external image URLs never render.
  let taskCursor = 0;
  return <div className="gm-markdown">{markdownLines(text).map(source => {
    const entry = source.task && taskLines ? taskLines[taskCursor++] : source;
    if (!entry) return null;
    const { text: line, index, code, fence, task } = entry;
    if (fence) return null;
    if (code) return <pre key={index}>{line || " "}</pre>;
    const image = line.match(/^!\[([^\]]*)\]\((\/api\/images\/[a-f0-9]{32}\.(?:png|jpg|gif|webp))\)$/);
    if (image) return <img key={index} src={image[2]} alt={image[1]} loading="lazy" />;
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) { const title = inline(heading[2]); return heading[1].length === 1 ? <h2 key={index}>{title}</h2> : <h3 key={index}>{title}</h3>; }
    if (task && renderTask) return <div key={`task-${index}`}>{renderTask(entry)}</div>;
    if (task) return <p className="gm-task" key={`task-${index}`}><input type="checkbox" checked={task.completed} disabled={tasksDisabled || !onTaskToggle} onChange={e => onTaskToggle?.(index, e.target.checked)} aria-label={task.text || `第 ${index + 1} 行任务`} /><span className={`gm-task-text${task.completed ? " completed" : ""}`}>{inline(task.text)}</span></p>;
    if (/^[-*] /.test(line)) return <p key={index}>• {inline(line.slice(2))}</p>;
    if (/^\d+\. /.test(line)) return <p key={index}>{inline(line)}</p>;
    if (line.startsWith("> ")) return <blockquote key={index}>{inline(line.slice(2))}</blockquote>;
    return line ? <p key={index}>{inline(line)}</p> : <div className="gm-md-space" key={index} />;
  })}</div>;
}
