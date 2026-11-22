// Seam 2: a fake `hass` whose websocket calls and authenticated fetches are
// answered by canned responses.
// The recorded ones come from the backend tests (tests/contract.py), so they have
// exactly the shapes the backend sends.
import type { HomeAssistant, Message } from "../src/hass";
import type {
  Catalog,
  Device,
  Dimension,
  Group,
  Totals,
  SpoolmanState,
  getMeasuredSuggestions,
  LineItemTemplate,
  Material,
  MaterialType,
  RunChange,
  RunDetail,
  RunImage,
  RunSummary,
} from "../src/api";
import aggregatesByProgram from "./fixtures/backend/aggregates-by-program.json";
import aggregatesGet from "./fixtures/backend/aggregates-get.json";
import aggregatesOtherProgram from "./fixtures/backend/aggregates-other-program.json";
import catalogSubscribe from "./fixtures/backend/catalog-subscribe.json";
import catalogSubscribeOtherDoses from "./fixtures/backend/catalog-subscribe-other-doses.json";
import catalogSubscribeOtherJob from "./fixtures/backend/catalog-subscribe-other-job.json";
import costStatementCreate from "./fixtures/backend/cost-statement-create.json";
import costStatementDefaults from "./fixtures/backend/cost-statement-defaults.json";
import devicesList from "./fixtures/backend/devices-list.json";
import devicesListCoffeeMachine from "./fixtures/backend/devices-list-coffee-machine.json";
import devicesListDishwasher from "./fixtures/backend/devices-list-dishwasher.json";
import devicesListElectricityNone from "./fixtures/backend/devices-list-electricity-none.json";
import devicesListEvCharger from "./fixtures/backend/devices-list-ev-charger.json";
import devicesListOther from "./fixtures/backend/devices-list-other.json";
import devicesListOtherDoses from "./fixtures/backend/devices-list-other-doses.json";
import devicesListOtherImages from "./fixtures/backend/devices-list-other-images.json";
import devicesListOtherJob from "./fixtures/backend/devices-list-other-job.json";
import devicesListOtherProgram from "./fixtures/backend/devices-list-other-program.json";
import devicesListOtherProgramDoses from "./fixtures/backend/devices-list-other-program-doses.json";
import devicesListOtherWater from "./fixtures/backend/devices-list-other-water.json";
import devicesListOven from "./fixtures/backend/devices-list-oven.json";
import devicesListPerProgram from "./fixtures/backend/devices-list-per-program.json";
import devicesListRoboticMower from "./fixtures/backend/devices-list-robotic-mower.json";
import devicesListTumbleDryer from "./fixtures/backend/devices-list-tumble-dryer.json";
import devicesListTumbleDryerFromMiele from "./fixtures/backend/devices-list-tumble-dryer-from-miele.json";
import devicesListWashingMachine from "./fixtures/backend/devices-list-washing-machine.json";
import devicesMeasuredSuggestions from "./fixtures/backend/devices-measured-suggestions.json";
import devicesMeasuredSuggestionsOven from "./fixtures/backend/devices-measured-suggestions-oven.json";
import devicesMeasuredSuggestionsSmall from "./fixtures/backend/devices-measured-suggestions-small.json";
import imagesDelete from "./fixtures/backend/images-delete.json";
import imagesSetCover from "./fixtures/backend/images-set-cover.json";
import imagesUploadTooMany from "./fixtures/backend/images-upload-too-many.json";
import imagesUpload from "./fixtures/backend/images-upload.json";
import lineItemsAdd from "./fixtures/backend/line-items-add.json";
import lineItemsAddElectricity from "./fixtures/backend/line-items-add-electricity.json";
import lineItemsAddMaterial from "./fixtures/backend/line-items-add-material.json";
import lineItemsMaterial from "./fixtures/backend/line-items-material.json";
import lineItemsAddTemplate from "./fixtures/backend/line-items-add-template.json";
import lineItemsAddWater from "./fixtures/backend/line-items-add-water.json";
import lineItemsSplit from "./fixtures/backend/line-items-split.json";
import lineItemsSaveAsTemplate from "./fixtures/backend/line-items-save-as-template.json";
import lineItemsUpdate from "./fixtures/backend/line-items-update.json";
import materialsCreateDishwasherAndBeverage from "./fixtures/backend/materials-create-dishwasher-and-beverage.json";
import materialsCreateLaundry from "./fixtures/backend/materials-create-laundry.json";
import materialsCreateOther from "./fixtures/backend/materials-create-other.json";
import materialsTypes from "./fixtures/backend/materials-types.json";
import runsCreate from "./fixtures/backend/runs-create.json";
import runsDeletePreview from "./fixtures/backend/runs-delete-preview.json";
import runsGet from "./fixtures/backend/runs-get.json";
import runsGetCoffeeMachine from "./fixtures/backend/runs-get-coffee-machine.json";
import runsGetDrying from "./fixtures/backend/runs-get-drying.json";
import runsGetElectricityNone from "./fixtures/backend/runs-get-electricity-none.json";
import runsGetOther from "./fixtures/backend/runs-get-other.json";
import runsGetOtherDoses from "./fixtures/backend/runs-get-other-doses.json";
import runsGetOtherImages from "./fixtures/backend/runs-get-other-images.json";
import runsGetOtherJob from "./fixtures/backend/runs-get-other-job.json";
import runsGetOtherProgram from "./fixtures/backend/runs-get-other-program.json";
import runsGetOtherWater from "./fixtures/backend/runs-get-other-water.json";
import runsGetPerProgram from "./fixtures/backend/runs-get-per-program.json";
import runsGetRoboticMower from "./fixtures/backend/runs-get-robotic-mower.json";
import runsGetWashingMachine from "./fixtures/backend/runs-get-washing-machine.json";
import runsGetWater from "./fixtures/backend/runs-get-water.json";
import runsSubscribe from "./fixtures/backend/runs-subscribe.json";
import spoolmanMaterials from "./fixtures/backend/spoolman-materials.json";
import spoolmanMerge from "./fixtures/backend/spoolman-merge.json";
import spoolmanReadUnavailable from "./fixtures/backend/spoolman-read-unavailable.json";
import spoolmanRead from "./fixtures/backend/spoolman-read.json";
import tagsRename from "./fixtures/backend/tags-rename.json";
import templatesUpdate from "./fixtures/backend/templates-update.json";

const [snapshot, ...changes] = runsSubscribe;
const found = <T>(value: T | undefined, what: string) => {
  if (value === undefined) throw new Error(`nothing recorded for ${what}`);
  return value;
};
const byProgram = aggregatesByProgram as {
  runs: RunSummary[];
  aggregates: { group_by: Dimension[]; run_ids: string[]; groups: Group[] }[];
};

export const recorded = {
  /** First event of `coinop/runs/subscribe`: the Runs "benchy", "helmet", "cancelled". */
  snapshot: { runs: (snapshot as { runs: RunSummary[] }).runs },
  /** Then the Run "print-live" is started, updated (45 min in) and ended. */
  changes: changes as { change: RunChange; run: RunSummary }[],
  /** `coinop/runs/get` for every recorded Run; "print-live" while still open, with its
   * measured Material ("print-live-material") locked and its automatic template
   * "print-live-wear" counting running hours. "benchy" has a Thumbnail and a Snapshot and
   * its measured PLA Basic Black ("benchy-pla"); "helmet" only a Snapshot and a measured
   * length without Material ("helmet-filament"). */
  runs: runsGet.map((result) => result.run as RunDetail),
  /** `coinop/runs/get` of Kobra's open Run "drying" while its ACE dries: first 0 of
   * the 10 minutes its drying power is learned from, so drying is pending; then
   * learned, so the Projected Total includes it. */
  drying: runsGetDrying.map((result) => result.run as RunDetail),
  /** `coinop/aggregates/get` over the snapshot's Runs (all in January 2026), for each
   * grouping the Overview and Analysis ask for, then ungrouped for each selection of them
   * (`run_ids`, sorted). */
  aggregates: aggregatesGet as { group_by: Dimension[]; run_ids?: string[]; groups: Group[] }[],
  /** `coinop/runs/list` of Kobra's "vase" and the "device-washer" Runs "monday" and
   * "tuesday" (Cotton 60°, 0.07 and 0.57), "eco" (Eco 40-60, 0.07) and "unknown" (no
   * Program, 0.07), with `coinop/aggregates/get` of those four by Program. */
  programs: byProgram,
  /** `coinop/runs/create`: Kobra's manual Run "manual" ("Bracket", Tag "Batch 7"),
   * estimated from average power. */
  manualRun: runsCreate.run as RunDetail,
  /** `coinop/cost_statement/defaults` with the hub's default Markup at 10 %. */
  statementDefaults: costStatementDefaults,
  /** `coinop/cost_statement/create`: the signed path to download it from. */
  statementCreate: costStatementCreate,
  /** `coinop/runs/delete_preview` for "helmet". */
  deletePreview: runsDeletePreview as { drop: Totals },
  /** The upload of one photo to "benchy", and of ten more, refused. */
  upload: imagesUpload as { images: RunImage[] },
  uploadTooMany: imagesUploadTooMany,
  /** `coinop/images/set_cover`: "benchy" with that upload picked as Cover Image. */
  setCover: imagesSetCover.run as RunDetail,
  /** `coinop/images/delete` of that upload: "benchy" without it again. */
  deleteImage: imagesDelete.run as RunDetail,
  /** `coinop/line_items/update`: Benchy's electricity overridden to an amount of 0.10. */
  lineItemsUpdate: lineItemsUpdate as { run: RunDetail },
  /** `coinop/line_items/add`: a refund of -2.00 ("helmet-refund") added to Helmet. */
  lineItemsAdd: lineItemsAdd as { run: RunDetail },
  /** `coinop/line_items/update`: PETG White picked for Helmet's measured 30 m
   * ("helmet-filament"), which had no Material. */
  lineItemsMaterial: lineItemsMaterial as { run: RunDetail },
  /** `coinop/line_items/add`: 3 g of PETG White ("benchy-petg") added to Benchy. */
  lineItemsAddMaterial: lineItemsAddMaterial as { run: RunDetail },
  /** `coinop/line_items/update` of a Run ("keychain") split across two Slots: 75% to
   * PLA Basic Black ("keychain-pla"), 25% to PETG White ("keychain-petg"), whose quantity
   * was corrected to 4 g. */
  splitRun: lineItemsSplit.run as RunDetail,
  /** `coinop/line_items/save_as_template`: Benchy's "Nozzle wear" as "template-nozzle". */
  saveAsTemplate: lineItemsSaveAsTemplate as { template: LineItemTemplate },
  /** `coinop/line_items/add_template`: 2 × "template-nozzle" added to Benchy ("benchy-nozzle"). */
  lineItemsAddTemplate: lineItemsAddTemplate as { run: RunDetail },
  /** `coinop/templates/update`: "template-packaging" repriced to 0.60. */
  templateUpdate: templatesUpdate as { template: LineItemTemplate },
  /** `coinop/devices/list`: only "device-kobra" (automatic template "template-wear",
   * Material used input in mm, default Material "pla-black"); "device-mini" (Runs only)
   * was removed. */
  devices: devicesList.devices as Device[],
  /** `coinop/devices/list` with only "device-washer", a washing machine on an energy meter. */
  washer: devicesListWashingMachine.devices[0] as Device,
  /** `coinop/devices/list` with only "device-dishwasher", a Dishwasher on an energy meter
   * with water per Program, dosing one of "material-tabs" (see `dishwasherAndBeverage`). */
  dishwasher: devicesListDishwasher.devices[0] as Device,
  /** `coinop/devices/list` with only "device-dryer", a Tumble dryer on an energy meter,
   * dosing "material-sheets" (not in a recorded catalogue): 1 in the Default row, 2 for
   * "Cupboard dry". */
  tumbleDryer: devicesListTumbleDryer.devices[0] as Device,
  /** `coinop/devices/list` with only "device-dryer", a Tumble dryer set up manually from a
   * Miele washing machine's HA device, whose profile finds a water meter too; no Doses. */
  dryerFromWasher: devicesListTumbleDryerFromMiele.devices[0] as Device,
  /** `coinop/devices/list` with only "device-coffee-machine", a Coffee machine whose
   * electricity and water come per Program, dosing "material-beans" (see
   * `dishwasherAndBeverage`): the Default row 0.02 kWh and 0.125 L, "Espresso" 0.012 kWh
   * and 0.04 L. */
  coffeeMachine: devicesListCoffeeMachine.devices[0] as Device,
  /** `coinop/runs/get` of its "Espresso" Run "espresso": 0.012 kWh at 0.30
   * ("espresso-electricity") and 0.04 L at 4.00 per m³ ("espresso-water") from the
   * Program's row, both amounts rounding to 0.00. */
  espresso: runsGetCoffeeMachine.run as RunDetail,
  /** `coinop/devices/list` with only "device-oven", an Oven (a Program and no Doses) on an
   * energy meter: the Default row 1 kWh, "Fan plus 180°" 1.6 kWh. */
  oven: devicesListOven.devices[0] as Device,
  /** `coinop/devices/measured_suggestions` of "device-oven" after a "Fan plus 180°" Run:
   * 1.4 kWh from 1 Run for that Program, nothing for the Default row. */
  ovenSuggestions: devicesMeasuredSuggestionsOven.suggestions as Awaited<
    ReturnType<typeof getMeasuredSuggestions>
  >,
  /** `coinop/devices/list` with only "device-wallbox", an EV charger on its session energy
   * sensor; per-Run meters is its only Capability. */
  wallbox: devicesListEvCharger.devices[0] as Device,
  /** `coinop/devices/list` with only "device-mower", a robotic mower (no Capability at all)
   * on its charging station's energy meter, with charging mapped to Paused. */
  mower: devicesListRoboticMower.devices[0] as Device,
  /** `coinop/runs/get` of its Run "mowing": 65 minutes of mowing, then 55 minutes paused
   * while it charged 0.25 kWh at 0.30 ("mowing-electricity"); ended with Outcome Unknown. */
  mowing: runsGetRoboticMower.run as RunDetail,
  /** `coinop/devices/list` with three Other Devices under two Type Names: "device-kiln"
   * ("Kiln"), which has nothing and estimates its electricity from 2 kW, then
   * "device-pool-pump" and "device-pond-pump" (both "Pump") on a cycle energy sensor,
   * whose meters count each Run from 0. */
  others: devicesListOther.devices as Device[],
  /** `coinop/runs/get` of the kiln's unnamed Run "firing": 90 minutes estimated as 3 kWh
   * at 0.30 ("firing-electricity"); ended with Outcome Unknown. */
  firing: runsGetOther.run as RunDetail,
  /** `coinop/devices/list` with only "device-studio-kiln", an Other Device ("Kiln") that
   * has images and a Part Count and no job: its Thumbnail image entity and its camera. */
  studioKiln: devicesListOtherImages.devices[0] as Device,
  /** `coinop/runs/get` of its Run "mugs" of 9 parts: 3 kWh estimated at 0.30
   * ("mugs-electricity"), with "mugs-thumbnail" and "mugs-snapshot". */
  mugs: runsGetOtherImages.run as RunDetail,
  /** `coinop/devices/list` with only "device-bread-maker", an Other Device under the Type
   * Name "Bread maker" with a Program and no Doses, its electricity per Program: the
   * Default row 0.4 kWh, "Whole wheat" 0.5 kWh; its Program input also knows "Basic". */
  breadMaker: devicesListOtherProgram.devices[0] as Device,
  /** `coinop/runs/get` of its Run "wheat-loaf" (Whole wheat): 0.5 kWh from the Program's
   * row at 0.30 ("wheat-loaf-electricity"). */
  wheatLoaf: runsGetOtherProgram.run as RunDetail,
  /** `coinop/runs/list` of its Runs "plain-loaf" (no Program, 0.12) and "wheat-loaf"
   * (Whole wheat, 0.15), with `coinop/aggregates/get` of the two by Program. */
  loaves: aggregatesOtherProgram as typeof byProgram,
  /** `coinop/devices/list` with only "device-soda-maker", an Other Device under the Type
   * Name "Soda maker" with Doses and no Program, with the electricity source none: its
   * Default row doses 8 g of "co2" and 40 ml of "syrup". */
  sodaMaker: devicesListOtherDoses.devices[0] as Device,
  /** `coinop/devices/list` with only "device-brew-kettle", an Other Device under the Type
   * Name "Brew kettle" with a Program, Doses and water, its electricity and water per
   * Program: the Default row 3 kWh, 25 L, 4,000 g of "malt" and 30 g of "hops", "Pale ale"
   * 3.6 kWh, 30 L and 4,500 g of "malt". */
  brewKettle: devicesListOtherProgramDoses.devices[0] as Device,
  /** `coinop/runs/get` of the soda maker's unnamed Run "bottle": 8 g of CO₂ at 0.02
   * ("bottle-co2") and 40 ml of Cola syrup at 0.01 ("bottle-syrup"), both from the Default
   * row, and no Electricity Line Item; ended with Outcome Unknown. */
  bottle: runsGetOtherDoses.run as RunDetail,
  /** `coinop/catalog/subscribe` with the Materials the Doses of both point to, all of the
   * form Other: "co2" (CO₂, by g), "syrup" (Cola syrup, by ml), "malt" (Pale malt, by g) and
   * "hops" (Hop pellets, by g). */
  doseMaterials: catalogSubscribeOtherDoses as Catalog,
  /** `coinop/devices/list` with only "device-cnc-router", an Other Device under the Type
   * Name "CNC router" with Job and Material, Images and a Part Count: its job name and
   * Material used inputs (in g), no Slots and no image input, the default Material "mdf". */
  cncRouter: devicesListOtherJob.devices[0] as Device,
  /** `coinop/runs/get` of its Run "sign" ("Sign Oak", after its job) of 3 parts: 0.3 kWh
   * estimated at 0.30 ("sign-electricity") and 120 g of MDF measured at 0.005
   * ("sign-material"). */
  sign: runsGetOtherJob.run as RunDetail,
  /** `coinop/catalog/subscribe` with the Materials of the form Other it can charge: "mdf"
   * (MDF, by g) and "plywood" (Plywood sheet, by piece). */
  stock: catalogSubscribeOtherJob as Catalog,
  /** `coinop/runs/get` of its finished Run "wash": 1.2 kWh measured at 0.30. */
  wash: runsGetWashingMachine.run as RunDetail,
  /** `coinop/devices/measured_suggestions` of "device-washer" after "wash" (Cotton 60°,
   * no row of its own): 1.2 kWh from 1 Run for the Default row and for "Cotton 60°". */
  measuredSuggestions: devicesMeasuredSuggestions.suggestions as Awaited<
    ReturnType<typeof getMeasuredSuggestions>
  >,
  /** `coinop/devices/measured_suggestions` of a Device with a water meter after two Runs
   * without a Program that took 0.04 and 0.05 L: 0.045 L for the Default row. */
  smallSuggestions: devicesMeasuredSuggestionsSmall.suggestions as Awaited<
    ReturnType<typeof getMeasuredSuggestions>
  >,
  /** `coinop/runs/get` of "water-wash" on "device-washer" with a water meter: 50 L measured,
   * 20 L at 4.00 and 30 L at 5.00 per m³ ("water-wash-water"). */
  waterWash: runsGetWater.run as RunDetail,
  /** `coinop/devices/list` with only "device-washer", a washing machine whose electricity
   * and water come per Program: the Default row 0.9 kWh and 50 L, "Wool" 0.4 kWh and 45 L. */
  perProgram: devicesListPerProgram.devices[0] as Device,
  /** `coinop/runs/get` of its "Wool" Run "wool": 0.4 kWh at 0.30 ("wool-electricity") and
   * 45 L at 4.00 per m³ ("wool-water") from the Program's row. */
  perProgramWash: runsGetPerProgram.run as RunDetail,
  /** `coinop/line_items/add`: 60 L at 4.50 per m³ ("basement-wash-water") added by hand to
   * "basement-wash" of "device-basement", a washing machine without water source. */
  lineItemsAddWater: lineItemsAddWater as { run: RunDetail },
  /** `coinop/devices/list` with only "device-washer", a washing machine with electricity
   * source none and water per Program; its Program Defaults still hold the kWh of
   * `perProgram`. */
  unpowered: devicesListElectricityNone.devices[0] as Device,
  /** `coinop/runs/get` of its "Wool" Run "unpowered": 45 L at 4.00 per m³
   * ("unpowered-water") and no Electricity Line Item. */
  unpoweredWash: runsGetElectricityNone.run as RunDetail,
  /** `coinop/line_items/add`: 0.4 kWh at 0.30 ("unpowered-electricity") added to it by
   * hand. */
  lineItemsAddElectricity: lineItemsAddElectricity as { run: RunDetail },
  /** `coinop/devices/list` with only "device-garden-valve", an Other Device under the Type
   * Name "Irrigation" that has water: on a water meter at 4.00 per m³, with the electricity
   * source none. */
  irrigation: devicesListOtherWater.devices[0] as Device,
  /** `coinop/runs/get` of its unnamed Run "watering": 120 L measured at 4.00 per m³
   * ("watering-water") and no Electricity Line Item; ended with Outcome Unknown. */
  watering: runsGetOtherWater.run as RunDetail,
  /**
   * `coinop/catalog/subscribe`: first empty, then the whole catalogue a panel opened
   * later gets: "material-1" (eSun PLA+ black, default for PLA), "material-2" (Standard
   * Resin grey), "material-3" (PLA red, archived), the Tags "Cosplay helmet", "Gift"
   * and "Spare parts" and the templates "template-wear" (running hours),
   * "template-inserts" and "template-packaging".
   */
  catalog: {
    empty: catalogSubscribe[0] as Catalog,
    filled: catalogSubscribe[1] as Catalog,
  },
  /** `coinop/tags/rename` of "Spare" to "Spare parts". */
  tagRename: tagsRename,
  /** Spoolman with the Filaments 7 eSun PLA+ black (20.00 / 1,000 g), 8 Prusament PETG
   * Galaxy Black (29.99 / 1,000 g from its spool), 9 eSun TPU clear (no price) and 10
   * Prusament PLA Galaxy Black, next to the own Materials "pla-black" (eSun, #1a1a1a,
   * default for PLA) and "pla-any" (PLA). */
  spoolman: {
    /** `coinop/spoolman/read`: 7 waits for "pla-black" and "pla-any", 10 for "pla-any". */
    read: spoolmanRead as SpoolmanState,
    notConfigured: spoolmanReadUnavailable[0] as SpoolmanState,
    unreachable: spoolmanReadUnavailable[1] as SpoolmanState,
    /** `coinop/spoolman/merge` of "pla-black" into 7, keeping "pla-any" own. */
    merged: spoolmanMerge as SpoolmanState,
    /** `coinop/materials/list` after that read: the own two, "material-filament-8" and
     * "material-filament-9"; then after the merge, also "material-filament-10". */
    materials: spoolmanMaterials[0].materials as Material[],
    mergedMaterials: spoolmanMaterials[1].materials as Material[],
  },
  /** `coinop/materials/types`: the built-in types for pre-filling. */
  materialTypes: materialsTypes as { types: MaterialType[] },
  /** `coinop/materials/create` of "material-detergent" (1,500 ml for 7.80) and
   * "material-pods" (40 pieces for 12.00), each answer's Material. */
  laundry: materialsCreateLaundry as Material[],
  /** `coinop/materials/create` of "material-tabs" (60 pieces for 9.00) and
   * "material-beans" (1,000 g for 16.00), each answer's Material. */
  dishwasherAndBeverage: materialsCreateDishwasherAndBeverage as Material[],
  /** `coinop/materials/create` of "material-fertiliser" (form Other, 500 ml for 6.00):
   * the answer's Material. */
  otherMaterial: materialsCreateOther as Material,
  material: (id: string) =>
    found(
      recorded.catalog.filled.materials.find((material) => material.id === id),
      id,
    ),
  summary: (id: string) =>
    found(
      recorded.snapshot.runs.find((run) => run.id === id),
      id,
    ),
  run: (id: string) =>
    found(
      recorded.runs.find((run) => run.id === id),
      id,
    ),
};

type Reply = (msg: Message) => unknown;
type Listener = (event: unknown) => void;

export class WsError extends Error {
  constructor(
    readonly code: string,
    message = code,
  ) {
    super(message);
  }
}

export class FakeBackend {
  /** Every message the panel sent (`callWS` and subscriptions), in order. */
  readonly calls: Message[] = [];
  /** Every path the panel fetched with `fetchWithAuth`, in order; uploads aside. */
  readonly fetches: string[] = [];
  /** Every multipart upload the panel posted, with its `file` parts. */
  readonly uploads: { path: string; files: File[] }[] = [];
  hass: HomeAssistant;
  private readonly files = new Map<string, Blob>();
  private readonly replies = new Map<string, Reply>();
  private readonly posts = new Map<string, (files: File[]) => [number, unknown]>();
  private readonly initialEvents = new Map<string, Reply>();
  private readonly listeners = new Map<string, Set<Listener>>();

  constructor({ language = "en", currency = "EUR", timeZone = "UTC" } = {}) {
    this.hass = {
      language,
      config: { currency, time_zone: timeZone, components: ["coinop"] },
      states: {},
      callWS: async <T>(msg: Message) => {
        this.calls.push(msg);
        const reply = this.replies.get(msg.type);
        if (!reply) throw new WsError("unknown_command");
        return (await reply(msg)) as T;
      },
      fetchWithAuth: async (path: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          const files = (init.body as FormData).getAll("file") as File[];
          this.uploads.push({ path, files });
          const [status, body] = this.posts.get(path)?.(files) ?? [404, { code: "not_found" }];
          return new Response(JSON.stringify(body), {
            status,
            headers: { "content-type": "application/json" },
          });
        }
        this.fetches.push(path);
        const file = this.files.get(path);
        return file ? new Response(file) : new Response(null, { status: 404 });
      },
      connection: {
        subscribeMessage: async <T>(callback: (event: T) => void, msg: Message) => {
          this.calls.push(msg);
          const initial = this.initialEvents.get(msg.type);
          if (!initial) throw new WsError("unknown_command");
          // Throwing here rejects the subscription, as a failed command does in HA.
          const events = (await initial(msg)) as unknown[];
          const listener = callback as Listener;
          const listeners = this.listeners.get(msg.type) ?? new Set();
          this.listeners.set(msg.type, listeners.add(listener));
          queueMicrotask(() => events.forEach(listener));
          return async () => void listeners.delete(listener);
        },
      },
    };
  }

  /** The messages of `type` the panel sent, in order. */
  sent(type: string) {
    return this.calls.filter((call) => call.type === type);
  }

  /** Answer `callWS({type, ...})`; throw `new WsError(code)` to fail it. */
  reply(type: string, reply: Reply) {
    this.replies.set(type, reply);
    return this;
  }

  /** Accept subscriptions to `type`, sending these events right after subscribing. */
  subscription(type: string, initialEvents: Reply) {
    this.initialEvents.set(type, initialEvents);
    return this;
  }

  /** Serve `content` at `path` to `fetchWithAuth`; anything else is 404. */
  file(path: string, content: Blob = new Blob([path], { type: "image/webp" })) {
    this.files.set(path, content);
    return this;
  }

  /** Answer a POST to `path` with `[status, json]`. */
  post(path: string, reply: (files: File[]) => [number, unknown]) {
    this.posts.set(path, reply);
    return this;
  }

  /** Send an event to every open subscription to `type`. */
  push(type: string, event: unknown) {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  openSubscriptions(type: string) {
    return this.listeners.get(type)?.size ?? 0;
  }

  /** What HA does on every change: hand the panel a new `hass` object. */
  update(changes: Partial<HomeAssistant>) {
    this.hass = { ...this.hass, ...changes };
    return this.hass;
  }
}

/** Every image the recorded Runs refer to. */
const recordedImages = [...recorded.runs, recorded.setCover].flatMap((run) =>
  run.images.flatMap((image) => [image.url, image.tile_url]),
);

/** A backend answering with the recorded responses; tests override what they need. */
export function recordedBackend(options?: ConstructorParameters<typeof FakeBackend>[0]) {
  const backend = new FakeBackend(options);
  for (const path of recordedImages) backend.file(path);
  return backend
    .subscription("coinop/runs/subscribe", () => [recorded.snapshot])
    .subscription("coinop/catalog/subscribe", () => [recorded.catalog.filled])
    .reply("coinop/materials/types", () => recorded.materialTypes)
    .reply("coinop/runs/get", (msg) => {
      // "unpowered" is the one recorded Run that still takes its electricity by hand.
      const run = [...recorded.runs, recorded.unpoweredWash].find(
        (candidate) => candidate.id === msg.run_id,
      );
      if (!run) throw new WsError("not_found");
      return { run };
    })
    .reply("coinop/devices/list", () => ({ devices: recorded.devices }))
    .reply("coinop/cost_statement/defaults", () => recorded.statementDefaults)
    .reply("coinop/aggregates/get", (msg) => {
      const runIds = (msg.run_ids as string[] | undefined)?.toSorted();
      const asked = `${String(msg.group_by)} of ${String(runIds)}`;
      return {
        groups: found(
          [
            ...recorded.aggregates,
            ...recorded.programs.aggregates,
            ...recorded.loaves.aggregates,
          ].find((answer) => `${String(answer.group_by)} of ${String(answer.run_ids)}` === asked),
          `grouping ${asked}`,
        ).groups,
      };
    });
}
