import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Animator } from "./animator";
import type { BotState } from "./character";
import { type PrefKey, type Prefs, connectToBackend } from "./link";
import { memories } from "./pages/memories";
import { chosenMic, microphone } from "./pages/microphone";
import { model } from "./pages/model";
import type { Ctx, PageDef } from "./pages/page";
import { friendsFor, stats } from "./pages/stats";
import { voice } from "./pages/voice";
import { drawBot } from "./render";
import { type OverlaySettings, getSettings, onSettings, updateSettings } from "./settings";
import { applyTheme, onSystemThemeChange, resolveTheme } from "./theme";
import { icon, modelLabel, slider, syncSlider } from "./ui";

type HideReason = "manual" | "fullscreen" | "camera" | null;
type PageName = "microphone" | "voice" | "model" | "memories" | "stats";

const PAGES: Record<PageName, PageDef> = { microphone, voice, model, memories, stats };
const SLIDE_MS = 220;
const STATE_TEXT: Record<BotState, string> = {
  idle: "Idle · just start talking",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  sleeping: "Dozing · talk to wake it",
};
const HIDDEN_TEXT: Record<Exclude<HideReason, null>, string> = { manual: "Hidden", fullscreen: "Hidden while a fullscreen app is open", camera: "Hidden while the camera is in use" };

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const avatar = $<HTMLCanvasElement>("#avatar");
const mainPage = $("#main");
const subPage = $("#sub");
const animator = new Animator(Math.random, performance.now());
let settings: OverlaySettings | null = null;
let hidden: HideReason = null;
let notice: { text: string; until: number } | null = null;

const ctx: Ctx = {
  connected: false,
  state: "idle",
  status: null,
  devices: null,
  voices: null,
  models: null,
  memories: null,
  stats: null,
  micLevels: [],
  theme: resolveTheme("system").theme,
  set<K extends PrefKey>(key: K, value: Prefs[K]) {
    backend.send({ type: "set", key, value });
  },
  send: (request) => backend.send(request),
};

// --- Sub pages: one level deep, pushed in from the right inside the same popover.

let open: { name: PageName; key: string } | null = null;

function fit(): void {
  const page = open ? subPage : mainPage;
  void invoke("fit_popover", { height: page.getBoundingClientRect().height });
}

function renderPage(): void {
  if (!open) return;
  const page = PAGES[open.name];
  open.key = JSON.stringify(page.key(ctx));
  $("#sub-body").replaceChildren(page.render(ctx));
  fit();
}

function refreshPage(): void {
  if (open && JSON.stringify(PAGES[open.name].key(ctx)) !== open.key) renderPage();
}

function slide(from: HTMLElement, to: HTMLElement, forward: boolean): void {
  to.hidden = false;
  const tallest = Math.max(from.getBoundingClientRect().height, to.getBoundingClientRect().height);
  void invoke("fit_popover", { height: tallest });
  const out = forward ? "-30%" : "100%";
  const inFrom = forward ? "100%" : "-30%";
  const ease = { duration: SLIDE_MS, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" };
  from.animate([{ transform: "translateX(0)", opacity: 1 }, { transform: `translateX(${out})`, opacity: 0 }], ease);
  to.animate([{ transform: `translateX(${inFrom})`, opacity: forward ? 1 : 0 }, { transform: "translateX(0)", opacity: 1 }], ease).onfinish = () => {
    from.hidden = true;
    fit();
  };
}

function push(name: PageName): void {
  if (!ctx.connected) return;
  const page = PAGES[name];
  for (const what of page.needs) backend.send({ type: "get", what });
  open = { name, key: "" };
  $("#sub-title").textContent = page.title;
  renderPage();
  slide(mainPage, subPage, true);
}

function back(animated = true): void {
  if (!open) return;
  open = null;
  if (animated) slide(subPage, mainPage, false);
  else {
    [subPage.hidden, mainPage.hidden] = [true, false];
    fit();
  }
}

// --- Main page.

function speedSlider(): HTMLElement {
  return slider("Speaking speed", { min: 0.7, max: 1.4, step: 0.05, value: 1, show: (v) => `${v.toFixed(2).replace(/0$/, "")}×`, commit: (v) => ctx.set("speed", v) });
}
const speed = speedSlider();
$("#speed").replaceWith(speed);
speed.dataset.needsBackend = "";

function render(): void {
  if (!settings) return;
  ctx.theme = resolveTheme(settings.theme).theme;
  applyTheme(settings.theme);
  document.querySelectorAll<HTMLElement>(".segmented").forEach((group) => {
    const current = settings![group.dataset.setting as "theme" | "size"];
    group.querySelectorAll<HTMLButtonElement>("button").forEach((b) => b.classList.toggle("on", b.dataset.value === current));
  });
  document.querySelectorAll<HTMLInputElement>("input[data-setting]").forEach((input) => {
    input.checked = Boolean(settings![input.dataset.setting as keyof OverlaySettings]);
  });
  const status = ctx.connected ? ctx.status : null;
  const prefs = status?.prefs;
  tile("mic").classList.toggle("on", !!status?.micOn);
  tile("mic").querySelector("span")!.textContent = status && !status.micOn ? "Mic off" : "Mic on";
  tile("stayPut").classList.toggle("on", settings.stayPut);
  tile("hidden").classList.toggle("on", settings.hidden);
  tile("sleep").classList.toggle("on", ctx.state === "sleeping");
  tile("mic").disabled = tile("sleep").disabled = !ctx.connected;
  document.querySelectorAll<HTMLElement>("[data-needs-backend]").forEach((el) => {
    el.classList.toggle("off", !status);
    el.querySelectorAll<HTMLInputElement | HTMLButtonElement>("input, button").forEach((c) => (c.disabled = !status));
    if (el instanceof HTMLButtonElement) el.disabled = !status;
  });
  document.querySelectorAll<HTMLInputElement>("input[data-pref]").forEach((input) => {
    input.checked = Boolean(prefs?.[input.dataset.pref as keyof Prefs]);
  });
  const mic = prefs ? (chosenMic(ctx) ?? "System default") : "–";
  $("#mic-name").textContent = mic.replace(/ Microphone$/, " Mic");
  const voiceName = prefs ? (ctx.voices?.voices.find((v) => v.id === prefs.voice)?.name ?? prefs.voice.split("_")[1]) : null;
  $("#voice-name").textContent = voiceName ? `Kokoro · ${voiceName.charAt(0).toUpperCase()}${voiceName.slice(1)}` : "–";
  if (prefs) syncSlider(speed, prefs.speed);
  const label = status ? modelLabel(status.model) : null;
  $("#model").textContent = label ? [label.name, label.quant].filter(Boolean).join(" · ") : "–";
  $("#memories").textContent = !status ? "–" : !prefs?.memoryOn ? "Off" : `${status.memories} saved`;
  const friends = friendsFor(ctx.stats);
  $("#friends").textContent = status && friends ? `Friends ${friends}` : "";
  $("#status").textContent =
    notice && Date.now() < notice.until
      ? notice.text
      : hidden
        ? HIDDEN_TEXT[hidden]
        : !ctx.connected
          ? "Voice not running"
          : status && !status.micOn
            ? "Microphone off"
            : STATE_TEXT[ctx.state];
  refreshPage();
  if (!open) fit();
}

const tile = (name: string) => $<HTMLButtonElement>(`[data-tile="${name}"]`);
const change = (patch: Partial<OverlaySettings>) => void updateSettings(patch).then((s) => ((settings = s), render()));

const backend = connectToBackend(
  (event) => {
    switch (event.type) {
      case "state":
        [ctx.state, animator.state] = [event.state, event.state];
        break;
      case "mood":
        animator.mood = event.mood;
        return;
      case "levels":
        ctx.micLevels.push(event.mic);
        if (ctx.micLevels.length > 120) ctx.micLevels.splice(0, ctx.micLevels.length - 120);
        return;
      case "status":
        ctx.status = event;
        break;
      case "notice":
        notice = { text: event.text, until: Date.now() + 5000 };
        setTimeout(render, 5100);
        break;
      case "devices":
        ctx.devices = event.inputs;
        break;
      case "voices":
        ctx.voices = event;
        break;
      case "models":
        ctx.models = event;
        break;
      case "memories":
        ctx.memories = event;
        break;
      case "stats":
        ctx.stats = event;
        break;
      default:
        return;
    }
    render();
  },
  (connected) => {
    ctx.connected = connected;
    if (connected) refreshData();
    else back(false);
    render();
  },
);

/** Fresh numbers each time the menu opens: the Stats row on the main page, plus whatever page is showing. */
function refreshData(): void {
  backend.send({ type: "get", what: "stats" });
  backend.send({ type: "get", what: "voices" });
  backend.send({ type: "get", what: "devices" });
  for (const what of open ? PAGES[open.name].needs : []) backend.send({ type: "get", what });
}

tile("mic").onclick = () => backend.send({ type: "command", name: ctx.status?.micOn ? "mute" : "unmute" });
tile("sleep").onclick = () => backend.send({ type: "command", name: "sleep" });
tile("stayPut").onclick = () => settings && change({ stayPut: !settings.stayPut });
tile("hidden").onclick = () => settings && change({ hidden: !settings.hidden });
document.querySelectorAll<HTMLElement>(".segmented").forEach((group) =>
  group.querySelectorAll<HTMLButtonElement>("button").forEach((b) => (b.onclick = () => change({ [group.dataset.setting!]: b.dataset.value }))),
);
document.querySelectorAll<HTMLInputElement>("input[data-setting]").forEach((input) => (input.onchange = () => change({ [input.dataset.setting!]: input.checked })));
document.querySelectorAll<HTMLInputElement>("input[data-pref]").forEach((input) => (input.onchange = () => ctx.set(input.dataset.pref as "interrupt", input.checked)));
document.querySelectorAll<HTMLButtonElement>("button.nav").forEach((b) => {
  b.append(icon("chevron"));
  b.onclick = () => push(b.dataset.page as PageName);
});
$("#back").append(icon("back"), "Settings");
$("#back").onclick = () => back();
$("#open-transcript").onclick = () => void invoke("open_transcript");
$("#quit").onclick = () => void invoke("quit");
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") open ? back() : void getCurrentWindow().hide();
  if (e.metaKey && e.key === "q") void invoke("quit");
  if (e.metaKey && e.key === "t") void invoke("open_transcript");
});

// Each opening starts on the main page with fresh numbers.
void getCurrentWindow().onFocusChanged(({ payload: focused }) => {
  if (focused && ctx.connected) refreshData();
  if (!focused) back(false);
});
void listen<HideReason>("visibility", ({ payload }) => ((hidden = payload), render()));
void onSettings((s) => ((settings = s), render()));
onSystemThemeChange(render);
void getSettings().then((s) => ((settings = s), render()));

function frame(now: number): void {
  if (settings) drawBot(avatar, animator.tick(now), ctx.theme);
  if (open) PAGES[open.name].tick?.(ctx);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
