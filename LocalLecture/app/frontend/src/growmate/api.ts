export async function api<T = unknown>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`/api${path}`, { method: method ?? (body === undefined ? "GET" : "POST"), headers: { "Content-Type": "application/json", "X-GrowMate-Request": "1" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  if (!response.ok) {
    let message = `操作失败（${response.status}）`;
    try { const data = await response.json(); message = typeof data.detail === "string" ? data.detail : "请检查输入内容是否完整、数值是否正确。"; } catch { /* network response can be non-JSON */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export function time(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 3600)).padStart(2, "0")}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
export function dateTime(value: string): string { return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
