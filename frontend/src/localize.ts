// Panel strings, bundled per language; missing languages and keys fall back to English.
import type { HomeAssistant } from "./hass";
import de from "./translations/de.json";
import en from "./translations/en.json";

const LANGUAGES: Record<string, Partial<typeof en>> = { en, de };

export type Key = keyof typeof en;

/** For keys built from backend values (e.g. Flag types) the panel may not know yet. */
export const isKey = (key: string): key is Key => key in en;

/** `hass.language` may carry a region ("de-CH"); translations are per language. */
export const panelLanguage = (hass: HomeAssistant) => {
  const base = hass.language.split("-")[0];
  return base in LANGUAGES ? base : "en";
};

export function localize(hass: HomeAssistant) {
  const strings = LANGUAGES[panelLanguage(hass)];
  return (key: Key, values: Record<string, string | number> = {}) =>
    (strings[key] ?? en[key]).replace(/\{(\w+)\}/g, (match, name: string) =>
      name in values ? String(values[name]) : match,
    );
}

export type Localize = ReturnType<typeof localize>;
