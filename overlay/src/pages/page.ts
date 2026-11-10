import type { BotState, Theme } from "../character";
import type { BackendEvent, Mic, Page, PrefKey, Prefs, Request, Stats, Status } from "../link";

type Reply<T extends BackendEvent["type"]> = Extract<BackendEvent, { type: T }>;

/** What a menu page can see and do. Data is null until the backend has answered. */
export interface Ctx {
  connected: boolean;
  state: BotState;
  status: Status | null;
  devices: Mic[] | null;
  voices: Reply<"voices"> | null;
  models: Reply<"models"> | null;
  memories: Reply<"memories"> | null;
  stats: Stats | null;
  /** Recent microphone levels, newest last, for the level meter. */
  micLevels: number[];
  theme: Theme;
  set<K extends PrefKey>(key: K, value: Prefs[K]): void;
  send(request: Request): void;
}

export interface PageDef {
  title: string;
  /** Replies to ask for when the page opens. */
  needs: Page[];
  /** The page rebuilds only when this changes, so a status update does not yank a slider out of your hand. */
  key(ctx: Ctx): unknown;
  render(ctx: Ctx): HTMLElement;
  /** Runs every frame while the page is showing, for live bits like the level meter. */
  tick?(ctx: Ctx): void;
}
