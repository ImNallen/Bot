/** Tiny DOM builders for the menu pages. Text always goes in as text, never as HTML. */

type Child = Node | string | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { class?: string } = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  const { class: className, ...rest } = props;
  if (className) node.className = className;
  Object.assign(node, rest);
  for (const child of children) if (child) node.append(child);
  return node;
}

const SVG = "http://www.w3.org/2000/svg";
const ICONS = {
  check: "M3.5 8.5 6.5 11.5 12.5 4.5",
  chevron: "M6 3.5 10.5 8 6 12.5",
  back: "M10 3.5 5.5 8 10 12.5",
  play: "M5.5 4v8l7-4Z",
  trash: "M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5",
  search: "M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10ZM10.7 10.7 14 14",
};

export function icon(name: keyof typeof ICONS, className = "icon"): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("class", `${className} i-${name}`);
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

export const section = (title: string | Node | null, ...children: Child[]) =>
  h("section", {}, title ? h("h2", {}, title) : null, ...children);

export const card = (...rows: Child[]) => h("div", { class: "card" }, ...rows);

export const note = (text: string) => h("p", { class: "note" }, text);

/** Two-line label: a title and a quieter detail under it. */
export const label = (title: string, detail?: string) =>
  h("span", { class: "label" }, h("span", {}, title), detail ? h("small", {}, detail) : null);

/** A row you pick from a list. The chosen one shows a check. */
export function choice(title: string, detail: string, chosen: boolean, pick: () => void, ...extra: Child[]): HTMLButtonElement {
  return h("button", { class: `row choice${chosen ? " chosen" : ""}`, onclick: pick }, ...extra, label(title, detail), chosen ? icon("check") : null);
}

export function toggle(title: string, on: boolean, flip: (on: boolean) => void, disabled = false): HTMLLabelElement {
  const input = h("input", { type: "checkbox", checked: on, disabled, onchange: () => flip(input.checked) });
  return h("label", { class: "row" }, h("span", {}, title), input);
}

interface SliderOptions {
  min: number;
  max: number;
  step: number;
  value: number;
  show: (v: number) => string;
  ends?: [string, string];
  /** Called once when the knob is let go, so dragging does not flood the backend. */
  commit: (v: number) => void;
  disabled?: boolean;
}

export function slider(title: string, o: SliderOptions): HTMLDivElement {
  const shown = h("span", { class: "value" }, o.show(o.value));
  const input = h("input", { type: "range", min: String(o.min), max: String(o.max), step: String(o.step), value: String(o.value), disabled: !!o.disabled });
  const paint = () => {
    shown.textContent = o.show(Number(input.value));
    input.style.setProperty("--fill", `${((Number(input.value) - o.min) / (o.max - o.min)) * 100}%`);
  };
  input.oninput = paint;
  input.onchange = () => o.commit(Number(input.value));
  paint();
  return h(
    "div",
    { class: "slider" },
    h("div", { class: "slider-head" }, h("span", {}, title), shown),
    input,
    o.ends ? h("div", { class: "slider-ends" }, h("span", {}, o.ends[0]), h("span", {}, o.ends[1])) : null,
  );
}

/** Keeps a slider's knob where the backend says, unless someone is holding it. */
export function syncSlider(root: HTMLElement, value: number): void {
  const input = root.querySelector<HTMLInputElement>("input[type=range]");
  if (!input || input.matches(":active") || Number(input.value) === value) return;
  input.value = String(value);
  input.dispatchEvent(new Event("input"));
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${Math.round(bytes / 1e9)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  if (bytes >= 1e3) return `${Math.round(bytes / 1e3)} KB`;
  return `${bytes} B`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Parses YYYY-MM-DD as a local calendar day. */
export function day(iso: string): Date {
  const [y = 1970, m = 1, d = 1] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const shortDate = (date: Date) => `${date.getDate()} ${MONTHS[date.getMonth()]}`;

export function daysBetween(from: Date, to: Date): number {
  return Math.round((day(isoDay(to)).getTime() - day(isoDay(from)).getTime()) / 86_400_000);
}

export const isoDay = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

/** "Today", "Yesterday", "In 3 days", "5 days ago", or a date for anything further out. */
export function relativeDay(date: Date, today = new Date()): string {
  const days = daysBetween(today, date);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  if (days > 1 && days <= 6) return `${DAYS[date.getDay()]} · in ${days} days`;
  if (days < -1 && days >= -6) return `${-days} days ago`;
  return shortDate(date);
}

/** "qwen3.6:35b-a3b-q8_0" reads as "qwen3.6 35B-A3B" with quantization "Q8". */
export function modelLabel(name: string): { name: string; quant: string } {
  const [base = name, tag = ""] = name.split(":");
  const quant: string = tag.match(/(?:^|-)(q\d+(?:_[a-z0-9]+)*|fp16|bf16)$/i)?.[1] ?? "";
  const size = tag.slice(0, tag.length - quant.length).replace(/-$/, "").toUpperCase().replace("LATEST", "");
  return { name: size ? `${base} ${size}` : base, quant: quant.toUpperCase().replace(/_0$/, "") };
}
