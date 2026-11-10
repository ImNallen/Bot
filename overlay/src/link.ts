import { type BotState, MOODS, type Mood, STATES } from "./character";

export type Command = "mute" | "unmute" | "sleep";

/** The backend settings the menu can change, in the menu's own units. */
export interface Prefs {
  mic: string | null;
  voice: string;
  speed: number;
  sensitivity: number;
  pause: number;
  interrupt: boolean;
  keepLoaded: boolean;
  thinking: boolean;
  learn: boolean;
  memoryOn: boolean;
}
export type PrefKey = Exclude<keyof Prefs, "memoryOn">;

export interface Status {
  type: "status";
  micOn: boolean;
  model: string;
  memories: number;
  prefs: Prefs;
}
export interface Mic {
  name: string;
  detail: string;
  default: boolean;
}
export interface VoiceInfo {
  id: string;
  name: string;
  detail: string;
}
export interface ModelInfo {
  name: string;
  size: number;
  quantization: string;
  loaded: boolean;
}
export interface MemoryItem {
  id: number;
  kind: "fact" | "event";
  text: string;
  on: string | null;
  learned: string;
  followUp: boolean;
}
export interface Stats {
  type: "stats";
  on: boolean;
  since: string | null;
  talkingSeconds: number;
  conversations: number;
  interruptions: number;
  replyStart: number | null;
  cloudBytes: number;
  moods: { mood: Mood; share: number }[];
  perDay: number[];
  favoriteWord: string | null;
  saidQuestion: number;
  chattyHour: number | null;
  longestChatSeconds: number;
}

export type BackendEvent =
  | { type: "state"; state: BotState }
  | { type: "mood"; mood: Mood }
  | { type: "levels"; speech: number; mic: number }
  | Status
  | { type: "heard"; text: string }
  | { type: "said"; text: string }
  | { type: "notice"; text: string }
  | { type: "devices"; inputs: Mic[] }
  | { type: "voices"; engine: string; voices: VoiceInfo[] }
  | { type: "models"; server: string; running: boolean; version: string | null; installed: ModelInfo[] }
  | { type: "memories"; on: boolean; items: MemoryItem[] }
  | Stats;

export type Page = "devices" | "voices" | "models" | "memories" | "stats";
export type Request =
  | { type: "command"; name: Command }
  | { type: "set"; key: PrefKey; value: Prefs[PrefKey] }
  | { type: "set"; key: "model"; value: string }
  | { type: "get"; what: Page }
  | { type: "preview"; voice: string }
  | { type: "forget"; id: number }
  | { type: "forget"; all: true };

type Check<T> = (v: unknown) => v is T;
const str: Check<string> = (v): v is string => typeof v === "string" && v.length < 2000;
const text: Check<string> = (v): v is string => str(v) && v.length > 0;
const num: Check<number> = (v): v is number => typeof v === "number" && Number.isFinite(v);
const count: Check<number> = (v): v is number => Number.isInteger(v) && (v as number) >= 0;
const level: Check<number> = (v): v is number => num(v) && v >= 0;
const bool: Check<boolean> = (v): v is boolean => typeof v === "boolean";
const oneOf = <T extends string>(values: readonly T[]): Check<T> => (v): v is T => typeof v === "string" && (values as readonly string[]).includes(v);
const nullable = <T>(check: Check<T>): Check<T | null> => (v): v is T | null => v === null || check(v);
const list = <T>(check: Check<T>): Check<T[]> => (v): v is T[] => Array.isArray(v) && v.length <= 1000 && v.every(check);
const shape = <T>(fields: { [K in keyof T]: Check<T[K]> }): Check<T> => (v): v is T =>
  typeof v === "object" && v !== null && Object.entries(fields).every(([k, check]) => (check as Check<unknown>)((v as Record<string, unknown>)[k]));

const prefs = shape<Prefs>({ mic: nullable(text), voice: text, speed: num, sensitivity: num, pause: num, interrupt: bool, keepLoaded: bool, thinking: bool, learn: bool, memoryOn: bool });
const CHECKS: { [T in BackendEvent["type"]]: Check<Omit<Extract<BackendEvent, { type: T }>, "type">> } = {
  state: shape({ state: oneOf(STATES) }),
  mood: shape({ mood: oneOf(MOODS) }),
  levels: shape({ speech: level, mic: level }),
  status: shape({ micOn: bool, model: str, memories: count, prefs }),
  heard: shape({ text }),
  said: shape({ text }),
  notice: shape({ text }),
  devices: shape({ inputs: list(shape<Mic>({ name: text, detail: str, default: bool })) }),
  voices: shape({ engine: str, voices: list(shape<VoiceInfo>({ id: text, name: text, detail: str })) }),
  models: shape({
    server: str,
    running: bool,
    version: nullable(str),
    installed: list(shape<ModelInfo>({ name: text, size: count, quantization: str, loaded: bool })),
  }),
  memories: shape({
    on: bool,
    items: list(shape<MemoryItem>({ id: count, kind: oneOf(["fact", "event"] as const), text, on: nullable(str), learned: str, followUp: bool })),
  }),
  stats: shape<Omit<Stats, "type">>({
    on: bool,
    since: nullable(str),
    talkingSeconds: count,
    conversations: count,
    interruptions: count,
    replyStart: nullable(num),
    cloudBytes: count,
    moods: list(shape({ mood: oneOf(MOODS), share: level })),
    perDay: list(count),
    favoriteWord: nullable(str),
    saidQuestion: count,
    chattyHour: nullable(count),
    longestChatSeconds: count,
  }),
};

/** Parses one message from the backend. Anything malformed or unknown is dropped, never half-applied. */
export function parseEvent(raw: string): BackendEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const type = (data as { type?: unknown }).type;
  if (typeof type !== "string" || !Object.hasOwn(CHECKS, type)) return null;
  return CHECKS[type as BackendEvent["type"]](data) ? (data as BackendEvent) : null;
}

export interface BackendLink {
  send(request: Request): void;
  readonly connected: boolean;
}

/** Keeps a connection to the backend open, reconnecting every couple of seconds while it is down. */
export function connectToBackend(onEvent: (e: BackendEvent) => void, onConnected: (connected: boolean) => void, url = "ws://127.0.0.1:8765"): BackendLink {
  let ws: WebSocket | null = null;
  const link = {
    connected: false,
    send(request: Request) {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(request));
    },
  };
  const open = () => {
    ws = new WebSocket(url);
    ws.onopen = () => {
      link.connected = true;
      onConnected(true);
    };
    ws.onmessage = (m) => {
      const event = typeof m.data === "string" ? parseEvent(m.data) : null;
      if (event) onEvent(event);
    };
    ws.onclose = () => {
      link.connected = false;
      onConnected(false);
      setTimeout(open, 2000);
    };
  };
  open();
  return link;
}
