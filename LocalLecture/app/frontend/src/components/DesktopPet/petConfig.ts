import type { PetSettings, PetState, TimeContext } from "./petState";

export const PET_CONFIG = {
  name: "顾时夜",
  size: { desktop: 180, tablet: 150, mobile: 110, tabletBreakpoint: 1180, mobileBreakpoint: 680, toolbar: 30 },
  position: { margin: 20, mobileBottom: 86, mobileNavigation: 72 },
  scale: { min: 0.65, max: 1.4, step: 0.05 },
  action: { blink: 200, wave: 1400, touch: 1100, surprise: 1100, happy: 1200, angry: 1200 },
  randomAction: { minDelay: 8000, maxDelay: 25000, blinkWeight: 0.75 },
  sleep: { timeout: 300000 },
  bubble: { visibleDuration: 3000, fadeDuration: 200, maxWidth: 260, edge: 8, gap: 10 },
  interaction: { clickResetTime: 6000, doubleClickTime: 280, dragThreshold: 5, keyboardStep: 10, touchWeight: 0.75 },
  dialogue: { weights: { minimal: 50, coding: 25, care: 15, direct: 10 }, recentLimit: 4, directCooldown: 600000, longIdle: 600000, repeatedClick: 3, surpriseClick: 5, repeatedMinimalBoost: 55, longIdleBoost: 45, contextBoost: 80, repeatedLineWeight: 8, careDailyChance: 0.4, encouragementWeights: { coding: 88, anxiety: 9, project: 3 } },
  timeRanges: [
    { from: 360, until: 600, context: "MORNING" },
    { from: 600, until: 1080, context: "DAY" },
    { from: 1080, until: 1410, context: "EVENING" },
  ] as { from: number; until: number; context: TimeContext }[],
  walk: { enabled: false, maxDistance: 240, duration: 3500, frames: 4 },
  layer: 30,
} as const;

const BASE = "/pet/gushiye/";
export const PET_ASSETS: Record<PetState, string> = {
  idle: BASE + "idle.png", blink: BASE + "blink.png", touch: BASE + "touch.png",
  wave: BASE + "wave.png", surprise: BASE + "surprise.png", drag: BASE + "drag.png", sleep: BASE + "sleep.png",
  walk: BASE + "idle.png", work: BASE + "idle.png", happy: BASE + "touch.png", angry: BASE + "surprise.png", ai_chat: BASE + "idle.png",
};
export const WALK_FRAMES = [1, 2, 3, 4].map(i => `${BASE}walk-0${i}.png`);
export const DEFAULT_SETTINGS: PetSettings = { version: 1, enabled: true, visible: true, scale: 1, randomActions: true, dialogueBubble: true, autoSleep: true, walkEnabled: PET_CONFIG.walk.enabled, position: null, lastDirectAt: null };

export function getTimeContext(date = new Date()): TimeContext {
  const minute = date.getHours() * 60 + date.getMinutes();
  return PET_CONFIG.timeRanges.find(range => minute >= range.from && minute < range.until)?.context ?? "LATE_NIGHT";
}
export function petSize(viewWidth: number, viewHeight: number, scale: number) {
  const base = viewWidth <= PET_CONFIG.size.mobileBreakpoint ? PET_CONFIG.size.mobile : viewWidth <= PET_CONFIG.size.tabletBreakpoint ? PET_CONFIG.size.tablet : PET_CONFIG.size.desktop;
  const width = Math.max(32, Math.min(base * scale, viewWidth, viewHeight - PET_CONFIG.size.toolbar));
  return { width, height: width + PET_CONFIG.size.toolbar };
}
