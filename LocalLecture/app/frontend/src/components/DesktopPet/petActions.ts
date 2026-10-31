import { PET_CONFIG } from "./petConfig";
import { selectDialogue } from "./dialogueEngine";
import { ACTIONS } from "./petState";
import type { Dialogue, PetContext, PetSettings, PetSnapshot, PetState } from "./petState";

export interface PetClock { now: () => number; random: () => number; setTimer: (callback: () => void, delay: number) => number; clearTimer: (id: number) => void }
const browserClock: PetClock = { now: Date.now, random: Math.random, setTimer: (fn, delay) => window.setTimeout(fn, delay), clearTimer: id => window.clearTimeout(id) };
type Options = Pick<PetSettings, "randomActions" | "dialogueBubble" | "autoSleep" | "walkEnabled" | "lastDirectAt">;

/** One scheduler owns action, inactivity, click and bubble deadlines. No React dependency. */
export class PetController {
  private snapshot: PetSnapshot = { state: "idle", bubble: null, clickCount: 0 };
  private listeners = new Set<() => void>();
  private running = false;
  private paused = false;
  private timer: number | null = null;
  private actionEnd = Infinity;
  private randomAt = Infinity;
  private bubbleAt = Infinity;
  private pendingClickAt = Infinity;
  private clickIdleDuration = 0;
  private lastClickAt = -Infinity;
  private lastUserActivity: number;
  private returnedAt = -Infinity;
  private previousIdle = 0;
  private recent: string[] = [];
  private lastDialogue: Dialogue | null = null;
  private bubbleId = 0;
  private options: Options;

  constructor(settings: Options, private clock = browserClock, private onDirect?: (stamp: number) => void) {
    this.options = { ...settings };
    this.lastUserActivity = clock.now();
  }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(update: Partial<PetSnapshot>) { this.snapshot = { ...this.snapshot, ...update }; this.listeners.forEach(listener => listener()); }
  private resetRandom() { this.randomAt = this.options.randomActions ? this.clock.now() + PET_CONFIG.randomAction.minDelay + this.clock.random() * (PET_CONFIG.randomAction.maxDelay - PET_CONFIG.randomAction.minDelay) : Infinity; }

  start(greeting?: Dialogue) {
    if (this.running) return;
    this.running = true;
    this.lastUserActivity = this.clock.now();
    this.resetRandom();
    if (greeting) this.showBubble(greeting);
    this.schedule();
  }
  greet(dialogue: Dialogue) { if (this.running) { this.showBubble(dialogue); this.schedule(); } }
  stop() {
    this.running = false;
    if (this.timer !== null) this.clock.clearTimer(this.timer);
    this.timer = null;
    this.actionEnd = this.randomAt = this.bubbleAt = this.pendingClickAt = Infinity;
    this.publish({ state: "idle", bubble: null, clickCount: 0 });
  }
  updateOptions(settings: Options) {
    const changedRandom = settings.randomActions !== this.options.randomActions;
    this.options = { ...settings };
    if (changedRandom) this.resetRandom();
    if (!settings.dialogueBubble) { this.bubbleAt = Infinity; this.publish({ bubble: null }); }
    if (!settings.autoSleep && this.snapshot.state === "sleep") this.wake();
    this.schedule();
  }
  setMenuOpen(open: boolean) { this.paused = open; this.activity(); if (!open) this.resetRandom(); this.schedule(); }
  activity() {
    const now = this.clock.now();
    const gap = now - this.lastUserActivity;
    if (gap >= PET_CONFIG.dialogue.longIdle) { this.previousIdle = gap; this.returnedAt = now; }
    this.lastUserActivity = now;
    // Ordinary pointer movements only update this timestamp; no render or timer per move.
    if (this.snapshot.state === "sleep") { this.wake(); this.schedule(); }
  }
  preparePointer() {
    const now = this.clock.now();
    this.clickIdleDuration = Math.max(0, now - this.lastUserActivity, now - this.returnedAt < PET_CONFIG.interaction.clickResetTime ? this.previousIdle : 0);
    this.activity();
  }
  private wake() { this.publish({ state: "idle" }); this.actionEnd = Infinity; this.resetRandom(); }
  private idle() { this.publish({ state: "idle" }); this.actionEnd = Infinity; this.resetRandom(); }

  requestAction(state: PetState): boolean {
    if (!this.running || this.snapshot.state === "drag") return false;
    // V0.2 extension points; no pretend walking or AI detection in V0.1.
    if (["walk", "work", "ai_chat"].includes(state)) return false;
    if (state === "sleep") {
      this.actionEnd = this.randomAt = this.pendingClickAt = Infinity;
      this.publish({ state: "sleep", bubble: null });
      this.bubbleAt = Infinity;
    } else {
      if (this.snapshot.state === "sleep") this.wake();
      if (ACTIONS[state].priority < ACTIONS[this.snapshot.state].priority) return false;
      this.publish({ state });
      this.actionEnd = ACTIONS[state].duration ? this.clock.now() + ACTIONS[state].duration : Infinity;
    }
    this.schedule();
    return true;
  }
  beginDrag() {
    if (!this.running) return;
    this.activity();
    this.actionEnd = this.randomAt = this.pendingClickAt = this.bubbleAt = Infinity;
    this.publish({ state: "drag", bubble: null });
    this.schedule();
  }
  endDrag() { if (this.snapshot.state === "drag") { this.activity(); this.idle(); this.schedule(); } }
  queueClick() {
    if (!this.running || this.snapshot.state === "drag") return;
    this.activity();
    if (this.pendingClickAt !== Infinity && this.clock.now() < this.pendingClickAt) {
      this.pendingClickAt = Infinity;
      this.respond(2, undefined, true);
    } else { this.pendingClickAt = this.clock.now() + PET_CONFIG.interaction.doubleClickTime; this.schedule(); }
  }
  encourage(context: PetContext) { this.preparePointer(); this.pendingClickAt = Infinity; this.respond(1, context); }
  private respond(count: number, context?: PetContext, double = false) {
    const now = this.clock.now();
    const clicks = now - this.lastClickAt >= PET_CONFIG.interaction.clickResetTime ? count : this.snapshot.clickCount + count;
    this.lastClickAt = now;
    this.publish({ clickCount: clicks });
    const dialogue = selectDialogue({ currentTime: new Date(now), clickCount: clicks, idleDuration: this.clickIdleDuration, currentState: this.snapshot.state, lastDialogue: this.lastDialogue?.text ?? null, lastCategory: this.lastDialogue?.category ?? null, recentDialogues: this.recent, lastDirectAt: this.options.lastDirectAt, context }, this.clock.random);
    this.lastDialogue = dialogue;
    this.recent = [...this.recent, dialogue.text].slice(-PET_CONFIG.dialogue.recentLimit);
    if (dialogue.category === "direct") { this.options.lastDirectAt = now; this.onDirect?.(now); }
    this.showBubble(dialogue);
    this.requestAction(double || clicks >= PET_CONFIG.dialogue.surpriseClick ? "surprise" : this.clock.random() < PET_CONFIG.interaction.touchWeight ? "touch" : "wave");
    this.schedule();
  }
  private showBubble(dialogue: Dialogue) {
    if (!this.options.dialogueBubble) return;
    this.publish({ bubble: { ...dialogue, id: ++this.bubbleId, phase: "enter" } });
    this.bubbleAt = this.clock.now() + PET_CONFIG.bubble.fadeDuration;
  }
  private tick = () => {
    this.timer = null;
    if (!this.running) return;
    const now = this.clock.now();
    if (this.snapshot.bubble && now >= this.bubbleAt) {
      const bubble = this.snapshot.bubble;
      if (bubble.phase === "enter") { this.publish({ bubble: { ...bubble, phase: "visible" } }); this.bubbleAt = now + PET_CONFIG.bubble.visibleDuration; }
      else if (bubble.phase === "visible") { this.publish({ bubble: { ...bubble, phase: "leave" } }); this.bubbleAt = now + PET_CONFIG.bubble.fadeDuration; }
      else { this.publish({ bubble: null }); this.bubbleAt = Infinity; }
    }
    if (now >= this.pendingClickAt) { this.pendingClickAt = Infinity; this.respond(1); }
    if (this.snapshot.clickCount && now - this.lastClickAt >= PET_CONFIG.interaction.clickResetTime) this.publish({ clickCount: 0 });
    if (now >= this.actionEnd) this.idle();
    if (!this.paused && this.snapshot.state === "idle") {
      if (this.options.autoSleep && now - this.lastUserActivity >= PET_CONFIG.sleep.timeout) this.requestAction("sleep");
      else if (now >= this.randomAt) { this.randomAt = Infinity; this.requestAction(this.clock.random() < PET_CONFIG.randomAction.blinkWeight ? "blink" : "wave"); }
    }
    this.schedule();
  };
  private schedule() {
    if (this.timer !== null) this.clock.clearTimer(this.timer);
    this.timer = null;
    if (!this.running) return;
    const deadlines = [this.actionEnd, this.bubbleAt, this.pendingClickAt];
    if (this.snapshot.clickCount) deadlines.push(this.lastClickAt + PET_CONFIG.interaction.clickResetTime);
    if (!this.paused && this.snapshot.state === "idle") {
      deadlines.push(this.randomAt);
      if (this.options.autoSleep) deadlines.push(this.lastUserActivity + PET_CONFIG.sleep.timeout);
    }
    const next = Math.min(...deadlines);
    if (Number.isFinite(next)) this.timer = this.clock.setTimer(this.tick, Math.max(1, next - this.clock.now()));
  }
}
