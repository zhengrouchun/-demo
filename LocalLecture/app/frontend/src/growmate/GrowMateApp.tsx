import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Home, Forest } from "./HomeForest";
import { Focus } from "./Focus";
import { Records } from "./Records";
import { Companion, Settings } from "./CompanionSettings";
import type { AppState, Page, Voice } from "./types";
import "./GrowMate.css";

const NAV: { id: Page; label: string; icon: string }[] = [{ id: "home", label: "首页", icon: "🏡" }, { id: "focus", label: "专注", icon: "⏱️" }, { id: "forest", label: "森林", icon: "🌳" }, { id: "records", label: "记录", icon: "📝" }, { id: "companion", label: "陪伴", icon: "🐶" }];

export default function GrowMateApp() {
  const [page, setPage] = useState<Page>("home");
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [socketConnected, setSocketConnected] = useState(false);
  const stateRef = useRef(state); stateRef.current = state;
  useEffect(() => { if (state?.timer?.mode === "strict") setPage("focus"); }, [state?.timer?.session_id]);
  const toastTimeout = useRef<number>();
  const refresh = useCallback(async () => { const next = await api<AppState>("/state"); setState(next); setError(""); }, []);
  const run = useCallback(async (operation: () => Promise<unknown>, success?: string): Promise<boolean> => {
    try { await operation(); await refresh(); if (success) { setToast(success); window.clearTimeout(toastTimeout.current); toastTimeout.current = window.setTimeout(() => setToast(""), 5000); } return true; }
    catch (err) { setError(err instanceof Error ? err.message : "操作失败，请稍后再试。"); return false; }
  }, [refresh]);
  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let reconnect: number | undefined;
    const load = () => { refresh().catch(() => { if (alive) setError("无法连接本地服务。请启动 GrowMate；若服务已启动，请刷新页面。"); }); };
    load();
    const poll = window.setInterval(load, 5000);
    const connect = () => {
      if (!alive) return;
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/voice/socket`);
      ws.onopen = () => { if (alive) setSocketConnected(true); };
      ws.onmessage = event => { try { const data = JSON.parse(event.data); if (alive && data.type === "voice_snapshot") setState(current => current ? { ...current, voice: data.payload as Voice } : current); } catch { /* ignore a malformed transport message */ } };
      ws.onclose = () => { if (alive) { setSocketConnected(false); reconnect = window.setTimeout(connect, 3000); } };
    };
    connect();
    return () => { alive = false; window.clearInterval(poll); window.clearTimeout(reconnect); ws?.close(); window.clearTimeout(toastTimeout.current); };
  }, [refresh]);

  useEffect(() => {
    const heartbeat = () => { const current = stateRef.current; if (current?.timer && (current.timer.mode !== "strict" || !document.hidden)) api("/focus/heartbeat", {}).catch(() => {}); };
    const interrupt = () => { if (stateRef.current?.timer?.mode === "strict") { fetch("/api/focus/interrupt", { method: "POST", headers: { "X-GrowMate-Request": "1" }, keepalive: true }).then(refresh).catch(() => {}); } };
    const visibility = () => { if (document.hidden) interrupt(); else { heartbeat(); refresh().catch(() => {}); } };
    const fullscreen = () => { if (!document.fullscreenElement) interrupt(); };
    const timer = window.setInterval(heartbeat, 5000);
    document.addEventListener("visibilitychange", visibility);
    document.addEventListener("fullscreenchange", fullscreen);
    window.addEventListener("pagehide", interrupt);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", visibility); document.removeEventListener("fullscreenchange", fullscreen); window.removeEventListener("pagehide", interrupt); };
  }, [refresh]);

  const navigate = useCallback((next: Page) => {
    if (stateRef.current?.timer?.mode === "strict" && next !== "focus") {
      if (!window.confirm("离开严格专注会导致小树生命值减一，确定离开？")) return;
      run(() => api("/focus/interrupt", {})).then(ok => { if (ok) { setPage(next); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); } });
    } else setPage(next);
  }, [run]);

  if (!state) return <div className="growmate gm-loading"><span>🐶🌱</span><h1>GrowMate</h1><p>{error || "正在打开你的森林…"}</p><button onClick={() => run(refresh)}>重新连接</button><p className="gm-muted">请先双击“启动GrowMate网页版.cmd”。</p></div>;
  const props = { state, navigate, run, refresh };
  return <div className="growmate"><aside className="gm-sidebar"><div className="gm-brand"><span>🐶</span><div><strong>GrowMate</strong><small>小狗陪你慢慢成长</small></div></div><nav aria-label="主导航">{NAV.map(n => <button key={n.id} className={page === n.id ? "selected" : ""} onClick={() => navigate(n.id)}><span>{n.icon}</span>{n.label}{n.id === "records" && !state.voice.resources_released && <i className="gm-recording-dot" aria-label="正在转写" />}</button>)}</nav><div className="gm-sidebar-bottom"><span>💧 {state.water_balance} 滴水</span><small>{socketConnected ? "本地服务已连接" : "正在恢复实时连接…"}</small><button className={page === "settings" ? "selected" : ""} onClick={() => navigate("settings")}>⚙️ 设置</button></div></aside><main className="gm-main"><div className="gm-mobile-brand"><strong>🐶 GrowMate</strong><button className="gm-text-button" onClick={() => navigate("settings")}>⚙️ 设置</button></div>{error && <div className="gm-error-banner" role="alert"><span>{error}</span><button onClick={() => setError("")}>关闭提示</button></div>}{page === "home" ? <Home {...props} /> : page === "focus" ? <Focus {...props} /> : page === "forest" ? <Forest {...props} /> : page === "records" ? <Records {...props} /> : page === "companion" ? <Companion {...props} /> : <Settings {...props} />}<footer className="gm-footer">GrowMate · 记录保存在这台电脑上</footer></main>{toast && <div className="gm-toast" role="status">✓ {toast}</div>}<nav className="gm-bottom-nav" aria-label="移动主导航">{NAV.map(n => <button key={n.id} className={page === n.id ? "selected" : ""} onClick={() => navigate(n.id)}><span>{n.icon}</span>{n.label}</button>)}</nav></div>;
}
