import { card, choice, formatBytes, h, label, modelLabel, note, section, toggle } from "../ui";
import type { PageDef } from "./page";

let switchingTo: string | null = null;

export const model: PageDef = {
  title: "Model",
  needs: ["models"],
  key: (ctx) => [ctx.connected, ctx.models, ctx.status?.model, ctx.status?.prefs.keepLoaded, ctx.status?.prefs.thinking],
  render(ctx) {
    const m = ctx.models;
    const prefs = ctx.status?.prefs;
    const current = ctx.status?.model;
    const host = m?.server.replace(/^https?:\/\//, "") ?? "";
    const installed = m?.installed ?? [];
    if (installed.find((i) => i.name === switchingTo)?.loaded) switchingTo = null;
    const size = installed.find((i) => i.name === current)?.size;
    return h(
      "div",
      {},
      card(
        h(
          "div",
          { class: "row" },
          label("Ollama", !m ? "Checking…" : m.running ? `Running at ${host}` : `Not reachable at ${host}`),
          m?.version ? h("span", { class: "value" }, m.version) : null,
        ),
      ),
      section(
        "Installed",
        card(
          ...installed.map((i) => {
            const { name, quant } = modelLabel(i.name);
            const state = i.name === switchingTo && !i.loaded ? "loading…" : i.loaded ? "loaded" : "";
            return choice(name, [quant, formatBytes(i.size), state].filter(Boolean).join(" · "), i.name === current, () => {
              if (i.name === current) return;
              switchingTo = i.name;
              ctx.send({ type: "set", key: "model", value: i.name });
            });
          }),
        ),
        m?.running && installed.length === 0 ? note("No chat models yet. Pull one with ollama pull.") : null,
      ),
      section(
        "Behavior",
        card(
          toggle("Keep model loaded", prefs?.keepLoaded ?? true, (on) => ctx.set("keepLoaded", on), !prefs),
          toggle("Thinking", prefs?.thinking ?? false, (on) => ctx.set("thinking", on), !prefs),
        ),
        note(`Keeping it loaded holds ${size ? formatBytes(size) : "its size"} of memory and avoids a cold start. Thinking makes replies slower.`),
      ),
    );
  },
};
