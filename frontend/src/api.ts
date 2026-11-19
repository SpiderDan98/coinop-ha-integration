// WattBill's websocket commands (custom_components/wattbill/websocket/). Amounts,
// subtotals and totals arrive rounded to the currency; the panel only formats them.
import type { HomeAssistant, Message } from "./hass";

export type Outcome = "completed" | "cancelled" | "failed" | "unknown";
export type Kind = "electricity" | "material" | "other";
export type Method = "measured" | "from_history" | "estimated" | "entered";
/** Running hours are the Run's running time without pauses. */
export type QuantityBasis = "entered" | "running_hours";

/** Fetched with `hass.fetchWithAuth`: the image views need authentication. */
export interface RunImage {
  id: string;
  kind: "thumbnail" | "snapshot" | "upload";
  created: string;
  url: string;
  tile_url: string;
}

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
  /** Alphabetical. */
  tags: string[];
  cover: RunImage | null;
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
  /** The Line Item Template it was copied from; the template may be gone since. */
  template_id: string | null;
  /** Running hours make the quantity computed, live until the Run is final. */
  basis: QuantityBasis | null;
  segments: { start: string; end: string; kwh: number; unit_price: number }[];
  /** Material Line Items: their Material, and a copy of it as it was when priced. */
  material_id: string | null;
  material: Pick<Material, "name" | "type" | "density" | "diameter" | "price_per_gram"> | null;
  /** Follows the printer's Material used input; `length` (mm) is the measured length. */
  measured: boolean;
  length: number | null;
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
  /** Thumbnail, Snapshot, then uploads by time. */
  images: RunImage[];
  subtotals: Record<Kind, number>;
}

export interface Device {
  id: string;
  name: string;
  /** The Device's subentry data as its flow wrote it; changed only by reconfiguring. */
  ha_settings: {
    status: { entity_id: string; attribute: string | null };
    job: {
      entity_id: string | null;
      attribute: string | null;
      /** Missing for Devices added before Material used existed. */
      material?: { entity_id: string; attribute: string | null; unit: string | null } | null;
    };
    /** Missing for Devices added before images existed. */
    images?: { thumbnail: string | null; camera: string | null; snapshot: boolean };
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
    price:
      | { source: "fixed"; value: number }
      | {
          source: "entity";
          entity_id: string;
          attribute: string | null;
          unit: string | null;
          factor: number | null;
        };
  };
  /** WattBill's own settings for the Device, set in the Devices tab. */
  settings: {
    tags_for_new_runs: string[];
    automatic_templates: string[];
    default_material: string | null;
  };
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
    Pick<RunDetail, "name" | "note" | "started" | "ended" | "outcome" | "part_count" | "tags">
  >,
) => runResult(hass, { type: "wattbill/runs/update", run_id: runId, ...changes });

export const clearFlag = (hass: HomeAssistant, runId: string, flag: string) =>
  runResult(hass, { type: "wattbill/runs/clear_flag", run_id: runId, flag });

/** End Run now: the open Run ends as Unknown and is finalised. */
export const endRun = (hass: HomeAssistant, runId: string) =>
  runResult(hass, { type: "wattbill/runs/end", run_id: runId });

export const UPLOAD_LIMIT = 10;
export const UPLOAD_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** Multipart, as the websocket caps messages; a refusal throws its `code`. */
export const uploadImages = async (hass: HomeAssistant, runId: string, files: File[]) => {
  const body = new FormData();
  for (const file of files) body.append("file", file);
  const response = await hass.fetchWithAuth(`/api/wattbill/runs/${runId}/images`, {
    method: "POST",
    body,
  });
  const result = (await response.json().catch(() => ({}))) as {
    images?: RunImage[];
    code?: string;
  };
  if (!response.ok || !result.images) throw new Error(result.code ?? "failed");
  return result.images;
};

/** Until that image is deleted; then the Cover Image falls back to the rule. */
export const setCover = (hass: HomeAssistant, runId: string, imageId: string) =>
  runResult(hass, { type: "wattbill/images/set_cover", run_id: runId, image_id: imageId });

export const deleteImage = (hass: HomeAssistant, runId: string, imageId: string) =>
  runResult(hass, { type: "wattbill/images/delete", run_id: runId, image_id: imageId });

type Entered = Partial<
  Pick<LineItem, "label" | "unit" | "quantity" | "unit_price" | "amount" | "material_id">
>;

/** An amount back-computes the unit price; a computed Line Item becomes manual.
 * A new Material re-prices the Line Item and reweighs its measured length. */
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

/** A Material Line Item names its Material and counts g or ml at its current price. */
export const addLineItem = (
  hass: HomeAssistant,
  runId: string,
  item: Entered & { kind: Exclude<Kind, "electricity"> },
) => runResult(hass, { type: "wattbill/line_items/add", run_id: runId, ...item });

/** A copy of the template; `quantity` replaces an entered default quantity. */
export const addTemplateLineItem = (
  hass: HomeAssistant,
  runId: string,
  templateId: string,
  quantity?: number,
) =>
  runResult(hass, {
    type: "wattbill/line_items/add_template",
    run_id: runId,
    template_id: templateId,
    ...(quantity === undefined ? {} : { quantity }),
  });

/** Computed Line Items have no label of their own, so they need `label`. */
export const saveAsTemplate = async (
  hass: HomeAssistant,
  runId: string,
  lineItemId: string,
  label?: string,
) =>
  (
    await hass.callWS<{ template: LineItemTemplate }>({
      type: "wattbill/line_items/save_as_template",
      run_id: runId,
      line_item_id: lineItemId,
      ...(label === undefined ? {} : { label }),
    })
  ).template;

export const deleteLineItem = (hass: HomeAssistant, runId: string, lineItemId: string) =>
  runResult(hass, { type: "wattbill/line_items/delete", run_id: runId, line_item_id: lineItemId });

export const previewDelete = async (hass: HomeAssistant, runIds: string[]) =>
  (await hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete_preview", run_ids: runIds }))
    .drop;

export const deleteRuns = (hass: HomeAssistant, runIds: string[]) =>
  hass.callWS<{ drop: Drop }>({ type: "wattbill/runs/delete", run_ids: runIds });
/** Names a Tag doesn't exist under yet are created. */
export const updateDeviceSettings = async (
  hass: HomeAssistant,
  deviceId: string,
  settings: Partial<Device["settings"]>,
) =>
  (
    await hass.callWS<{ settings: Device["settings"] }>({
      type: "wattbill/devices/update_settings",
      device_id: deviceId,
      settings,
    })
  ).settings;

/** Renaming to another Tag's name merges both; resolves to the resulting Tag. */
export const renameTag = async (hass: HomeAssistant, tag: string, name: string) =>
  (await hass.callWS<{ tag: string }>({ type: "wattbill/tags/rename", tag, name })).tag;

/** Removes the Tag from every Run and Device. */
export const deleteTag = (hass: HomeAssistant, tag: string) =>
  hass.callWS<Record<string, never>>({ type: "wattbill/tags/delete", tag });

/** Current Devices only; a Run whose `device_id` isn't listed belongs to a removed Device. */
export const listDevices = async (hass: HomeAssistant) =>
  (await hass.callWS<{ devices: Device[] }>({ type: "wattbill/devices/list" })).devices;

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

/** Linking to a Spoolman Filament; Spoolman then supplies the price and the details. */
export type SpoolmanLink = { source: "spoolman"; filament_id: number };

export interface Material extends Omit<MaterialFields, "price"> {
  id: string;
  archived: boolean;
  /** A linked Material keeps the last price per gram read from Spoolman. */
  price: MaterialFields["price"] | (SpoolmanLink & { per_gram: number | null });
  price_per_gram: number;
}

export interface Filament {
  id: number;
  name: string | null;
  vendor: string | null;
  type: string | null;
  density: number;
  diameter: number;
  colour: string | null;
  price_per_gram: number | null;
}

/** Reading the Filaments also brings the linked Materials up to date. */
export type Filaments = {
  status: "ok" | "unreachable" | "not_configured";
  filaments: Filament[];
};

export interface MaterialType {
  type: string;
  form: MaterialForm;
  density: number;
}

export interface LineItemTemplate {
  id: string;
  label: string;
  unit: string;
  unit_price: number;
  /** Not used with running hours. */
  default_quantity: number;
  basis: QuantityBasis;
}

export type TemplateFields = Omit<LineItemTemplate, "id">;

/** Every catalogue in the first event; afterwards only the one that changed. */
/** Tags are alphabetical; Runs and Devices name them. */
export type Catalog = { materials: Material[]; tags: string[]; templates: LineItemTemplate[] };

export const subscribeCatalog = (hass: HomeAssistant, onEvent: (event: Partial<Catalog>) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "wattbill/catalog/subscribe" });

export const getMaterialTypes = async (hass: HomeAssistant) =>
  (await hass.callWS<{ types: MaterialType[] }>({ type: "wattbill/materials/types" })).types;

export const createMaterial = (hass: HomeAssistant, material: MaterialFields) =>
  hass.callWS<{ material: Material }>({ type: "wattbill/materials/create", material });

export const listFilaments = (hass: HomeAssistant) =>
  hass.callWS<Filaments>({ type: "wattbill/spoolman/filaments" });

export const createMaterialFromSpoolman = (hass: HomeAssistant, filamentId: number) =>
  hass.callWS<{ material: Material }>({
    type: "wattbill/materials/create_from_spoolman",
    filament_id: filamentId,
  });

/** Answers the error code `spoolman_unreachable` when linking while Spoolman is away. */
export const updateMaterial = (
  hass: HomeAssistant,
  materialId: string,
  material: Partial<Omit<MaterialFields, "price">> & {
    price?: MaterialFields["price"] | SpoolmanLink;
  },
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

export const createTemplate = (hass: HomeAssistant, template: TemplateFields) =>
  hass.callWS<{ template: LineItemTemplate }>({ type: "wattbill/templates/create", template });

/** Runs keep their copies; only Line Items added afterwards follow. */
export const updateTemplate = (
  hass: HomeAssistant,
  templateId: string,
  template: Partial<TemplateFields>,
) =>
  hass.callWS<{ template: LineItemTemplate }>({
    type: "wattbill/templates/update",
    template_id: templateId,
    template,
  });

/** Runs keep their copies; Devices stop adding it automatically. */
export const deleteTemplate = (hass: HomeAssistant, templateId: string) =>
  hass.callWS<Record<string, never>>({
    type: "wattbill/templates/delete",
    template_id: templateId,
  });
