// WattBill's websocket commands (custom_components/wattbill/websocket/). Amounts,
// subtotals and totals arrive rounded to the currency; the panel only formats them.
import type { HomeAssistant } from "./hass";

export type Outcome = "completed" | "cancelled" | "failed" | "unknown";
export type Kind = "electricity" | "material" | "other";
export type Method = "measured" | "from_history" | "estimated" | "entered";

export interface RunSummary {
  id: string;
  device_id: string;
  device_name: string;
  name: string | null;
  started: string;
  ended: string | null;
  outcome: Outcome | null;
  finalised: boolean;
  running_seconds: number;
  total: number;
}

export interface LineItem {
  id: string;
  kind: Kind;
  label: string | null;
  quantity: number | null;
  unit: string;
  unit_price: number;
  amount: number;
  method: Method | null;
  segments: { start: string; end: string; kwh: number; unit_price: number }[];
}

export interface RunDetail extends RunSummary {
  line_items: LineItem[];
  subtotals: Record<Kind, number>;
}

export interface Device {
  id: string;
  name: string;
  /** The Device's subentry data as its flow wrote it; changed only by reconfiguring. */
  ha_settings: {
    status: { entity_id: string; attribute: string | null };
    job: { entity_id: string | null; attribute: string | null };
    consumption: { source: "estimate"; running_power: number; paused_power: number | null };
    price: { source: "fixed"; value: number };
  };
  /** WattBill's own settings for the Device, set in the Devices tab. */
  settings: Record<string, unknown>;
}

export type RunChange = "started" | "updated" | "ended" | "deleted";
export type RunsEvent = { runs: RunSummary[] } | { change: RunChange; run: RunSummary };

export const KINDS: Kind[] = ["electricity", "material", "other"];

/** All Runs first, then each change; resolves to the unsubscribe function. */
export const subscribeRuns = (hass: HomeAssistant, onEvent: (event: RunsEvent) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "wattbill/runs/subscribe" });

export const getRun = async (hass: HomeAssistant, runId: string) =>
  (await hass.callWS<{ run: RunDetail }>({ type: "wattbill/runs/get", run_id: runId })).run;

/** Current Devices only; a Run whose `device_id` isn't listed belongs to a removed Device. */
export const listDevices = async (hass: HomeAssistant) =>
  (await hass.callWS<{ devices: Device[] }>({ type: "wattbill/devices/list" })).devices;
