import { describe, expect, it } from "vitest";
import { Animator } from "./animator";
import { motion, presets } from "./character";

function seeded(seed = 1) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

function run(a: Animator, fromMs: number, toMs: number, stepMs = 16) {
  const frames = [];
  for (let t = fromMs; t <= toMs; t += stepMs) frames.push({ t, f: a.tick(t) });
  return frames;
}

describe("Animator", () => {
  it("blinks within the configured interval and closes the eyes fully", () => {
    const a = new Animator(seeded(3), 0);
    const frames = run(a, 0, 12_000, 8);
    const closed = frames.filter(({ f }) => f.params.lid > 0.99).map(({ t }) => t);
    expect(closed.length).toBeGreaterThan(0);
    const firstClose = closed[0]!;
    expect(firstClose).toBeGreaterThanOrEqual(motion.blink.intervalMs[0]);
    expect(firstClose).toBeLessThanOrEqual(motion.blink.intervalMs[1] + motion.blink.closeMs + 16);
  });

  it("settles on the target expression after a state change", () => {
    const a = new Animator(seeded(), 0);
    a.state = "speaking";
    a.mood = "happy";
    const last = run(a, 0, 1500).at(-1)!.f;
    expect(last.params.smile).toBeCloseTo(presets.happy.smile, 2);
    expect(last.params.blush).toBeCloseTo(presets.happy.blush, 2);
  });

  it("looks toward the cursor while it moves", () => {
    const a = new Animator(seeded(), 0);
    let f = a.tick(0);
    for (let t = 16; t < 600; t += 16) {
      a.pointAt(-400 + t * 0.01, -200, t);
      f = a.tick(t);
    }
    expect(f.params.lookX).toBeLessThan(-0.8);
    expect(f.params.lookY).toBeLessThan(-0.5);
  });

  it("does not follow the cursor while thinking", () => {
    const a = new Animator(seeded(), 0);
    a.state = "thinking";
    let f = a.tick(0);
    for (let t = 16; t < 1500; t += 16) {
      a.pointAt(-600, 300, t);
      f = a.tick(t);
    }
    expect(f.params.lookX).toBeCloseTo(presets.thinking.lookX, 1);
  });

  it("keeps eyes nearly shut and never blinks while sleeping", () => {
    const a = new Animator(seeded(), 0);
    a.state = "sleeping";
    const lids = run(a, 0, 15_000).slice(100).map(({ f }) => f.params.lid);
    expect(Math.min(...lids)).toBeGreaterThan(0.9);
    expect(Math.max(...lids)).toBeLessThan(0.93);
  });

  it("opens the mouth with speech level only while speaking", () => {
    const a = new Animator(seeded(), 0);
    a.speechLevel = 0.3;
    expect(run(a, 0, 300).at(-1)!.f.mouth).toBe(0);
    a.state = "speaking";
    const loud = run(a, 300, 600).at(-1)!.f.mouth;
    a.speechLevel = 0;
    const quiet = run(a, 600, 900).at(-1)!.f.mouth;
    expect(loud).toBeGreaterThan(0.8);
    expect(quiet).toBeLessThan(0.3);
    expect(quiet).toBeGreaterThan(0);
  });
});
