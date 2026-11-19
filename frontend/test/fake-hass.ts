// Seam 2: a fake `hass` whose websocket calls and authenticated fetches are
// answered by canned responses.
// The recorded ones come from the backend tests (tests/contract.py), so they have
// exactly the shapes the backend sends.
import type { HomeAssistant, Message } from "../src/hass";
import type {
  Catalog,
  Device,
  Drop,
  MaterialType,
  RunChange,
  RunDetail,
  RunSummary,
} from "../src/api";
import catalogSubscribe from "./fixtures/backend/catalog-subscribe.json";
import devicesList from "./fixtures/backend/devices-list.json";
import lineItemsAdd from "./fixtures/backend/line-items-add.json";
import lineItemsAddMaterial from "./fixtures/backend/line-items-add-material.json";
import lineItemsMaterial from "./fixtures/backend/line-items-material.json";
import lineItemsUpdate from "./fixtures/backend/line-items-update.json";
import materialsTypes from "./fixtures/backend/materials-types.json";
import runsDeletePreview from "./fixtures/backend/runs-delete-preview.json";
import runsGet from "./fixtures/backend/runs-get.json";
import runsSubscribe from "./fixtures/backend/runs-subscribe.json";
import tagsRename from "./fixtures/backend/tags-rename.json";

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
   * measured Material ("print-live-material") locked. "benchy" has a Thumbnail and a
   * Snapshot and its measured PLA Basic Black ("benchy-pla"); "helmet" only a Snapshot and
   * a measured length without Material ("helmet-filament"). */
  runs: runsGet.map((result) => result.run as RunDetail),
  /** `wattbill/runs/delete_preview` for "helmet". */
  deletePreview: runsDeletePreview as { drop: Drop },
  /** `wattbill/line_items/update`: Benchy's electricity overridden to an amount of 0.10. */
  lineItemsUpdate: lineItemsUpdate as { run: RunDetail },
  /** `wattbill/line_items/add`: a refund of -2.00 ("helmet-refund") added to Helmet. */
  lineItemsAdd: lineItemsAdd as { run: RunDetail },
  /** `wattbill/line_items/update`: PETG White picked for Helmet's measured 30 m
   * ("helmet-filament"), which had no Material. */
  lineItemsMaterial: lineItemsMaterial as { run: RunDetail },
  /** `wattbill/line_items/add`: 3 g of PETG White ("benchy-petg") added to Benchy. */
  lineItemsAddMaterial: lineItemsAddMaterial as { run: RunDetail },
  /** `wattbill/devices/list`: only "device-kobra" (Material used input in mm, default
   * Material "pla-black"); "device-mini" (Runs only) was removed. */
  devices: devicesList.devices as Device[],
  /**
   * `wattbill/catalog/subscribe`: first empty, then the whole catalogue a panel opened
   * later gets: "material-1" (eSun PLA+ black, default for PLA), "material-2" (Standard
   * Resin grey), "material-3" (PLA red, archived) and the Tags "Cosplay helmet", "Gift"
   * and "Spare parts".
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
  /** Every path the panel fetched with `fetchWithAuth`, in order. */
  readonly fetches: string[] = [];
  hass: HomeAssistant;
  private readonly files = new Map<string, Blob>();
  private readonly replies = new Map<string, Reply>();
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
      fetchWithAuth: async (path: string) => {
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
const recordedImages = recorded.runs.flatMap((run) =>
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
