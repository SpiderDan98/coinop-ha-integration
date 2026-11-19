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

export type RunChange = "started" | "updated" | "ended" | "deleted";
export type RunsEvent = { runs: RunSummary[] } | { change: RunChange; run: RunSummary };

export const KINDS: Kind[] = ["electricity", "material", "other"];

/** All Runs first, then each change; resolves to the unsubscribe function. */
export const subscribeRuns = (hass: HomeAssistant, onEvent: (event: RunsEvent) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "wattbill/runs/subscribe" });

export const getRun = async (hass: HomeAssistant, runId: string) =>
  (await hass.callWS<{ run: RunDetail }>({ type: "wattbill/runs/get", run_id: runId })).run;

export type MaterialForm = "filament" | "resin";
export type PackUnit = "g" | "ml";

/** What a Material is made of; `update` takes any part of it. */
export interface MaterialFields {
  name: string;
  form: MaterialForm;
  type: string;
  density: number;
  vendor: string | null;
  colour: string | null;
  diameter: number | null;
  default_for_type: boolean;
  price: { source: "fixed"; pack_price: number; pack_size: number; pack_unit: PackUnit };
}

export interface Material extends MaterialFields {
  id: string;
  archived: boolean;
  price_per_gram: number;
}

export interface MaterialType {
  type: string;
  form: MaterialForm;
  density: number;
}

/** Every catalogue in the first event; afterwards only the one that changed. */
export type Catalog = { materials: Material[] };

export const subscribeCatalog = (hass: HomeAssistant, onEvent: (event: Partial<Catalog>) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "wattbill/catalog/subscribe" });

export const getMaterialTypes = async (hass: HomeAssistant) =>
  (await hass.callWS<{ types: MaterialType[] }>({ type: "wattbill/materials/types" })).types;

export const createMaterial = (hass: HomeAssistant, material: MaterialFields) =>
  hass.callWS<{ material: Material }>({ type: "wattbill/materials/create", material });

export const updateMaterial = (
  hass: HomeAssistant,
  materialId: string,
  material: Partial<MaterialFields>,
) =>
  hass.callWS<{ material: Material }>({
    type: "wattbill/materials/update",
    material_id: materialId,
    material,
  });

export const archiveMaterial = (hass: HomeAssistant, materialId: string) =>
  hass.callWS<{ material: Material }>({
    type: "wattbill/materials/archive",
    material_id: materialId,
  });

export const restoreMaterial = (hass: HomeAssistant, materialId: string) =>
  hass.callWS<{ material: Material }>({
    type: "wattbill/materials/restore",
    material_id: materialId,
  });

/** `deleted` is false when Runs use the Material: it was archived instead. */
export const deleteMaterial = async (hass: HomeAssistant, materialId: string) =>
  (
    await hass.callWS<{ deleted: boolean }>({
      type: "wattbill/materials/delete",
      material_id: materialId,
    })
  ).deleted;
