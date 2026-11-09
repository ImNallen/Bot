import { type BotState, GAZE_WEIGHT, type Mood, PARAM_KEYS, type Params, clamp, motion, presets, targetParams } from "./character";
import type { Frame } from "./render";

const EXPRESSION_OMEGA = 4 / (motion.expressionTransitionMs / 1000);
const GAZE_OMEGA = 28;

/** Critically damped spring, integrated implicitly so it stays stable at any frame rate. */
function spring(x: number, v: number, target: number, omega: number, dt: number): [number, number] {
  const f = 1 + 2 * dt * omega;
  const oo = omega * omega;
  const hoo = dt * oo;
  const det = 1 / (f + dt * hoo);
  return [(f * x + dt * v + dt * hoo * target) * det, (v + hoo * (target - x)) * det];
}

export interface Rng {
  (): number;
}

/**
 * Owns everything that moves. Inputs are the state, the reply mood, where the cursor is and audio
 * levels; output is one Frame per tick. Time and randomness are passed in so behaviour is testable.
 */
export class Animator {
  state: BotState = "idle";
  mood: Mood = "neutral";
  /** Forces a preset, for the dev panel. */
  override: Params | null = null;
  speechLevel = 0;
  micLevel = 0;

  private params: Params = { ...presets.neutral };
  private velocity: Params = Object.fromEntries(PARAM_KEYS.map((k) => [k, 0])) as Params;
  private gaze = { x: 0, y: 0, vx: 0, vy: 0 };
  private cursor = { x: 0, y: 0, movedAt: -Infinity };
  private glance = { x: 0, y: 0, until: 0 };
  private blink = { start: Infinity, double: false };
  private nextBlinkAt: number;
  private mouth = 0;
  private bobPhase = 0;
  private last: number | null = null;

  constructor(private rng: Rng = Math.random, now = 0) {
    this.nextBlinkAt = now + this.blinkInterval();
  }

  /** Cursor offset from the bot's centre in screen points. */
  pointAt(dx: number, dy: number, now: number): void {
    if (Math.hypot(dx - this.cursor.x, dy - this.cursor.y) > 2) this.cursor.movedAt = now;
    this.cursor.x = dx;
    this.cursor.y = dy;
  }

  tick(now: number): Frame {
    const dt = this.last === null ? 0 : clamp((now - this.last) / 1000, 0, 0.1);
    this.last = now;

    const target = this.override ?? targetParams(this.state, this.mood);
    for (const k of PARAM_KEYS) {
      [this.params[k], this.velocity[k]] = spring(this.params[k], this.velocity[k], target[k], EXPRESSION_OMEGA, dt);
    }

    const [gx, gy] = this.gazeTarget(now);
    [this.gaze.x, this.gaze.vx] = spring(this.gaze.x, this.gaze.vx, gx, GAZE_OMEGA, dt);
    [this.gaze.y, this.gaze.vy] = spring(this.gaze.y, this.gaze.vy, gy, GAZE_OMEGA, dt);

    const speaking = this.state === "speaking";
    const mouthTarget = speaking ? 0.15 + clamp(this.speechLevel * 4, 0, 1) * 0.85 : 0;
    this.mouth += (mouthTarget - this.mouth) * clamp(dt / 0.05, 0, 1);

    const period = motion.bob.periodMs / 1000 / (this.state === "sleeping" ? 0.6 : 1);
    this.bobPhase += (dt / period) * Math.PI * 2;

    const weight = this.override ? 0 : GAZE_WEIGHT[this.state];
    const params: Params = {
      ...this.params,
      lid: Math.max(this.params.lid, this.blinkAmount(now)),
      lookX: this.params.lookX + this.gaze.x * weight,
      lookY: this.params.lookY + this.gaze.y * weight,
    };
    return {
      params,
      bob: Math.sin(this.bobPhase) * motion.bob.amplitudePx * 2,
      mouth: speaking ? Math.max(0.01, this.mouth) : 0,
      state: this.state,
      time: now / 1000,
      micLevel: this.micLevel,
    };
  }

  /** Lid closure from the blink schedule: close, hold, open, sometimes twice. */
  private blinkAmount(now: number): number {
    const b = motion.blink;
    if (this.state === "sleeping") return 0;
    if (now >= this.nextBlinkAt && !Number.isFinite(this.blink.start)) {
      this.blink = { start: now, double: this.rng() < b.doubleBlinkChance };
    }
    const t = now - this.blink.start;
    const one = b.closeMs + b.holdMs + b.openMs;
    const total = this.blink.double ? one * 2 + 60 : one;
    if (t < 0) return 0;
    if (t >= total) {
      this.blink.start = Infinity;
      this.nextBlinkAt = now + this.blinkInterval();
      return 0;
    }
    const local = t < one + 60 ? t : t - one - 60;
    if (local < b.closeMs) return local / b.closeMs;
    if (local < b.closeMs + b.holdMs) return 1;
    if (local < one) return 1 - (local - b.closeMs - b.holdMs) / b.openMs;
    return 0;
  }

  /** Follows the cursor; once it has been still for a while, glances around on its own. */
  private gazeTarget(now: number): [number, number] {
    const g = motion.idleGlance;
    if (now - this.cursor.movedAt < g.afterCursorStillMs) {
      const soften = (d: number) => d / (Math.abs(d) + 220);
      return [soften(this.cursor.x) * 1.6, soften(this.cursor.y) * 1.6];
    }
    if (now >= this.glance.until) {
      const [lo, hi] = g.intervalMs;
      const lookAway = this.rng() < 0.6;
      this.glance = {
        x: lookAway ? (this.rng() * 2 - 1) * 0.9 : 0,
        y: lookAway ? (this.rng() * 2 - 1) * 0.6 : 0,
        until: now + lo + this.rng() * (hi - lo),
      };
    }
    return [this.glance.x, this.glance.y];
  }

  private blinkInterval(): number {
    const [lo, hi] = motion.blink.intervalMs;
    return lo + this.rng() * (hi - lo);
  }
}
