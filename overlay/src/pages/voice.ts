import { card, choice, h, icon, note, section } from "../ui";
import type { PageDef } from "./page";

export const voice: PageDef = {
  title: "Voice",
  needs: ["voices"],
  key: (ctx) => [ctx.connected, ctx.voices, ctx.status?.prefs.voice],
  render(ctx) {
    const current = ctx.status?.prefs.voice;
    const play = (id: string) =>
      h("span", {
        class: "play",
        title: "Play a sample",
        onclick: (e: MouseEvent) => {
          e.stopPropagation();
          ctx.send({ type: "preview", voice: id });
        },
      }, icon("play"));
    return h(
      "div",
      {},
      section("Engine", card(choice(ctx.voices?.engine ?? "Kokoro 82M", "Fast · runs on this Mac", true, () => {}))),
      section(
        "Voices",
        card(...(ctx.voices?.voices ?? []).map((v) => choice(v.name, v.detail, v.id === current, () => ctx.set("voice", v.id), play(v.id)))),
        note("Play says a short line in the bot's own words. Samples wait while it is talking."),
      ),
    );
  },
};
