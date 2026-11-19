// Seam 2: a fake `hass` whose websocket calls and authenticated fetches are
// answered by canned responses.
// The recorded ones come from the backend tests (tests/contract.py), so they have
// exactly the shapes the backend sends.
import type { HomeAssistant, Message } from "../src/hass";
import type {
  Catalog,
  Device,
  Drop,
  LineItemTemplate,
  MaterialType,
  RunChange,
  RunDetail,
  RunImage,
  RunSummary,
} from "../src/api";
import catalogSubscribe from "./fixtures/backend/catalog-subscribe.json";
import devicesList from "./fixtures/backend/devices-list.json";
import imagesDelete from "./fixtures/backend/images-delete.json";
import imagesSetCover from "./fixtures/backend/images-set-cover.json";
import imagesUploadTooMany from "./fixtures/backend/images-upload-too-many.json";
import imagesUpload from "./fixtures/backend/images-upload.json";
import lineItemsAdd from "./fixtures/backend/line-items-add.json";
import lineItemsAddMaterial from "./fixtures/backend/line-items-add-material.json";
import lineItemsMaterial from "./fixtures/backend/line-items-material.json";
import lineItemsAddTemplate from "./fixtures/backend/line-items-add-template.json";
import lineItemsSplit from "./fixtures/backend/line-items-split.json";
import lineItemsSaveAsTemplate from "./fixtures/backend/line-items-save-as-template.json";
import lineItemsUpdate from "./fixtures/backend/line-items-update.json";
import materialsTypes from "./fixtures/backend/materials-types.json";
import runsDeletePreview from "./fixtures/backend/runs-delete-preview.json";
import runsGet from "./fixtures/backend/runs-get.json";
import runsSubscribe from "./fixtures/backend/runs-subscribe.json";
import tagsRename from "./fixtures/backend/tags-rename.json";
import templatesUpdate from "./fixtures/backend/templates-update.json";

const [snapshot, ...changes] = runsSubscribe;
const found = <T>(value: T | undefined, what: string) => {
  if (value === undefined) throw new Error(`nothing recorded for ${what}`);
  return value;
};

export const recorded = {
  /** First event of `wattbill/runs/subscribe`: the Runs "benchy", "helmet", "cancelled". */
  snapshot: { runs: (snapshot as { runs: RunSummary[] }).runs },
  /** Then the Run "print-live" is started, updated (45 min in) and ended. */
  changes: changes as { change: RunChange; run: RunSummary }[],
  /** `wattbill/runs/get` for every recorded Run; "print-live" while still open, with its
   * measured Material ("print-live-material") locked and its automatic template
   * "print-live-wear" counting running hours. "benchy" has a Thumbnail and a Snapshot and
   * its measured PLA Basic Black ("benchy-pla"); "helmet" only a Snapshot and a measured
   * length without Material ("helmet-filament"). */
  runs: runsGet.map((result) => result.run as RunDetail),
  /** `wattbill/runs/delete_preview` for "helmet". */
  deletePreview: runsDeletePreview as { drop: Drop },
  /** The upload of one photo to "benchy", and of ten more, refused. */
  upload: imagesUpload as { images: RunImage[] },
  uploadTooMany: imagesUploadTooMany,
  /** `wattbill/images/set_cover`: "benchy" with that upload picked as Cover Image. */
  setCover: imagesSetCover.run as RunDetail,
  /** `wattbill/images/delete` of that upload: "benchy" without it again. */
  deleteImage: imagesDelete.run as RunDetail,
  /** `wattbill/line_items/update`: Benchy's electricity overridden to an amount of 0.10. */
  lineItemsUpdate: lineItemsUpdate as { run: RunDetail },
  /** `wattbill/line_items/add`: a refund of -2.00 ("helmet-refund") added to Helmet. */
  lineItemsAdd: lineItemsAdd as { run: RunDetail },
  /** `wattbill/line_items/update`: PETG White picked for Helmet's measured 30 m
   * ("helmet-filament"), which had no Material. */
  lineItemsMaterial: lineItemsMaterial as { run: RunDetail },
  /** `wattbill/line_items/add`: 3 g of PETG White ("benchy-petg") added to Benchy. */
  lineItemsAddMaterial: lineItemsAddMaterial as { run: RunDetail },
  /** `wattbill/line_items/update` of a Run ("keychain") split across two Slots: 75% to
   * PLA Basic Black ("keychain-pla"), 25% to PETG White ("keychain-petg"), whose quantity
   * was corrected to 4 g. */
  splitRun: lineItemsSplit.run as RunDetail,
  /** `wattbill/line_items/save_as_template`: Benchy's "Nozzle wear" as "template-nozzle". */
  saveAsTemplate: lineItemsSaveAsTemplate as { template: LineItemTemplate },
  /** `wattbill/line_items/add_template`: 2 × "template-nozzle" added to Benchy ("benchy-nozzle"). */
  lineItemsAddTemplate: lineItemsAddTemplate as { run: RunDetail },
  /** `wattbill/templates/update`: "template-packaging" repriced to 0.60. */
  templateUpdate: templatesUpdate as { template: LineItemTemplate },
  /** `wattbill/devices/list`: only "device-kobra" (automatic template "template-wear",
   * Material used input in mm, default Material "pla-black"); "device-mini" (Runs only)
   * was removed. */
  devices: devicesList.devices as Device[],
  /**
   * `wattbill/catalog/subscribe`: first empty, then the whole catalogue a panel opened
   * later gets: "material-1" (eSun PLA+ black, default for PLA), "material-2" (Standard
   * Resin grey), "material-3" (PLA red, archived), the Tags "Cosplay helmet", "Gift"
   * and "Spare parts" and the templates "template-wear" (running hours),
   * "template-inserts" and "template-packaging".
   */
  catalog: {
    empty: catalogSubscribe[0] as Catalog,
    filled: catalogSubscribe[1] as Catalog,
  },
  /** `wattbill/tags/rename` of "Spare" to "Spare parts". */
  tagRename: tagsRename,
  /** `wattbill/materials/types`: the built-in types for pre-filling. */
  materialTypes: materialsTypes as { types: MaterialType[] },
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
  constructor(readonly code: string) {
    super(code);
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
      config: { currency, time_zone: timeZone },
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
    .subscription("wattbill/runs/subscribe", () => [recorded.snapshot])
    .subscription("wattbill/catalog/subscribe", () => [recorded.catalog.filled])
    .reply("wattbill/materials/types", () => recorded.materialTypes)
    .reply("wattbill/runs/get", (msg) => {
      const run = recorded.runs.find((candidate) => candidate.id === msg.run_id);
      if (!run) throw new WsError("not_found");
      return { run };
    })
    .reply("wattbill/devices/list", () => ({ devices: recorded.devices }));
}
