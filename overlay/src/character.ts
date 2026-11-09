import spec from "../../design/character.json";

export const PARAM_KEYS = ["w", "h", "lid", "angle", "smile", "lookX", "lookY", "blush"] as const;
export type ParamKey = (typeof PARAM_KEYS)[number];
export type Params = Record<ParamKey, number>;

export const EXPRESSIONS = ["neutral", "happy", "listening", "thinking", "sad", "sleepy", "surprised", "annoyed"] as const;
export type Expression = (typeof EXPRESSIONS)[number];

export const MOODS = ["neutral", "happy", "sad", "surprised", "annoyed"] as const;
export type Mood = (typeof MOODS)[number];

export const STATES = ["idle", "listening", "thinking", "speaking", "sleeping"] as const;
export type BotState = (typeof STATES)[number];

export type ThemeName = "dark" | "light";
export type Theme = (typeof spec.themes)["dark"];

export interface Geometry {
  diameter: number;
  eye: { width: number; height: number; centerY: number; spacing: number };
  look: { maxX: number; maxY: number };
  blush: { width: number; height: number; offsetX: number; y: number };
  mouth: { width: number; minHeight: number; maxHeight: number; y: number };
}

export interface Motion {
  expressionTransitionMs: number;
  blink: { intervalMs: [number, number]; closeMs: number; holdMs: number; openMs: number; doubleBlinkChance: number };
  bob: { amplitudePx: number; periodMs: number };
  idleGlance: { afterCursorStillMs: number; intervalMs: [number, number] };
  sleep: { afterIdleMs: number };
}

export const geometry: Geometry = spec.geometry;
export const motion = spec.motion as Motion;
export const themes: Record<ThemeName, Theme> = spec.themes;
export const presets: Record<Expression, Params> = spec.expressions;

/** Lids that are nearly shut while asleep; the "sleepy" preset is the drowsy look, not sleep itself. */
const SLEEPING: Partial<Params> = { lid: 0.92, lookY: 0.4 };

/** Which face a state shows. While speaking the reply's mood decides, otherwise the state does. */
export function targetParams(state: BotState, mood: Mood): Params {
  switch (state) {
    case "idle":
      return presets.neutral;
    case "listening":
      return presets.listening;
    case "thinking":
      return presets.thinking;
    case "speaking":
      return presets[mood];
    case "sleeping":
      return { ...presets.sleepy, ...SLEEPING };
  }
}

/** How much the eyes follow the cursor in each state. Thinking and sleeping look inward. */
export const GAZE_WEIGHT: Record<BotState, number> = { idle: 1, listening: 0.7, thinking: 0, speaking: 0.5, sleeping: 0 };

export function clamp(x: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, x));
}
