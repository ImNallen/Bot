import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Animator } from "./animator";
import { type BotState, type Mood } from "./character";
import { type BackendEvent, connectToBackend } from "./link";
import { CANVAS_UNITS, drawBot } from "./render";
import { BODY_PT, type OverlaySettings, getSettings, onSettings } from "./settings";
import { applyTheme, onSystemThemeChange, resolveTheme } from "./theme";

const MARGIN_PT = 24;
const BUBBLE_FADE_MS = 4000;
const STATE_LABEL: Record<BotState, string> = { idle: "idle", listening: "listening", thinking: "thinking", speaking: "speaking", sleeping: "dozing" };

const canvas = document.getElementById("bot") as HTMLCanvasElement;
const bubble = document.getElementById("bubble")!;
const bubbleText = bubble.querySelector("p")!;
const panel = document.getElementById("panel")!;
const messages = document.getElementById("messages")!;
const panelState = document.getElementById("panel-state")!;
const animator = new Animator(Math.random, performance.now());

let settings: OverlaySettings = { theme: "system", size: "m", keepAway: true, hideInFullscreen: true, stayPut: false, hidden: false };
let body = BODY_PT.m;
const center = { x: 0, y: 0 };

/** The bot's centre and size decide where everything else sits, and which parts of the window take clicks. */
function layout(): void {
  body = BODY_PT[settings.size];
  const canvasPt = (body * CANVAS_UNITS) / 240;
  center.x = window.innerWidth - MARGIN_PT - body / 2;
  center.y = window.innerHeight - MARGIN_PT - body / 2;
  Object.assign(canvas.style, { left: `${center.x - canvasPt / 2}px`, top: `${center.y - canvasPt / 2}px`, width: `${canvasPt}px`, height: `${canvasPt}px` });
  canvas.width = canvas.height = Math.round(canvasPt * (window.devicePixelRatio || 1));
  const botTop = center.y - body / 2;
  Object.assign(bubble.style, { right: `${window.innerWidth - (center.x + body * 0.1)}px`, bottom: `${window.innerHeight - botTop + 6}px` });
  Object.assign(panel.style, { right: `${MARGIN_PT}px`, bottom: `${window.innerHeight - botTop + 12}px` });
  reportHitRegions();
}

function reportHitRegions(): void {
  const regions: object[] = [{ kind: "circle", x: center.x, y: center.y, r: body / 2 }];
  if (!panel.hidden) {
    const r = panel.getBoundingClientRect();
    regions.push({ kind: "rect", x: r.left, y: r.top, w: r.width, h: r.height });
  }
  void invoke("set_hit_regions", { list: regions });
}

function applySettings(next: OverlaySettings): void {
  settings = next;
  applyTheme(settings.theme);
  layout();
}

// --- speech bubble and transcript ---------------------------------------------------------------

let fadeTimer: number | undefined;
let botLine: HTMLLIElement | null = null;

function showBubble(text: string): void {
  if (!panel.hidden) return;
  clearTimeout(fadeTimer);
  bubbleText.textContent = text;
  bubble.hidden = false;
  bubble.classList.remove("fading");
}

function fadeBubble(after: number): void {
  clearTimeout(fadeTimer);
  fadeTimer = window.setTimeout(() => {
    bubble.classList.add("fading");
    fadeTimer = window.setTimeout(() => (bubble.hidden = true), 400);
  }, after);
}

function addMessage(who: "you" | "bot", text: string): HTMLLIElement {
  messages.querySelector(".empty")?.remove();
  const li = document.createElement("li");
  li.className = who;
  li.textContent = text;
  messages.append(li);
  while (messages.children.length > 200) messages.firstElementChild?.remove();
  messages.scrollTop = messages.scrollHeight;
  return li;
}

function setPanel(open: boolean): void {
  panel.hidden = !open;
  if (open) {
    bubble.hidden = true;
    if (!messages.children.length) messages.innerHTML = '<li class="empty">Nothing said yet.</li>';
  }
  reportHitRegions();
}

function onBackend(event: BackendEvent): void {
  switch (event.type) {
    case "state":
      animator.state = event.state;
      panelState.textContent = STATE_LABEL[event.state];
      if (event.state === "listening") bubble.hidden = true;
      if (event.state === "idle" || event.state === "sleeping") fadeBubble(BUBBLE_FADE_MS);
      break;
    case "mood":
      animator.mood = event.mood;
      break;
    case "levels":
      animator.speechLevel = event.speech;
      animator.micLevel = Math.min(1, event.mic * 12);
      break;
    case "heard":
      addMessage("you", event.text);
      botLine = null;
      break;
    case "said":
      botLine = botLine ?? addMessage("bot", "");
      botLine.textContent = `${botLine.textContent} ${event.text}`.trim();
      showBubble(botLine.textContent);
      break;
    case "status":
      break;
  }
}

// --- clicks ---------------------------------------------------------------------------------------

/** While no backend is connected, clicking the bot steps through every state and mood instead. */
const DEMO: [BotState, Mood][] = [
  ["idle", "neutral"], ["listening", "neutral"], ["thinking", "neutral"], ["speaking", "happy"], ["speaking", "neutral"],
  ["speaking", "sad"], ["speaking", "surprised"], ["speaking", "annoyed"], ["sleeping", "neutral"],
];
let demoStep = 0;

const backend = connectToBackend(onBackend, (connected) => {
  if (!connected) [animator.state, animator.mood, animator.speechLevel, animator.micLevel] = ["idle", "neutral", 0, 0];
});

canvas.addEventListener("click", (e) => {
  const r = canvas.getBoundingClientRect();
  if (Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2)) > body / 2) return;
  if (backend.connected) return setPanel(panel.hidden);
  demoStep = (demoStep + 1) % DEMO.length;
  [animator.state, animator.mood] = DEMO[demoStep]!;
  animator.speechLevel = animator.state === "speaking" ? 0.08 : 0;
});
document.getElementById("panel-close")!.addEventListener("click", () => setPanel(false));
window.addEventListener("keydown", (e) => e.key === "Escape" && setPanel(false));

void listen<{ x: number; y: number }>("pointer", ({ payload }) => animator.pointAt(payload.x - center.x, payload.y - center.y, performance.now()));
void listen("open-transcript", () => setPanel(true));
void onSettings(applySettings);
onSystemThemeChange(() => applySettings(settings));
window.addEventListener("resize", layout);
void getSettings().then(applySettings);
applySettings(settings);

function frame(now: number): void {
  drawBot(canvas, animator.tick(now), resolveTheme(settings.theme).theme);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
