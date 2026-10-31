export interface MarkdownTask { text: string; completed: boolean; markerOffset: number }
export interface MarkdownLine { text: string; index: number; code: boolean; fence: boolean; task?: MarkdownTask }

/** Share task recognition between preview and editing, so code examples stay untouched. */
export function markdownLines(markdown: string): MarkdownLine[] {
  let fence: { char: string; length: number } | undefined;
  return markdown.split("\n").map((raw, index) => {
    const text = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    const line: MarkdownLine = { text, index, code: false, fence: false };
    if (fence) {
      const closing = text.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/);
      if (closing && closing[1][0] === fence.char && closing[1].length >= fence.length) {
        fence = undefined; line.fence = true;
      } else line.code = true;
      return line;
    }
    const opening = text.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (opening && (opening[1][0] === "~" || !opening[2].includes("`"))) {
      fence = { char: opening[1][0], length: opening[1].length }; line.fence = true;
      return line;
    }
    // Four-space/tab-indented Markdown is code, not a clickable task.
    if (/^(?: {4}|\t)/.test(text)) { line.code = true; return line; }
    const match = text.match(/^( {0,3}- \[)([ xX])(\](?:[ \t]+(.*))?)$/);
    if (match) line.task = { text: match[4] ?? "", completed: match[2] !== " ", markerOffset: match[1].length };
    return line;
  });
}

/** Only replace the checkbox marker; preserve every task and all other Markdown bytes. */
export function setMarkdownTask(markdown: string, lineIndex: number, completed: boolean): string {
  if (!Number.isInteger(lineIndex) || lineIndex < 0) return markdown;
  const task = markdownLines(markdown)[lineIndex]?.task;
  if (!task || task.completed === completed) return markdown;
  const lines = markdown.split("\n"), line = lines[lineIndex];
  lines[lineIndex] = line.slice(0, task.markerOffset) + (completed ? "x" : " ") + line.slice(task.markerOffset + 1);
  return lines.join("\n");
}

/** Explicitly convert consecutive numbered lists; ordinary Markdown stays ordinary by default. */
export function numberedTaskConversion(markdown: string): { markdown: string; count: number } {
  const raw = markdown.split("\n"), replacements = new Map<number, string>();
  let group: { index: number; number: number; text: string }[] = [];
  const flush = () => {
    if (group.length >= 2) for (const line of group) replacements.set(line.index, line.text);
    group = [];
  };
  for (const line of markdownLines(markdown)) {
    if (!line.code && !line.fence && !line.text.trim()) continue;
    const match = !line.code && !line.fence && line.text.match(/^( {0,3})([1-9]\d{0,2})(?:[.)、．][ \t]*|(?=[\u3400-\u9fff]))(.+)$/);
    // Do not mistake dates/versions such as 10.3 or 1.2 for numbered items.
    if (!match || !match[3].trim() || /^\d/.test(match[3])) { flush(); continue; }
    const number = Number(match[2]);
    if (group.length && number !== group[group.length - 1].number + 1) flush();
    group.push({ index: line.index, number, text: match[1] + "- [ ] " + match[3] });
  }
  flush();
  for (const [index, text] of replacements) raw[index] = text + (raw[index].endsWith("\r") ? "\r" : "");
  return { markdown: raw.join("\n"), count: replacements.size };
}
