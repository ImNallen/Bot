import { presets } from "../character";
import type { Stats } from "../link";
import { drawBot } from "../render";
import { card, day, formatBytes, formatDuration, h, note, section, shortDate } from "../ui";
import type { Ctx, PageDef } from "./page";

export function friendsFor(stats: Stats | null): string | null {
  if (!stats?.since) return null;
  const days = Math.max(1, Math.round((Date.now() - day(stats.since).getTime()) / 86_400_000));
  return `${days} ${days === 1 ? "day" : "days"}`;
}

function face(ctx: Ctx, mood: keyof typeof presets, size = 20): HTMLCanvasElement {
  const canvas = h("canvas", { class: "face" });
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.height = Math.round(size * dpr);
  canvas.style.width = canvas.style.height = `${size}px`;
  drawBot(canvas, { params: presets[mood], bob: 0, mouth: 0, state: "idle", time: 0, micLevel: 0 }, ctx.theme);
  return canvas;
}

function fill(className: string, size: string, axis: "width" | "height", title = ""): HTMLElement {
  const bar = h("i", { className, title });
  bar.style[axis] = size;
  return bar;
}

const tile = (value: string, caption: string) => h("div", { class: "stat" }, h("strong", {}, value), h("small", {}, caption));
const fact = (title: string, value: string) => h("div", { class: "row" }, h("span", {}, title), h("span", { class: "value" }, value));

function chart(perDay: number[]): HTMLElement {
  const top = Math.max(1, ...perDay);
  const first = new Date(Date.now() - (perDay.length - 1) * 86_400_000);
  return h(
    "div",
    { class: "chart" },
    h("div", { class: "bars" }, ...perDay.map((n, i) => fill(i === perDay.length - 1 ? "today" : "", `${Math.max(4, (n / top) * 100)}%`, "height", String(n)))),
    h("div", { class: "chart-ends" }, h("span", {}, shortDate(first)), h("span", { class: "today" }, `Today ${perDay.at(-1) ?? 0}`)),
  );
}

export const stats: PageDef = {
  title: "Stats",
  needs: ["stats"],
  key: (ctx) => [ctx.connected, ctx.stats, ctx.theme],
  render(ctx) {
    const s = ctx.stats;
    if (!s) return h("div", {}, note(ctx.connected ? "Counting…" : "Start the voice app to see stats."));
    if (!s.on) return h("div", {}, note("Stats are off while memory is off."));
    if (!s.since) return h("div", {}, h("div", { class: "friends" }, face(ctx, "happy", 40), h("div", {}, h("strong", {}, "Nothing to count yet"), h("small", {}, "Talk to it and numbers show up here."))));
    const hour = s.chattyHour === null ? "–" : `${String(s.chattyHour).padStart(2, "0")}:00`;
    return h(
      "div",
      {},
      h(
        "div",
        { class: "friends" },
        face(ctx, "happy", 40),
        h("div", {}, h("strong", {}, `Friends for ${friendsFor(s)}`), h("small", {}, `Since ${shortDate(day(s.since))} · ${formatDuration(s.talkingSeconds)} of talking`)),
      ),
      h(
        "div",
        { class: "stat-grid" },
        tile(String(s.conversations), s.conversations === 1 ? "conversation" : "conversations"),
        tile(String(s.interruptions), "times you cut it off"),
        tile(s.replyStart === null ? "–" : `${s.replyStart.toFixed(2)} s`, "typical reply start"),
        tile(formatBytes(s.cloudBytes), "sent to the cloud"),
      ),
      s.moods.length
        ? section(
            h("span", { class: "split" }, h("span", {}, "Its moods"), h("span", {}, "this week")),
            card(
              ...s.moods.map((m) =>
                h(
                  "div",
                  { class: "row mood" },
                  face(ctx, m.mood),
                  h("span", {}, m.mood.charAt(0).toUpperCase() + m.mood.slice(1)),
                  h("span", { class: "meter-bar" }, fill("", `${m.share * 100}%`, "width")),
                  h("span", { class: "value" }, `${Math.round(m.share * 100)}%`),
                ),
              ),
            ),
          )
        : null,
      section(h("span", { class: "split" }, h("span", {}, "Chats per day"), h("span", {}, "last 14 days")), card(chart(s.perDay))),
      section(
        "Fun facts",
        card(
          s.favoriteWord ? fact("Favorite word", `${s.favoriteWord} ${s.favoriteWord} ${s.favoriteWord}`) : null,
          fact("Said “question”", `${s.saidQuestion} ${s.saidQuestion === 1 ? "time" : "times"}`),
          fact("Most chatty hour", hour),
          fact("Longest chat", formatDuration(s.longestChatSeconds)),
        ),
      ),
      note("Counted on this Mac from your voice chats. Nothing is sent anywhere."),
    );
  },
};
