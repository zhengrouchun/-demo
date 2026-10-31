import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { PET_CONFIG, getTimeContext, petSize } from "./petConfig";
import { GREETINGS } from "./petDialogues";
import { PetController } from "./petActions";
import { usePetAsset } from "./petAssets";
import { clampPosition, consumeGreeting, defaultPosition, loadPetSettings, savePetSettings } from "./petStorage";
import { PetBubble } from "./PetBubble";
import { PetMenu } from "./PetMenu";
import type { PetSettings, Position } from "./petState";
import "./styles.css";

function viewport() { return { width: window.innerWidth, height: window.innerHeight }; }
function usableHeight(view: ReturnType<typeof viewport>) { return Math.max(0, view.height - (view.width <= PET_CONFIG.size.mobileBreakpoint ? PET_CONFIG.position.mobileNavigation : 0)); }
type Update = (patch: Partial<PetSettings>) => void;
interface Drag { id: number; element: HTMLButtonElement; startX: number; startY: number; origin: Position; moved: boolean }

function ActivePet({ settings, update }: { settings: PetSettings; update: Update }) {
  const [view, setView] = useState(viewport);
  const size = petSize(view.width, usableHeight(view), settings.scale);
  const [position, setPosition] = useState(() => settings.position ? clampPosition(settings.position, size.width, size.height, view.width, usableHeight(view)) : defaultPosition(size.width, size.height, view.width, view.height));
  const positionRef = useRef(position);
  const settingsRef = useRef(settings); settingsRef.current = settings;
  const root = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const drag = useRef<Drag | null>(null);
  const moveFrame = useRef<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [controller] = useState(() => new PetController(settings, undefined, stamp => update({ lastDirectAt: stamp })));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const source = usePetAsset(snapshot.state);
  const move = useCallback((next: Position) => {
    positionRef.current = next;
    if (root.current) root.current.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`;
    setPosition(next); update({ position: next });
  }, [update]);
  const closeMenu = useCallback(() => { setMenuOpen(false); menuButton.current?.focus(); }, []);

  useEffect(() => {
    controller.start();
    const greetingFrame = window.requestAnimationFrame(() => {
      if (!settingsRef.current.dialogueBubble || !consumeGreeting()) return;
      const lines = GREETINGS[getTimeContext()];
      controller.greet({ text: lines[Math.floor(Math.random() * lines.length)], category: "daily" });
    });
    const activity = (event: Event) => {
      if (event.target instanceof Element && event.target.closest("[data-desktop-pet]")) return;
      controller.activity();
    };
    for (const name of ["pointermove", "pointerdown", "keydown", "scroll"] as const) document.addEventListener(name, activity, { passive: true, capture: true });
    const pause = () => { controller.setMenuOpen(document.hidden); if (!document.hidden) controller.activity(); };
    document.addEventListener("visibilitychange", pause);
    return () => {
      window.cancelAnimationFrame(greetingFrame);
      if (moveFrame.current !== null) window.cancelAnimationFrame(moveFrame.current);
      const current = drag.current;
      drag.current = null;
      if (current?.element.hasPointerCapture(current.id)) current.element.releasePointerCapture(current.id);
      for (const name of ["pointermove", "pointerdown", "keydown", "scroll"] as const) document.removeEventListener(name, activity, true);
      document.removeEventListener("visibilitychange", pause);
      controller.stop();
    };
  }, [controller]);
  useEffect(() => { controller.updateOptions(settings); }, [controller, settings]);
  useEffect(() => { controller.setMenuOpen(menuOpen); }, [controller, menuOpen]);
  useEffect(() => {
    const resize = () => {
      const nextView = viewport();
      const nextSize = petSize(nextView.width, usableHeight(nextView), settingsRef.current.scale);
      setView(nextView);
      move(clampPosition(positionRef.current, nextSize.width, nextSize.height, nextView.width, usableHeight(nextView)));
    };
    resize(); window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [settings.scale, move]);
  useEffect(() => {
    if (!menuOpen) return;
    const outside = (e: PointerEvent) => { if (e.target instanceof Element && !e.target.closest("[data-desktop-pet]")) closeMenu(); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") closeMenu(); };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [menuOpen, closeMenu]);
  function pointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || drag.current) return;
    controller.preparePointer(); setMenuOpen(false);
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, element: event.currentTarget, startX: event.clientX, startY: event.clientY, origin: { ...positionRef.current }, moved: false };
  }
  function pointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    const dx = event.clientX - current.startX, dy = event.clientY - current.startY;
    if (!current.moved && Math.hypot(dx, dy) < PET_CONFIG.interaction.dragThreshold) return;
    if (!current.moved) { current.moved = true; controller.beginDrag(); }
    positionRef.current = clampPosition({ x: current.origin.x + dx, y: current.origin.y + dy }, size.width, size.height, view.width, usableHeight(view));
    if (moveFrame.current === null) moveFrame.current = window.requestAnimationFrame(() => {
      moveFrame.current = null;
      const next = positionRef.current;
      if (root.current) root.current.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`;
    });
  }
  function pointerEnd(event: ReactPointerEvent<HTMLButtonElement>, cancelled = false) {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    drag.current = null;
    if (moveFrame.current !== null) window.cancelAnimationFrame(moveFrame.current);
    moveFrame.current = null;
    if (current.element.hasPointerCapture(current.id)) current.element.releasePointerCapture(current.id);
    if (current.moved) { move(positionRef.current); controller.endDrag(); }
    else if (!cancelled) controller.queueClick();
  }
  const hide = () => update({ visible: false });
  const reset = () => { move(defaultPosition(size.width, size.height, view.width, view.height)); closeMenu(); };
  const style = { width: size.width, height: size.height, transform: `translate3d(${position.x}px, ${position.y}px, 0)`, "--pet-image-size": `${size.width}px`, "--pet-layer": PET_CONFIG.layer } as CSSProperties;
  return <div className="desktop-pet-layer" data-desktop-pet><div ref={root} className="desktop-pet" style={style} data-state={snapshot.state} data-click-count={snapshot.clickCount}>
    <button className="gsp-character" aria-label="顾时夜，点击互动，拖动可移动位置" title="点击回应 · 拖动换个位置" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={e => pointerEnd(e)} onPointerCancel={e => pointerEnd(e, true)} onLostPointerCapture={e => pointerEnd(e, true)} onDragStart={e => e.preventDefault()} onClick={e => { if (e.detail === 0) { controller.preparePointer(); controller.queueClick(); } }} onDoubleClick={e => e.preventDefault()} onKeyDown={e => {
      const step = PET_CONFIG.interaction.keyboardStep;
      const offsets: Record<string, Position> = { ArrowLeft: { x: -step, y: 0 }, ArrowRight: { x: step, y: 0 }, ArrowUp: { x: 0, y: -step }, ArrowDown: { x: 0, y: step } };
      const offset = offsets[e.key];
      if (offset) { e.preventDefault(); controller.activity(); move(clampPosition({ x: position.x + offset.x, y: position.y + offset.y }, size.width, size.height, view.width, usableHeight(view))); }
    }}>{source ? <img className="gsp-image" src={source} alt="黑发黑色长外套的顾时夜 Q 版小人" draggable={false} /> : <span className="gsp-asset-fallback" role="img" aria-label="顾时夜">顾</span>}{snapshot.state === "sleep" && <span className="gsp-sleep-mark" aria-hidden="true">z z</span>}</button>
    <div className="gsp-toolbar"><span>顾时夜</span><button ref={menuButton} className="gsp-icon" aria-label="打开桌宠设置" aria-expanded={menuOpen} onClick={() => setMenuOpen(open => !open)}>⋯</button><button className="gsp-icon" aria-label="隐藏顾时夜" onClick={hide}>−</button></div>
  </div>{snapshot.bubble && <PetBubble bubble={snapshot.bubble} position={position} petWidth={size.width} petHeight={size.height} viewWidth={view.width} viewHeight={view.height} />}{menuOpen && <PetMenu settings={settings} position={position} petWidth={size.width} petHeight={size.height} viewWidth={view.width} viewHeight={view.height} onChange={update} onClose={closeMenu} onHide={hide} onReset={reset} onEncourage={context => { closeMenu(); controller.encourage(context); }} onWave={() => { closeMenu(); controller.preparePointer(); controller.requestAction("wave"); }} />}</div>;
}
export default function DesktopPet() {
  const [settings, setSettings] = useState(loadPetSettings);
  const settingsRef = useRef(settings);
  const update = useCallback<Update>(patch => { const next = { ...settingsRef.current, ...patch }; settingsRef.current = next; savePetSettings(next); setSettings(next); }, []);
  return createPortal(settings.enabled && settings.visible ? <ActivePet settings={settings} update={update} /> : <div className="desktop-pet-layer" data-desktop-pet><button className="gsp-recall" aria-label="召回顾时夜" title="让顾时夜回来" onClick={() => update({ enabled: true, visible: true })}>顾</button></div>, document.body);
}
