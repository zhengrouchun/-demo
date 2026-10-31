import { DEFAULT_SETTINGS, PET_CONFIG } from "./petConfig";
import type { PetSettings, Position } from "./petState";

export const SETTINGS_KEY = "desktopPet.settings";
const GREETING_KEY = "desktopPet.greetingDate";
type StorageLike = Pick<Storage, "getItem" | "setItem">;
const greetingFallback = new Set<string>();
function storage(kind: "localStorage" | "sessionStorage"): StorageLike | null {
  try { return window[kind]; } catch { return null; }
}
export function clampPosition(position: Position, width: number, height: number, viewWidth: number, viewHeight: number): Position {
  const finite = (n: number) => Number.isFinite(n) ? n : 0;
  return { x: Math.max(0, Math.min(finite(position.x), Math.max(0, viewWidth - width))), y: Math.max(0, Math.min(finite(position.y), Math.max(0, viewHeight - height))) };
}
export function defaultPosition(width: number, height: number, viewWidth: number, viewHeight: number): Position {
  return clampPosition({ x: viewWidth - width - PET_CONFIG.position.margin, y: viewHeight - height - (viewWidth <= PET_CONFIG.size.mobileBreakpoint ? PET_CONFIG.position.mobileBottom : PET_CONFIG.position.margin) }, width, height, viewWidth, viewHeight);
}
export function loadPetSettings(source = storage("localStorage")): PetSettings {
  try {
    const raw: unknown = JSON.parse(source?.getItem(SETTINGS_KEY) ?? "null");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ...DEFAULT_SETTINGS };
    const value = raw as Record<string, unknown>;
    const settings = { ...DEFAULT_SETTINGS };
    for (const key of ["enabled", "visible", "randomActions", "dialogueBubble", "autoSleep", "walkEnabled"] as const) if (typeof value[key] === "boolean") settings[key] = value[key];
    if (typeof value.scale === "number" && Number.isFinite(value.scale)) settings.scale = Math.max(PET_CONFIG.scale.min, Math.min(PET_CONFIG.scale.max, value.scale));
    const p = value.position as Record<string, unknown> | undefined;
    if (p && typeof p.x === "number" && Number.isFinite(p.x) && typeof p.y === "number" && Number.isFinite(p.y)) settings.position = { x: p.x, y: p.y };
    if (typeof value.lastDirectAt === "number" && Number.isFinite(value.lastDirectAt)) settings.lastDirectAt = value.lastDirectAt;
    return settings;
  } catch { return { ...DEFAULT_SETTINGS }; }
}
export function savePetSettings(settings: PetSettings, target = storage("localStorage")) {
  try { target?.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* Private mode or full storage: this page still works. */ }
}
export function consumeGreeting(date = new Date(), target = storage("sessionStorage")) {
  const day = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
  if (greetingFallback.has(day)) return false;
  try { if (target?.getItem(GREETING_KEY) === day) return false; target?.setItem(GREETING_KEY, day); } catch { /* Use in-memory session fallback. */ }
  greetingFallback.add(day);
  return true;
}
