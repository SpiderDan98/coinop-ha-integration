// WattBill's websocket commands (custom_components/wattbill/websocket/). Amounts,
// subtotals and totals arrive rounded to the currency; the panel only formats them.
import type { HomeAssistant, Message } from "./hass";

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
  part_count: number;
  cost_per_part: number;
  /** Open Flags; a cleared Flag is gone. */
  flags: string[];
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
  /** What WattBill computed, kept while the user's override counts instead. */
  computed: Pick<LineItem, "quantity" | "unit_price" | "amount"> | null;
  /** Computed values update live until the Run is final. */
  locked: boolean;
  deletable: boolean;
}

export interface RunDetail extends RunSummary {
  job_name: string | null;
  note: string | null;
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
    consumption:
      | { source: "estimate"; running_power: number; paused_power: number | null }
      | { source: "energy"; entity_id: string; attribute: string | null }
      | {
          source: "power";
          entity_id: string;
          attribute: string | null;
          /** Fills gaps in the power reports. */
          running_power: number | null;
        };
    price: { source: "fixed"; value: number };
  };
  /** WattBill's own settings for the Device, set in the Devices tab. */
  settings: Record<string, unknown>;
}

export type RunChange = "started" | "updated" | "ended" | "deleted";
export type RunsEvent = { runs: RunSummary[] } | { change: RunChange; run: RunSummary };

/** How much the sensor totals fall when Runs are deleted. */
export interface Drop {
  cost: number;
  energy_kwh: number;
  material_grams: number;
  runs: number;
  flagged_runs: number;
}

export const KINDS: Kind[] = ["electricity", "material", "other"];
export const OUTCOMES: Outcome[] = ["completed", "cancelled", "failed", "unknown"];

/** All Runs first, then each change; resolves to the unsubscribe function. */
export const subscribeRuns = (hass: HomeAssistant, onEvent: (event: RunsEvent) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "wattbill/runs/subscribe" });

export const getRun = async (hass: HomeAssistant, runId: string) =>
  (await hass.callWS<{ run: RunDetail }>({ type: "wattbill/runs/get", run_id: runId })).run;

const runResult = async (hass: HomeAssistant, msg: Message) =>
  (await hass.callWS<{ run: RunDetail }>(msg)).run;

/** Start, end and Outcome only once the Run is finalised; no change recomputes a cost. */
export const updateRun = (
  hass: HomeAssistant,
  runId: string,
  changes: Partial<
    Pick<RunDetail, "name" | "note" | "started" | "ended" | "outcome" | "part_count">
  >,
) => runResult(hass, { type: "wattbill/runs/update", run_id: runId, ...changes });

export const clearFlag = (hass: HomeAssistant, runId: string, flag: string) =>
  runResult(hass, { type: "wattbill/runs/clear_flag", run_id: runId, flag });

/** End Run now: the open Run ends as Unknown and is finalised. */
export const endRun = (hass: HomeAssistant, runId: string) =>
  runResult(hass, { type: "wattbill/runs/end", run_id: runId });

type Entered = Partial<Pick<LineItem, "label" | "unit" | "quantity" | "unit_price" | "amount">>;

/** An amount back-computes the unit price; a computed Line Item becomes manual. */
export const updateLineItem = (
  hass: HomeAssistant,
  runId: string,
  lineItemId: string,
  changes: Entered,
) =>
  runResult(hass, {
    type: "wattbill/line_items/update",
    run_id: runId,
    line_item_id: lineItemId,
    ...changes,
  });

export const resetLineItem = (hass: HomeAssistant, runId: string, lineItemId: string) =>
  runResult(hass, { type: "wattbill/line_items/reset", run_id: runId, line_item_id: lineItemId });

/** Only Other Line Items are added by hand so far. */
export const addLineItem = (hass: HomeAssistant, runId: string, item: Entered) =>
  runResult(hass, { type: "wattbill/line_items/add", run_id: runId, kind: "other", ...item });

export const deleteLineItem = (hass: HomeAssistant, runId: string, lineItemId: string) =>
  runResult(hass, { type: "wattbill/line_items/delete", run_id: runId, line_item_id: lineItemId });

export const previewDelete = async (hass: HomeAssistant, runIds: string[]) =>
  (await hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete_preview", run_ids: runIds }))
    .drop;

export const deleteRuns = (hass: HomeAssistant, runIds: string[]) =>
  hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete", run_ids: runIds });
/** Current Devices only; a Run whose `device_id` isn't listed belongs to a removed Device. */
export const listDevices = async (hass: HomeAssistant) =>
  (await hass.callWS<{ devices: Device[] }>({ type: "wattbill/devices/list" })).devices;
