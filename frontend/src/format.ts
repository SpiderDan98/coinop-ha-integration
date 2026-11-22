// Numbers, money, dates and durations in the user's language, in HA's time zone.
import type { HomeAssistant } from "./hass";
import { localize } from "./localize";

const QUANTITY_DECIMALS: Record<string, number> = { kWh: 3, L: 1, g: 1, ml: 1, h: 2, pcs: 0 };
/** Decimals of an amount under 1 of a unit, so that a coffee's 0.04 L doesn't read as 0. */
const SMALL_QUANTITY_DECIMALS: Record<string, number> = { L: 3 };
/** Units priced per a larger one, as bills are: a litre's price is shown per m³. */
const PRICE_UNITS: Record<string, { unit: string; factor: number }> = {
  L: { unit: "m³", factor: 1000 },
};

/** The unit a price per `unit` is shown in, and what a price per `unit` is multiplied by. */
export const priceUnit = (unit: string) => PRICE_UNITS[unit] ?? { unit, factor: 1 };

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
  const timeOfDay = new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone });
  const conjunction = new Intl.ListFormat(locale, { type: "conjunction" });
  const wallClockParts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  });
  /** "YYYY-MM-DDTHH:mm" as a clock in HA's time zone shows `time`. */
  const wallClock = (time: number) => {
    const parts = Object.fromEntries(
      wallClockParts.formatToParts(time).map(({ type, value }) => [type, value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  };
  const zoneOffset = (time: number) => Date.parse(`${wallClock(time)}Z`) - (time - (time % 60000));
  // Month keys name a calendar month, so they are formatted as UTC dates.
  const monthName = new Intl.DateTimeFormat(locale, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const monthShort = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" });
  const percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 });
  return {
    /** "YYYY-MM" of `iso` in HA's time zone, as the backend groups months. */
    month: (iso: string) => wallClock(Date.parse(iso)).slice(0, 7),
    /** "January 2026" for "2026-01". */
    monthName: (month: string) => monthName.format(new Date(`${month}-01T00:00Z`)),
    /** "Jan" for "2026-01". */
    monthShort: (month: string) => monthShort.format(new Date(`${month}-01T00:00Z`)),
    percent: (share: number) => percent.format(share),
    /** A `datetime-local` input's value, in HA's time zone. */
    toInput: (iso: string) => wallClock(Date.parse(iso)),
    /** The ISO time a `datetime-local` value means in HA's time zone, if it is one. */
    fromInput: (value: string) => {
      const asUtc = Date.parse(`${value}Z`);
      if (Number.isNaN(asUtc)) return undefined;
      // Twice, since the offset at the first guess may differ across a DST change.
      const guess = asUtc - zoneOffset(asUtc);
      return new Date(asUtc - zoneOffset(guess)).toISOString();
    },
    currencySymbol: currency.formatToParts(0).find(({ type }) => type === "currency")?.value ?? "",
    money: (amount: number) => currency.format(amount),
    /** A number input's value: no grouping, at most `digits` decimals. */
    toNumberInput: (value: number | null, digits: number) =>
      value === null ? "" : String(Number(value.toFixed(digits))),
    /** An amount input's value, with the currency's decimals. */
    toAmountInput: (amount: number) =>
      amount.toFixed(currency.resolvedOptions().maximumFractionDigits ?? 2),
    unitPrice: (price: number) => unitPrice.format(price),
    quantity: (quantity: number, unit: string) => {
      const small = Math.abs(quantity) < 1 ? SMALL_QUANTITY_DECIMALS[unit] : undefined;
      const maximumFractionDigits = small ?? QUANTITY_DECIMALS[unit] ?? 2;
      return `${quantity.toLocaleString(locale, { maximumFractionDigits })} ${unit}`;
    },
    date: (iso: string) => date.format(new Date(iso)),
    dateTime: (iso: string) => dateTime.format(new Date(iso)),
    /** "a, b and c" in the language. */
    list: (items: string[]) => conjunction.format(items),
    timeRange: (start: string, end: string) =>
      timeOfDay.formatRange(new Date(start), new Date(end)),
    /** "40 min", "3 h", "2 h 35 min"; never broken across lines. */
    duration: (seconds: number) => {
      const total = Math.round(seconds / 60);
      const [hours, minutes] = [Math.floor(total / 60), total % 60];
      const key = !hours ? "duration.minutes" : minutes ? "duration" : "duration.hours";
      return t(key, { hours, minutes }).replaceAll(" ", "\u00a0");
    },
  };
}

export type Format = ReturnType<typeof formatter>;
