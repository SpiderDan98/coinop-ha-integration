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
}

export interface RunDetail extends RunSummary {
  job_name: string | null;
  note: string | null;
  line_items: LineItem[];
  subtotals: Record<Kind, number>;
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

export const previewDelete = async (hass: HomeAssistant, runIds: string[]) =>
  (await hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete_preview", run_ids: runIds }))
    .drop;

export const deleteRuns = (hass: HomeAssistant, runIds: string[]) =>
  hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete", run_ids: runIds });
