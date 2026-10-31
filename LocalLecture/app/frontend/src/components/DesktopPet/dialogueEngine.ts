import { getTimeContext, PET_CONFIG } from "./petConfig";
import { PET_DIALOGUES } from "./petDialogues";
import type { Dialogue, DialogueCategory, PetContext, PetState } from "./petState";

export interface DialogueContext {
  currentTime: Date; clickCount: number; idleDuration: number; currentState: PetState;
  lastDialogue: string | null; lastCategory: DialogueCategory | null;
  recentDialogues: readonly string[]; lastDirectAt: number | null; context?: PetContext;
}
function chooseWeighted<T>(items: readonly { value: T; weight: number }[], random: () => number): T {
  const total = items.reduce((sum, item) => sum + item.weight, 0);
  let remaining = random() * total;
  for (const item of items) { remaining -= item.weight; if (remaining < 0) return item.value; }
  return items[items.length - 1].value;
}
export function selectDialogue(context: DialogueContext, random = Math.random): Dialogue {
  const time = getTimeContext(context.currentTime);
  const weights: { value: DialogueCategory; weight: number }[] = Object.entries(PET_CONFIG.dialogue.weights).map(([value, weight]) => ({ value: value as DialogueCategory, weight }));
  const direct = weights.find(item => item.value === "direct")!;
  if (context.lastDirectAt !== null && context.currentTime.getTime() - context.lastDirectAt < PET_CONFIG.dialogue.directCooldown) direct.weight = 0;
  if (context.clickCount >= PET_CONFIG.dialogue.repeatedClick) { weights[0].weight += PET_CONFIG.dialogue.repeatedMinimalBoost; direct.weight = 0; }
  if (context.idleDuration >= PET_CONFIG.dialogue.longIdle) weights.push({ value: time === "LATE_NIGHT" ? "lateNight" : "daily", weight: PET_CONFIG.dialogue.longIdleBoost });
  if (context.context && context.context !== "daily") weights.push({ value: context.context, weight: PET_CONFIG.dialogue.contextBoost });
  let category = chooseWeighted(weights.filter(item => item.weight > 0), random);
  if (category === "coding" && !context.context) {
    category = chooseWeighted(Object.entries(PET_CONFIG.dialogue.encouragementWeights).map(([value, weight]) => ({ value: value as DialogueCategory, weight })), random);
  } else if (category === "care" && random() < PET_CONFIG.dialogue.careDailyChance) category = "daily";
  const pool = PET_DIALOGUES[category].filter(text => time === "LATE_NIGHT" || text !== "……又熬夜。");
  const recent = new Set([...context.recentDialogues, context.lastDialogue].filter(Boolean));
  let candidates = pool.filter(text => !recent.has(text));
  if (!candidates.length) { category = "minimal"; candidates = PET_DIALOGUES.minimal.filter(text => !recent.has(text)); }
  if (!candidates.length) candidates = PET_DIALOGUES.minimal.filter(text => text !== context.lastDialogue);
  const text = chooseWeighted(candidates.map(value => ({ value, weight: value === "别闹。" && context.clickCount >= PET_CONFIG.dialogue.repeatedClick ? PET_CONFIG.dialogue.repeatedLineWeight : 1 })), random);
  return { text, category };
}
