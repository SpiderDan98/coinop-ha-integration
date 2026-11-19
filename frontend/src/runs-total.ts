import type { ReactiveController, ReactiveControllerHost } from "lit";
import { getAggregates, type RunSummary } from "./api";
import type { HomeAssistant } from "./hass";

/** What the backend totals for some Runs, read again whenever they or their costs change;
 * undefined until read or if reading failed. */
export class RunsTotal implements ReactiveController {
  cost?: number;
  private key?: string;
  private request = 0;

  constructor(private readonly host: ReactiveControllerHost) {
    host.addController(this);
  }

  hostConnected() {}

  load(hass: HomeAssistant, runs: RunSummary[]) {
    const key = runs.map((run) => `${run.id}:${run.total}`).join();
    if (key === this.key) return;
    this.key = key;
    const request = ++this.request;
    const total = runs.length
      ? getAggregates(hass, [], { run_ids: runs.map((run) => run.id) }).then(
          ([group]) => group?.cost ?? 0,
          () => undefined,
        )
      : Promise.resolve(0);
    void total.then((cost) => {
      if (request !== this.request) return;
      this.cost = cost;
      this.host.requestUpdate();
    });
  }
}
