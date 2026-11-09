import { type BotState, MOODS, type Mood, STATES } from "./character";

export type BackendEvent =
  | { type: "state"; state: BotState }
  | { type: "mood"; mood: Mood }
  | { type: "levels"; speech: number; mic: number };

const isOneOf = <T extends string>(values: readonly T[], v: unknown): v is T => typeof v === "string" && (values as readonly string[]).includes(v);
const isLevel = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;

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
    default:
      return null;
  }
}

/** Keeps a connection to the backend open, reconnecting every couple of seconds while it is down. */
export function connectToBackend(url: string, onEvent: (e: BackendEvent) => void, onConnected: (connected: boolean) => void): void {
  const open = () => {
    const ws = new WebSocket(url);
    ws.onopen = () => onConnected(true);
    ws.onmessage = (m) => {
      const event = typeof m.data === "string" ? parseEvent(m.data) : null;
      if (event) onEvent(event);
    };
    ws.onclose = () => {
      onConnected(false);
      setTimeout(open, 2000);
    };
  };
  open();
}
