// Coin-op's websocket commands (custom_components/coinop/websocket/). Amounts,
// subtotals and totals arrive rounded to the currency; the panel only formats them.
import type { HomeAssistant, Message } from "./hass";

export const OUTCOMES = ["completed", "cancelled", "failed", "unknown"] as const;
export const KINDS = ["electricity", "water", "material", "other"] as const;
export type Outcome = (typeof OUTCOMES)[number];
export type Kind = (typeof KINDS)[number];
/** The kinds to show: Water only where a Device has water or a Line Item counts it. */
export const shownKinds = (water: boolean) => KINDS.filter((kind) => kind !== "water" || water);
export const hasWater = (devices: Device[] | undefined) =>
  devices?.some((device) => device.capabilities.includes("water")) ?? false;
export type Method = "measured" | "from_history" | "estimated" | "program_default" | "entered";
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
  /** The Program it ran; always null for a Device Type without Programs. */
  program: string | null;
  started: string;
  ended: string | null;
  outcome: Outcome | null;
  finalised: boolean;
  running_seconds: number;
  total: number;
  /** Null for a Device Type without Part Count. */
  part_count: number | null;
  cost_per_part: number | null;
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
  /** The Slots the measured total was attributed through, as their entities reported them. */
  slots: { number: number; type: string; colour: string | null }[];
  /** Split across several Materials: this Line Item's estimated share of the measured total. */
  share: number | null;
  /** A Dose's Line Item: its Dose and where its amount came from. */
  dose_id?: string;
  dose_source?: "program_default" | "default_row" | "stock_input";
  /** What Coin-op computed, kept while the user's override counts instead. */
  computed: Pick<LineItem, "quantity" | "unit_price" | "amount"> | null;
  /** Computed values update live until the Run is final. */
  locked: boolean;
  deletable: boolean;
}

export interface RunDetail extends RunSummary {
  job_name: string | null;
  note: string | null;
  /** The printer's measured total, which corrections of split Line Items never change. */
  usage: { at: string; value: number; unit: "mm" | "g" } | null;
  line_items: LineItem[];
  /** Thumbnail, Snapshot, then uploads by time. */
  images: RunImage[];
  /** How many photos a Run takes, of which media types and how large. */
  uploads: { limit: number; types: string[]; max_bytes: number };
  subtotals: Record<Kind, number>;
}

export interface Device {
  id: string;
  name: string;
  /** The Device Type, which the Devices tab groups by. */
  type: "3d_printer" | "washing_machine";
  /** What its Device Type has; the panel shows a part only for these. */
  capabilities: (
    | "job"
    | "images"
    | "material"
    | "part_count"
    | "average_power"
    | "program"
    | "doses"
    | "water"
    | "program_consumption"
  )[];
  /** The Device's subentry data as its flow wrote it; changed only by reconfiguring. */
  ha_settings: {
    status: { entity_id: string; attribute: string | null };
    /** Missing for a Device Type without job. */
    job?: {
      entity_id: string | null;
      attribute: string | null;
      /** Missing for Devices added before Material used existed. */
      material?: { entity_id: string; attribute: string | null; unit: string | null } | null;
      /** In Slot order; missing for Devices added before Slots existed. */
      slots?: string[];
      colour_attribute?: string | null;
      loaded_slot?: string | null;
    };
    /** Missing for Devices added before images existed. */
    images?: { thumbnail: string | null; camera: string | null; snapshot: boolean };
    consumption:
      | { source: "estimate"; running_power: number; paused_power: number | null }
      /** From the Program Defaults' kWh. */
      | { source: "per_program" }
      | { source: "energy"; entity_id: string; attribute: string | null }
      | {
          source: "power";
          entity_id: string;
          attribute: string | null;
          /** Fills gaps in the power reports. */
          running_power: number | null;
        };
    /** Missing for a Device Type without water. */
    water?: { source: "meter" | "flow" | "per_program" | "none" };
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
  /** Coin-op's own settings for the Device, set in the Devices tab. */
  settings: {
    tags_for_new_runs: string[];
    automatic_templates: string[];
    default_material: string | null;
    /** In order; each Dose becomes a Material Line Item on Runs that dose it. */
    doses: {
      id: string;
      material_id: string;
      /** An entity reporting how much is left in g or ml; an attribute names its unit. */
      stock?: { entity_id: string; attribute: string | null; unit: string | null };
    }[];
    /** The amount per Dose id in its Material's unit; a missing one is not dosed. The
     * kWh and litres a Run takes when not measured; missing ones are not set. A Run
     * uses the row of its Program, else the Default row. */
    program_defaults: {
      default: { doses: Record<string, number>; kwh?: number; litres?: number };
      programs: Record<string, Device["settings"]["program_defaults"]["default"]>;
    };
  };
  /** What its Program input offers, then the other Programs its Runs had. */
  known_programs: string[];
}

export type RunChange = "started" | "created" | "updated" | "ended" | "deleted";
export type RunsEvent = { runs: RunSummary[] } | { change: RunChange; run: RunSummary };

/** What Runs add up to; also how much the sensor totals fall when they are deleted. */
export interface Totals {
  cost: number;
  electricity_cost: number;
  water_cost: number;
  material_cost: number;
  other_cost: number;
  material_grams: number;
  energy_kwh: number;
  water_litres: number;
  runs: number;
  running_hours: number;
  flagged_runs: number;
}

export type Dimension = "kind" | "device" | "month" | "material" | "outcome" | "tag" | "program";

/**
 * One group's values along the dimensions asked for, then its totals. Cost, grams and
 * kWh sum the group's Line Items; a Run counts once in every group holding one of its
 * Line Items, so Material and Tag groups overlap. `month` is "YYYY-MM" of the Run's
 * start in HA's time zone; `null` is "none" (no Material, no Tag, no Program, Run still
 * open).
 */
export type Group = Totals &
  Partial<{
    kind: Kind;
    device_id: string;
    device_name: string;
    month: string;
    material_id: string | null;
    material_name: string | null;
    outcome: Outcome | null;
    tag: string | null;
    program: string | null;
  }>;

/** Only combinations that have Line Items; no Runs, no groups. `only` limits them to some
 * Runs and to the Line Items of some Materials (`null` for none). */
export const getAggregates = async (
  hass: HomeAssistant,
  groupBy: Dimension[],
  only: { run_ids?: string[]; material_ids?: (string | null)[] } = {},
) =>
  (
    await hass.callWS<{ groups: Group[] }>({
      type: "coinop/aggregates/get",
      group_by: groupBy,
      ...only,
    })
  ).groups;

/** `getAggregates` of every named grouping at once. */
export async function getGroupings<const G extends Record<string, Dimension[]>>(
  hass: HomeAssistant,
  groupings: G,
) {
  const names = Object.keys(groupings) as (keyof G)[];
  const groups = await Promise.all(names.map((name) => getAggregates(hass, groupings[name])));
  return Object.fromEntries(names.map((name, index) => [name, groups[index]])) as Record<
    keyof G,
    Group[]
  >;
}

/** All Runs first, then each change; resolves to the unsubscribe function. */
export const subscribeRuns = (hass: HomeAssistant, onEvent: (event: RunsEvent) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "coinop/runs/subscribe" });

export const getRun = async (hass: HomeAssistant, runId: string) =>
  (await hass.callWS<{ run: RunDetail }>({ type: "coinop/runs/get", run_id: runId })).run;

const runResult = async (hass: HomeAssistant, msg: Message) =>
  (await hass.callWS<{ run: RunDetail }>(msg)).run;

/** Start, end and Outcome only once the Run is finalised; no change recomputes a cost. */
export const updateRun = (
  hass: HomeAssistant,
  runId: string,
  changes: Partial<
    Pick<
      RunDetail,
      "name" | "note" | "started" | "ended" | "outcome" | "part_count" | "program" | "tags"
    >
  >,
) => runResult(hass, { type: "coinop/runs/update", run_id: runId, ...changes });

/** A Run made by hand, final at once. */
export const createRun = (
  hass: HomeAssistant,
  run: Pick<RunDetail, "device_id" | "name" | "started" | "ended" | "outcome" | "tags">,
) => runResult(hass, { type: "coinop/runs/create", ...run });

export const clearFlag = (hass: HomeAssistant, runId: string, flag: string) =>
  runResult(hass, { type: "coinop/runs/clear_flag", run_id: runId, flag });

/** End Run now: the open Run ends as Unknown and is finalised. */
export const endRun = (hass: HomeAssistant, runId: string) =>
  runResult(hass, { type: "coinop/runs/end", run_id: runId });

/** Multipart, as the websocket caps messages; a refusal throws its `code`. */
export const uploadImages = async (hass: HomeAssistant, runId: string, files: File[]) => {
  const body = new FormData();
  for (const file of files) body.append("file", file);
  const response = await hass.fetchWithAuth(`/api/coinop/runs/${runId}/images`, {
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
  runResult(hass, { type: "coinop/images/set_cover", run_id: runId, image_id: imageId });

export const deleteImage = (hass: HomeAssistant, runId: string, imageId: string) =>
  runResult(hass, { type: "coinop/images/delete", run_id: runId, image_id: imageId });

type Entered = Partial<
  Pick<LineItem, "label" | "unit" | "quantity" | "unit_price" | "amount" | "material_id">
>;

/** An amount back-computes the unit price; a computed Line Item becomes manual.
 * A new Material re-prices the Line Item and reweighs its measured length; between a
 * Material bought by the piece and one by weight only the unit changes. */
export const updateLineItem = (
  hass: HomeAssistant,
  runId: string,
  lineItemId: string,
  changes: Entered,
) =>
  runResult(hass, {
    type: "coinop/line_items/update",
    run_id: runId,
    line_item_id: lineItemId,
    ...changes,
  });

export const resetLineItem = (hass: HomeAssistant, runId: string, lineItemId: string) =>
  runResult(hass, { type: "coinop/line_items/reset", run_id: runId, line_item_id: lineItemId });

/** A Material Line Item names its Material and counts g or ml (pcs for one bought by
 * the piece) at its current price. */
export const addLineItem = (
  hass: HomeAssistant,
  runId: string,
  item: Entered & { kind: Exclude<Kind, "electricity"> },
) => runResult(hass, { type: "coinop/line_items/add", run_id: runId, ...item });

/** A copy of the template; `quantity` replaces an entered default quantity. */
export const addTemplateLineItem = (
  hass: HomeAssistant,
  runId: string,
  templateId: string,
  quantity?: number,
) =>
  runResult(hass, {
    type: "coinop/line_items/add_template",
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
      type: "coinop/line_items/save_as_template",
      run_id: runId,
      line_item_id: lineItemId,
      ...(label === undefined ? {} : { label }),
    })
  ).template;

export const deleteLineItem = (hass: HomeAssistant, runId: string, lineItemId: string) =>
  runResult(hass, { type: "coinop/line_items/delete", run_id: runId, line_item_id: lineItemId });

export const previewDelete = async (hass: HomeAssistant, runIds: string[]) =>
  (await hass.callWS<{ drop: Totals }>({ type: "coinop/runs/delete_preview", run_ids: runIds }))
    .drop;

export const deleteRuns = (hass: HomeAssistant, runIds: string[]) =>
  hass.callWS<{ drop: Totals }>({ type: "coinop/runs/delete", run_ids: runIds });

export const STATEMENT_DETAILS = ["detailed", "compact"] as const;
export const STATEMENT_LANGUAGES = ["en", "de"] as const;

/** The only option with a server-side default: the hub's Markup in %. */
export const getStatementDefaults = (hass: HomeAssistant) =>
  hass.callWS<{ markup: number }>({ type: "coinop/cost_statement/defaults" });

/** The signed path to download the PDF from, briefly; a null title means the default. */
export const createStatement = async (
  hass: HomeAssistant,
  runIds: string[],
  options: {
    title: string | null;
    note: string | null;
    detail: (typeof STATEMENT_DETAILS)[number];
    /** Each Run's Cover Image, in a Detailed statement. */
    images: boolean;
    language: (typeof STATEMENT_LANGUAGES)[number];
    markup: number;
  },
) =>
  (
    await hass.callWS<{ path: string }>({
      type: "coinop/cost_statement/create",
      run_ids: runIds,
      ...options,
    })
  ).path;
/** Names a Tag doesn't exist under yet are created. */
export const updateDeviceSettings = async (
  hass: HomeAssistant,
  deviceId: string,
  settings: Partial<Device["settings"]>,
) =>
  (
    await hass.callWS<{ settings: Device["settings"] }>({
      type: "coinop/devices/update_settings",
      device_id: deviceId,
      settings,
    })
  ).settings;

/** The mean measured kWh and litres of the Device's Completed Runs and how many Runs
 * that is, per Program row; the Default row's from Runs whose Program has no row. */
export const getMeasuredSuggestions = async (hass: HomeAssistant, deviceId: string) => {
  type Row = Partial<Record<"kwh" | "litres", { mean: number; runs: number }>>;
  return (
    await hass.callWS<{ suggestions: { default: Row; programs: Record<string, Row> } }>({
      type: "coinop/devices/measured_suggestions",
      device_id: deviceId,
    })
  ).suggestions;
};

/** A name another Tag has, ignoring case, is that Tag; resolves to the resulting Tag. */
export const createTag = async (hass: HomeAssistant, name: string) =>
  (await hass.callWS<{ tag: string }>({ type: "coinop/tags/create", name })).tag;

/** Renaming to another Tag's name merges both; resolves to the resulting Tag. */
export const renameTag = async (hass: HomeAssistant, tag: string, name: string) =>
  (await hass.callWS<{ tag: string }>({ type: "coinop/tags/rename", tag, name })).tag;

/** Removes the Tag from every Run and Device. */
export const deleteTag = (hass: HomeAssistant, tag: string) =>
  hass.callWS<Record<string, never>>({ type: "coinop/tags/delete", tag });

/** Current Devices only; a Run whose `device_id` isn't listed belongs to a removed Device. */
export const listDevices = async (hass: HomeAssistant) =>
  (await hass.callWS<{ devices: Device[] }>({ type: "coinop/devices/list" })).devices;

export const MATERIAL_FORMS = [
  "filament",
  "resin",
  "detergent",
  "fabric_softener",
  "laundry_additive",
] as const;
export type MaterialForm = (typeof MATERIAL_FORMS)[number];
export const PACK_UNITS = ["g", "ml", "pcs"] as const;
export type PackUnit = (typeof PACK_UNITS)[number];

/** What a Material is made of; `update` takes any part of it. One bought by the
 * piece ("pcs") has no density. */
export interface MaterialFields {
  name: string;
  form: MaterialForm;
  type: string;
  density: number | null;
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
  /** Exactly one is set: per piece when bought by the piece, else per gram. */
  price_per_gram: number | null;
  price_per_piece: number | null;
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
  density: number | null;
  pack_unit: PackUnit;
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

/** Tags are alphabetical; Runs and Devices name them. */
export type Catalog = { materials: Material[]; tags: string[]; templates: LineItemTemplate[] };

/** Every catalogue in the first event; afterwards only the one that changed. */
export const subscribeCatalog = (hass: HomeAssistant, onEvent: (event: Partial<Catalog>) => void) =>
  hass.connection.subscribeMessage(onEvent, { type: "coinop/catalog/subscribe" });

export const getMaterialTypes = async (hass: HomeAssistant) =>
  (await hass.callWS<{ types: MaterialType[] }>({ type: "coinop/materials/types" })).types;

export const createMaterial = (hass: HomeAssistant, material: MaterialFields) =>
  hass.callWS<{ material: Material }>({ type: "coinop/materials/create", material });

export const listFilaments = (hass: HomeAssistant) =>
  hass.callWS<Filaments>({ type: "coinop/spoolman/filaments" });

export const createMaterialFromSpoolman = (hass: HomeAssistant, filamentId: number) =>
  hass.callWS<{ material: Material }>({
    type: "coinop/materials/create_from_spoolman",
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
    type: "coinop/materials/update",
    material_id: materialId,
    material,
  });

export const archiveMaterial = (hass: HomeAssistant, materialId: string) =>
  hass.callWS<{ material: Material }>({
    type: "coinop/materials/archive",
    material_id: materialId,
  });

export const restoreMaterial = (hass: HomeAssistant, materialId: string) =>
  hass.callWS<{ material: Material }>({
    type: "coinop/materials/restore",
    material_id: materialId,
  });

/** `deleted` is false when Runs use the Material: it was archived instead. */
export const deleteMaterial = async (hass: HomeAssistant, materialId: string) =>
  (
    await hass.callWS<{ deleted: boolean }>({
      type: "coinop/materials/delete",
      material_id: materialId,
    })
  ).deleted;

export const createTemplate = (hass: HomeAssistant, template: TemplateFields) =>
  hass.callWS<{ template: LineItemTemplate }>({ type: "coinop/templates/create", template });

/** Runs keep their copies; only Line Items added afterwards follow. */
export const updateTemplate = (
  hass: HomeAssistant,
  templateId: string,
  template: Partial<TemplateFields>,
) =>
  hass.callWS<{ template: LineItemTemplate }>({
    type: "coinop/templates/update",
    template_id: templateId,
    template,
  });

/** Runs keep their copies; Devices stop adding it automatically. */
export const deleteTemplate = (hass: HomeAssistant, templateId: string) =>
  hass.callWS<Record<string, never>>({
    type: "coinop/templates/delete",
    template_id: templateId,
  });
