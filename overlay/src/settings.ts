import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export type ThemeChoice = "system" | "light" | "dark";
export type SizeChoice = "s" | "m" | "l";

/** Mirrors OverlaySettings in src-tauri/src/settings.rs, which owns, saves and broadcasts it. */
export interface OverlaySettings {
  theme: ThemeChoice;
  size: SizeChoice;
  keepAway: boolean;
  hideInFullscreen: boolean;
  stayPut: boolean;
  hidden: boolean;
}

export const BODY_PT: Record<SizeChoice, number> = { s: 96, m: 120, l: 144 };

export const getSettings = () => invoke<OverlaySettings>("get_settings");
export const updateSettings = (patch: Partial<OverlaySettings>) => invoke<OverlaySettings>("update_settings", { patch });
export const onSettings = (callback: (s: OverlaySettings) => void) => listen<OverlaySettings>("settings", ({ payload }) => callback(payload));
