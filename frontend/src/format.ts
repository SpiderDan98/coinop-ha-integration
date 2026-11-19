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
  return {
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
    money: (amount: number) => currency.format(amount),
    /** A number input's value: no grouping, at most `digits` decimals. */
    toNumberInput: (value: number | null, digits: number) =>
      value === null ? "" : String(Number(value.toFixed(digits))),
    /** An amount input's value, with the currency's decimals. */
    toAmountInput: (amount: number) =>
      amount.toFixed(currency.resolvedOptions().maximumFractionDigits ?? 2),
    unitPrice: (price: number) => unitPrice.format(price),
    quantity: (quantity: number, unit: string) =>
      `${quantity.toLocaleString(locale, { maximumFractionDigits: QUANTITY_DECIMALS[unit] ?? 2 })} ${unit}`,
    date: (iso: string) => date.format(new Date(iso)),
    dateTime: (iso: string) => dateTime.format(new Date(iso)),
    duration: (seconds: number) => {
      const minutes = Math.round(seconds / 60);
      return t("duration", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
    },
  };
}

export type Format = ReturnType<typeof formatter>;
