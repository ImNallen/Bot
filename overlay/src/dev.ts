import { Animator } from "./animator";
import { type BotState, EXPRESSIONS, MOODS, type Mood, STATES, type ThemeName, presets, targetParams, themes } from "./character";
import { CANVAS_UNITS, type Frame, drawBot } from "./render";

const DPR = window.devicePixelRatio || 1;

function canvasFor(el: HTMLCanvasElement): HTMLCanvasElement {
  const css = el.getBoundingClientRect().width || 160;
  el.width = el.height = Math.round(css * DPR);
  return el;
}

function figure(parent: HTMLElement, label: string): HTMLCanvasElement {
  const fig = document.createElement("figure");
  const canvas = document.createElement("canvas");
  const cap = document.createElement("figcaption");
  cap.textContent = label;
  fig.append(canvas, cap);
  parent.append(fig);
  return canvasFor(canvas);
}

function still(state: BotState, params = targetParams(state, "happy")): Frame {
  return { params, bob: 0, mouth: state === "speaking" ? 0.55 : 0, state, time: 0.35, micLevel: 0.3 };
}

for (const theme of ["dark", "light"] as ThemeName[]) {
  for (const name of EXPRESSIONS) drawBot(figure(document.getElementById(`expr-${theme}`)!, name), still("idle", presets[name]), themes[theme]);
  for (const state of STATES) drawBot(figure(document.getElementById(`state-${theme}`)!, state), still(state), themes[theme]);
}

const live = canvasFor(document.getElementById("live") as HTMLCanvasElement);
const animator = new Animator(Math.random, performance.now());
const controls = document.getElementById("controls")!;

function buttons(label: string, values: readonly string[], pick: (v: string) => void, current: () => string) {
  const row = document.createElement("div");
  row.append(`${label}: `);
  for (const v of values) {
    const b = document.createElement("button");
    b.textContent = v;
    b.onclick = () => {
      pick(v);
      for (const btn of controls.querySelectorAll("button")) btn.classList.toggle("on", false);
      render();
    };
    b.dataset.value = v;
    row.append(b);
  }
  controls.append(row);
  const render = () => row.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.value === current()));
  render();
}

buttons("state", STATES, (v) => { animator.override = null; animator.state = v as BotState; }, () => animator.state);
buttons("mood", MOODS, (v) => { animator.mood = v as Mood; }, () => animator.mood);
buttons("force expression", EXPRESSIONS, (v) => { animator.override = presets[v as keyof typeof presets]; }, () => "");

window.addEventListener("mousemove", (e) => {
  const r = live.getBoundingClientRect();
  const scale = 120 / (r.width * (240 / CANVAS_UNITS));
  animator.pointAt((e.clientX - (r.left + r.width / 2)) * scale, (e.clientY - (r.top + r.height / 2)) * scale, performance.now());
});

setInterval(() => (animator.speechLevel = animator.state === "speaking" ? Math.random() * 0.25 : 0), 60);
setInterval(() => (animator.micLevel = animator.state === "listening" ? Math.random() : 0), 90);

function loop(now: number) {
  drawBot(live, animator.tick(now), themes.light);
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
