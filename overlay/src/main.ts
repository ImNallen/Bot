import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Animator } from "./animator";
import { connectToBackend } from "./link";
import { type BotState, type Mood, themes } from "./character";
import { CANVAS_UNITS, drawBot } from "./render";

const BODY_PT = 120;
const MARGIN_PT = 24;
const CANVAS_PT = (BODY_PT * CANVAS_UNITS) / 240;
const inTauri = "__TAURI_INTERNALS__" in window;

const canvas = document.getElementById("bot") as HTMLCanvasElement;
const animator = new Animator(Math.random, performance.now());
const dark = window.matchMedia("(prefers-color-scheme: dark)");

/** The bot's centre in window points, kept in one place so drawing, eye tracking and hit testing agree. */
const center = { x: 0, y: 0 };

function layout(): void {
  center.x = window.innerWidth - MARGIN_PT - BODY_PT / 2;
  center.y = window.innerHeight - MARGIN_PT - BODY_PT / 2;
  Object.assign(canvas.style, { left: `${center.x - CANVAS_PT / 2}px`, top: `${center.y - CANVAS_PT / 2}px`, width: `${CANVAS_PT}px`, height: `${CANVAS_PT}px` });
  canvas.width = canvas.height = Math.round(CANVAS_PT * (window.devicePixelRatio || 1));
  if (inTauri) void invoke("set_hit_region", { x: center.x, y: center.y, r: BODY_PT / 2 });
}

/** While no backend is connected, clicking the bot steps through every state and mood. */
const DEMO: [BotState, Mood][] = [
  ["idle", "neutral"],
  ["listening", "neutral"],
  ["thinking", "neutral"],
  ["speaking", "happy"],
  ["speaking", "neutral"],
  ["speaking", "sad"],
  ["speaking", "surprised"],
  ["speaking", "annoyed"],
  ["sleeping", "neutral"],
];
let demoStep = 0;
let backendConnected = false;
canvas.addEventListener("click", (e) => {
  if (backendConnected) return;
  const r = canvas.getBoundingClientRect();
  if (Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2)) > BODY_PT / 2) return;
  demoStep = (demoStep + 1) % DEMO.length;
  [animator.state, animator.mood] = DEMO[demoStep]!;
});

setInterval(() => {
  if (backendConnected) return;
  animator.speechLevel = animator.state === "speaking" ? Math.random() * 0.25 : 0;
  animator.micLevel = animator.state === "listening" ? Math.random() : 0;
}, 70);

connectToBackend(
  "ws://127.0.0.1:8765",
  (event) => {
    switch (event.type) {
      case "state":
        animator.state = event.state;
        break;
      case "mood":
        animator.mood = event.mood;
        break;
      case "levels":
        animator.speechLevel = event.speech;
        animator.micLevel = Math.min(1, event.mic * 12);
        break;
    }
  },
  (connected) => {
    backendConnected = connected;
    if (!connected) [animator.state, animator.mood, animator.speechLevel, animator.micLevel] = ["idle", "neutral", 0, 0];
  },
);

if (inTauri) {
  void listen<{ x: number; y: number }>("pointer", ({ payload }) => animator.pointAt(payload.x - center.x, payload.y - center.y, performance.now()));
} else {
  window.addEventListener("mousemove", (e) => animator.pointAt(e.clientX - center.x, e.clientY - center.y, performance.now()));
}

window.addEventListener("resize", layout);
layout();

function frame(now: number): void {
  drawBot(canvas, animator.tick(now), dark.matches ? themes.dark : themes.light);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
