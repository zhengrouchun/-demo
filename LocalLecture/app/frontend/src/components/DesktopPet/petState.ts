import { PET_CONFIG } from "./petConfig";

export type PetState = "idle" | "blink" | "touch" | "wave" | "surprise" | "drag" | "sleep" | "walk" | "work" | "happy" | "angry" | "ai_chat";
export type DialogueCategory = "minimal" | "daily" | "care" | "coding" | "anxiety" | "lateNight" | "project" | "direct";
export type PetContext = "daily" | "coding" | "anxiety" | "project";
export type TimeContext = "MORNING" | "DAY" | "EVENING" | "LATE_NIGHT";
export interface Position { x: number; y: number }
export interface PetSettings {
  version: 1;
  enabled: boolean;
  visible: boolean;
  scale: number;
  randomActions: boolean;
  dialogueBubble: boolean;
  autoSleep: boolean;
  walkEnabled: boolean;
  position: Position | null;
  lastDirectAt: number | null;
}
export interface Dialogue { text: string; category: DialogueCategory }
export interface Bubble extends Dialogue { id: number; phase: "enter" | "visible" | "leave" }
export interface PetSnapshot { state: PetState; bubble: Bubble | null; clickCount: number }

export const ACTIONS: Record<PetState, { priority: number; duration: number }> = {
  idle: { priority: 0, duration: 0 }, blink: { priority: 10, duration: PET_CONFIG.action.blink },
  wave: { priority: 30, duration: PET_CONFIG.action.wave }, touch: { priority: 60, duration: PET_CONFIG.action.touch },
  surprise: { priority: 60, duration: PET_CONFIG.action.surprise }, drag: { priority: 100, duration: 0 },
  sleep: { priority: 0, duration: 0 }, walk: { priority: 20, duration: 0 },
  work: { priority: 20, duration: 0 }, happy: { priority: 60, duration: PET_CONFIG.action.happy },
  angry: { priority: 60, duration: PET_CONFIG.action.angry }, ai_chat: { priority: 60, duration: 0 },
};
