import { type Theme, type ThemeName, themes } from "./character";
import type { ThemeChoice } from "./settings";

const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

export function resolveTheme(choice: ThemeChoice): { name: ThemeName; theme: Theme } {
  const name: ThemeName = choice === "system" ? (systemDark.matches ? "dark" : "light") : choice;
  return { name, theme: themes[name] };
}

/** Every token in design/character.json becomes a CSS variable, so pages never hard-code a colour. */
export function applyTheme(choice: ThemeChoice): ThemeName {
  const { name, theme } = resolveTheme(choice);
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme)) root.style.setProperty(`--${key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`, value);
  root.dataset.theme = name;
  return name;
}

export function onSystemThemeChange(callback: () => void): void {
  systemDark.addEventListener("change", callback);
}
