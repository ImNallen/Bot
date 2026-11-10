import type { MemoryItem } from "../link";
import { card, day, h, icon, label, note, relativeDay, section, shortDate, toggle } from "../ui";
import type { Ctx, PageDef } from "./page";

let query = "";
let confirmUntil = 0;

function row(ctx: Ctx, m: MemoryItem): HTMLElement {
  const when = m.on ? `${relativeDay(day(m.on))}${m.followUp ? " · will ask how it went" : ""}` : `Learned ${shortDate(day(m.learned))}`;
  const forget = h("button", { class: "forget", title: "Forget this", onclick: () => ctx.send({ type: "forget", id: m.id }) }, icon("trash"));
  return h("div", { class: "row memory" }, label(m.text.charAt(0).toUpperCase() + m.text.slice(1), when), forget);
}

function lists(ctx: Ctx): HTMLElement {
  const items = (ctx.memories?.items ?? []).filter((m) => m.text.toLowerCase().includes(query.trim().toLowerCase()));
  const facts = items.filter((m) => m.kind === "fact").reverse();
  const events = items.filter((m) => m.kind === "event").sort((a, b) => (b.on ?? "").localeCompare(a.on ?? ""));
  return h(
    "div",
    { class: "memory-lists" },
    facts.length ? section("About you", card(...facts.map((m) => row(ctx, m)))) : null,
    events.length ? section("Plans and events", card(...events.map((m) => row(ctx, m)))) : null,
    !items.length && ctx.memories ? note(query ? "Nothing matches." : "Nothing yet. It learns from your chats once it has been quiet for a bit.") : null,
  );
}

export const memories: PageDef = {
  title: "Memories",
  needs: ["memories"],
  key: (ctx) => [ctx.connected, ctx.memories, ctx.status?.prefs.learn],
  render(ctx) {
    const prefs = ctx.status?.prefs;
    const count = ctx.memories?.items.length ?? 0;
    if (ctx.memories && !ctx.memories.on) return h("div", {}, note("Memory is off. Start the voice app without COMPANION_REMEMBER=false to turn it on."));
    let shown = lists(ctx);
    const search = h("input", {
      type: "search",
      placeholder: "Search memories",
      value: query,
      oninput: () => {
        query = search.value;
        const next = lists(ctx);
        shown.replaceWith(next);
        shown = next;
      },
    });
    const forgetAll = h("button", { class: "row action danger", disabled: count === 0 }, "Forget everything…");
    forgetAll.onclick = () => {
      if (Date.now() < confirmUntil) {
        confirmUntil = 0;
        ctx.send({ type: "forget", all: true });
        return;
      }
      confirmUntil = Date.now() + 4000;
      forgetAll.textContent = `Forget all ${count}? Click again`;
      setTimeout(() => (forgetAll.textContent = "Forget everything…"), 4000);
    };
    return h(
      "div",
      {},
      h("label", { class: "search" }, icon("search"), search),
      shown,
      card(toggle("Remember new things", prefs?.learn ?? true, (on) => ctx.set("learn", on), !prefs), forgetAll),
      note(`${count} ${count === 1 ? "memory" : "memories"}, stored only on this Mac. Hover a memory to forget it.`),
    );
  },
};
