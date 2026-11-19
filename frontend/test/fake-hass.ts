// Seam 2: a fake `hass` whose websocket calls are answered by canned responses.
// The recorded ones come from the backend tests (tests/contract.py), so they have
// exactly the shapes the backend sends.
import type { HomeAssistant, Message } from "../src/hass";
import type { Device, RunChange, RunDetail, RunSummary } from "../src/api";
import devicesList from "./fixtures/backend/devices-list.json";
import runsGet from "./fixtures/backend/runs-get.json";
import runsSubscribe from "./fixtures/backend/runs-subscribe.json";

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
  /** `wattbill/runs/get` for every recorded Run; "print-live" while still open. */
  runs: runsGet.map((result) => result.run as RunDetail),
  /** `wattbill/devices/list`: only "device-kobra"; "device-mini" (Runs only) was removed. */
  devices: devicesList.devices as Device[],
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
  hass: HomeAssistant;
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

/** A backend answering with the recorded responses; tests override what they need. */
export function recordedBackend(options?: ConstructorParameters<typeof FakeBackend>[0]) {
  return new FakeBackend(options)
    .subscription("wattbill/runs/subscribe", () => [recorded.snapshot])
    .reply("wattbill/runs/get", (msg) => {
      const run = recorded.runs.find((candidate) => candidate.id === msg.run_id);
      if (!run) throw new WsError("not_found");
      return { run };
    })
    .reply("wattbill/devices/list", () => ({ devices: recorded.devices }));
}
