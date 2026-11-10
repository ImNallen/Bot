import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { Animator } from "./animator";
import type { BotState } from "./character";
import { connectToBackend } from "./link";
import { drawBot } from "./render";
import { type OverlaySettings, getSettings, onSettings, updateSettings } from "./settings";
import { applyTheme, onSystemThemeChange, resolveTheme } from "./theme";

type HideReason = "manual" | "fullscreen" | "camera" | null;

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
const animator = new Animator(Math.random, performance.now());
let settings: OverlaySettings | null = null;
const live = { connected: false, state: "idle" as BotState, micOn: true, hidden: null as HideReason };

function render(): void {
  if (!settings) return;
  applyTheme(settings.theme);
  document.querySelectorAll<HTMLElement>(".segmented").forEach((group) => {
    const current = settings![group.dataset.setting as "theme" | "size"];
    group.querySelectorAll<HTMLButtonElement>("button").forEach((b) => b.classList.toggle("on", b.dataset.value === current));
  });
  document.querySelectorAll<HTMLInputElement>("input[data-setting]").forEach((input) => {
    input.checked = Boolean(settings![input.dataset.setting as keyof OverlaySettings]);
  });
  tile("mic").classList.toggle("on", live.connected && live.micOn);
  tile("mic").querySelector("span")!.textContent = live.micOn ? "Mic on" : "Mic off";
  tile("stayPut").classList.toggle("on", settings.stayPut);
  tile("hidden").classList.toggle("on", settings.hidden);
  tile("sleep").classList.toggle("on", live.state === "sleeping");
  tile("mic").disabled = tile("sleep").disabled = !live.connected;
  $("#status").textContent = live.hidden
    ? HIDDEN_TEXT[live.hidden]
    : !live.connected
      ? "Voice not running"
      : !live.micOn
        ? "Microphone off"
        : STATE_TEXT[live.state];
  void invoke("fit_popover", { height: $("#popover").getBoundingClientRect().height });
}

const tile = (name: string) => $<HTMLButtonElement>(`[data-tile="${name}"]`);
const change = (patch: Partial<OverlaySettings>) => void updateSettings(patch).then((s) => ((settings = s), render()));

const backend = connectToBackend(
  (event) => {
    if (event.type === "state") [live.state, animator.state] = [event.state, event.state];
    if (event.type === "mood") animator.mood = event.mood;
    if (event.type === "status") {
      live.micOn = event.micOn;
      $("#model").textContent = event.model.replace(/:(\d+)b/i, " $1B").replace(/-a3b/i, "-A3B").replace(/-q8_0$/i, " · Q8");
      $("#memories").textContent = `${event.memories} saved`;
    }
    if (event.type === "state" || event.type === "status") render();
  },
  (connected) => {
    live.connected = connected;
    render();
  },
);

tile("mic").onclick = () => backend.send(live.micOn ? "mute" : "unmute");
tile("sleep").onclick = () => backend.send("sleep");
tile("stayPut").onclick = () => settings && change({ stayPut: !settings.stayPut });
tile("hidden").onclick = () => settings && change({ hidden: !settings.hidden });
document.querySelectorAll<HTMLElement>(".segmented").forEach((group) =>
  group.querySelectorAll<HTMLButtonElement>("button").forEach((b) => (b.onclick = () => change({ [group.dataset.setting!]: b.dataset.value }))),
);
document.querySelectorAll<HTMLInputElement>("input[data-setting]").forEach((input) => (input.onchange = () => change({ [input.dataset.setting!]: input.checked })));
$("#open-transcript").onclick = () => void invoke("open_transcript");
$("#quit").onclick = () => void invoke("quit");
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") void getCurrentWindow().hide();
  if (e.key === "q" && e.metaKey) void invoke("quit");
});

void listen<HideReason>("visibility", ({ payload }) => ((live.hidden = payload), render()));
void onSettings((s) => ((settings = s), render()));
onSystemThemeChange(render);
void getSettings().then((s) => ((settings = s), render()));

function frame(now: number): void {
  if (settings) drawBot(avatar, animator.tick(now), resolveTheme(settings.theme).theme);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
