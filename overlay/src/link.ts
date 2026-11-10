import { type BotState, MOODS, type Mood, STATES } from "./character";

export type Command = "mute" | "unmute" | "sleep";

export type BackendEvent =
  | { type: "state"; state: BotState }
  | { type: "mood"; mood: Mood }
  | { type: "levels"; speech: number; mic: number }
  | { type: "status"; micOn: boolean; model: string; memories: number }
  | { type: "heard" | "said"; text: string };

const isOneOf = <T extends string>(values: readonly T[], v: unknown): v is T => typeof v === "string" && (values as readonly string[]).includes(v);
const isLevel = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const isText = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length < 2000;

/** Parses one message from the backend. Anything malformed or unknown is dropped, never half-applied. */
export function parseEvent(raw: string): BackendEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const e = data as Record<string, unknown>;
  switch (e.type) {
    case "state":
      return isOneOf(STATES, e.state) ? { type: "state", state: e.state } : null;
    case "mood":
      return isOneOf(MOODS, e.mood) ? { type: "mood", mood: e.mood } : null;
    case "levels":
      return isLevel(e.speech) && isLevel(e.mic) ? { type: "levels", speech: e.speech, mic: e.mic } : null;
    case "status":
      return typeof e.micOn === "boolean" && typeof e.model === "string" && Number.isInteger(e.memories)
        ? { type: "status", micOn: e.micOn, model: e.model, memories: e.memories as number }
        : null;
    case "heard":
    case "said":
      return isText(e.text) ? { type: e.type, text: e.text } : null;
    default:
      return null;
  }
}

export interface BackendLink {
  send(command: Command): void;
  readonly connected: boolean;
}

/** Keeps a connection to the backend open, reconnecting every couple of seconds while it is down. */
export function connectToBackend(onEvent: (e: BackendEvent) => void, onConnected: (connected: boolean) => void, url = "ws://127.0.0.1:8765"): BackendLink {
  let ws: WebSocket | null = null;
  const link = {
    connected: false,
    send(command: Command) {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "command", name: command }));
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
