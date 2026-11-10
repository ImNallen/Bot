import { card, choice, h, note, section, slider } from "../ui";
import type { Ctx, PageDef } from "./page";

const BARS = 44;
let meter: HTMLCanvasElement | null = null;
let hearing: HTMLElement | null = null;

/** The menu's mic setting is part of a device name, as with COMPANION_MIC, so match it the way the backend does. */
export function chosenMic(ctx: Ctx): string | null {
  const wanted = ctx.status?.prefs.mic?.toLowerCase();
  if (!wanted) return null;
  return ctx.devices?.find((d) => d.name.toLowerCase().includes(wanted))?.name ?? ctx.status!.prefs.mic;
}

const sensitivityWord = (v: number) => (v < 0.34 ? "Low" : v < 0.67 ? "Medium" : "High");

export const microphone: PageDef = {
  title: "Microphone",
  needs: ["devices"],
  key: (ctx) => [ctx.connected, ctx.devices, ctx.status?.prefs.mic, ctx.status?.micOn],
  render(ctx) {
    const prefs = ctx.status?.prefs;
    const current = chosenMic(ctx);
    const devices = ctx.devices ?? [];
    meter = h("canvas", { class: "meter" });
    hearing = h("span", { class: "value" });
    return h(
      "div",
      {},
      section(
        "Input device",
        card(
          ...devices.map((d) => choice(d.name, d.default ? [d.detail, "System default"].filter(Boolean).join(" · ") : d.detail, d.name === current, () => ctx.set("mic", d.name))),
          choice("Follow system default", "", prefs?.mic === null, () => ctx.set("mic", null)),
        ),
        ctx.connected && !ctx.devices ? note("Looking for microphones…") : null,
      ),
      section("Level", card(h("div", { class: "row meter-row" }, meter, hearing))),
      section(
        "Turn taking",
        card(
          slider("Voice sensitivity", {
            min: 0, max: 1, step: 0.05, value: prefs?.sensitivity ?? 0.5, show: sensitivityWord,
            ends: ["Ignores more noise", "Hears whispers"], commit: (v) => ctx.set("sensitivity", v), disabled: !prefs,
          }),
          slider("Pause before replying", {
            min: 0.35, max: 1.5, step: 0.05, value: prefs?.pause ?? 0.65, show: (v) => `${v.toFixed(2).replace(/0$/, "")} s`,
            ends: ["Faster", "More patient"], commit: (v) => ctx.set("pause", v), disabled: !prefs,
          }),
        ),
        note("A shorter pause replies faster but can cut you off mid-thought."),
      ),
    );
  },
  tick(ctx) {
    if (!meter || !hearing) return;
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = meter.getBoundingClientRect();
    if (meter.width !== Math.round(width * dpr)) [meter.width, meter.height] = [Math.round(width * dpr), Math.round(height * dpr)];
    const g = meter.getContext("2d")!;
    g.clearRect(0, 0, meter.width, meter.height);
    const levels = ctx.micLevels.slice(-BARS);
    const gap = meter.width / BARS;
    const on = ctx.connected && !!ctx.status?.micOn;
    levels.forEach((level, i) => {
      const loud = on ? Math.min(1, (level * 10) ** 0.6) : 0;
      const bar = Math.max(dpr * 2.5, loud * meter!.height);
      g.fillStyle = loud > 0.08 ? ctx.theme.listening : ctx.theme.textSecondary;
      g.globalAlpha = loud > 0.08 ? 1 : 0.45;
      g.beginPath();
      g.roundRect((BARS - levels.length + i) * gap + gap * 0.2, (meter!.height - bar) / 2, gap * 0.55, bar, dpr * 1.5);
      g.fill();
    });
    g.globalAlpha = 1;
    hearing.textContent = !ctx.connected ? "Voice not running" : !ctx.status?.micOn ? "Mic off" : ctx.state === "listening" ? "Hearing you" : "Quiet";
  },
};
