// Numbers, money, dates and durations in the user's language, in HA's time zone.
import type { HomeAssistant } from "./hass";
import { localize } from "./localize";

const QUANTITY_DECIMALS: Record<string, number> = { kWh: 3, g: 1, ml: 1, h: 2, pcs: 0 };

export function formatter(hass: HomeAssistant) {
  const locale = hass.language;
  const t = localize(hass);
  const timeZone = hass.config.time_zone;
  const currency = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: hass.config.currency,
  });
  const unitPrice = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: hass.config.currency,
    maximumFractionDigits: 4,
  });
  const date = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  });
  const dateTime = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  });
  const time = new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone });
  return {
    money: (amount: number) => currency.format(amount),
    unitPrice: (price: number) => unitPrice.format(price),
    quantity: (quantity: number, unit: string) =>
      `${quantity.toLocaleString(locale, { maximumFractionDigits: QUANTITY_DECIMALS[unit] ?? 2 })} ${unit}`,
    date: (iso: string) => date.format(new Date(iso)),
    dateTime: (iso: string) => dateTime.format(new Date(iso)),
    timeRange: (start: string, end: string) => time.formatRange(new Date(start), new Date(end)),
    duration: (seconds: number) => {
      const minutes = Math.round(seconds / 60);
      return t("duration", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
    },
  };
}

export type Format = ReturnType<typeof formatter>;
