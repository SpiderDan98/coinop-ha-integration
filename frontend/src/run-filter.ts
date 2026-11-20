// The Runs tab's filter, kept in the URL's query so it survives a reload and the back button.
import { OUTCOMES, type RunSummary } from "./api";
import type { Format } from "./format";
import type { Localize } from "./localize";
import { runName } from "./run-parts";

export const OUTCOME_FILTERS = ["open", ...OUTCOMES, "failed_cancelled"] as const;

/** Tags match any of `tags`, or no Tag at all with `untagged`. */
export const NO_FILTER = {
  name: "",
  deviceId: "",
  month: "",
  outcome: "" as "" | (typeof OUTCOME_FILTERS)[number],
  flagged: false,
  tags: [] as string[],
  untagged: false,
};

export type Filter = typeof NO_FILTER;

/** Only final Runs go into a Cost Statement or can be deleted. */
export const selectable = (run: RunSummary) => run.finalised;

export function matches(run: RunSummary, filter: Filter, t: Localize, format: Format) {
  const outcome = run.ended === null ? "open" : (run.outcome ?? "unknown");
  const name = filter.name.trim().toLocaleLowerCase();
  return (
    (!name || runName(run, t).toLocaleLowerCase().includes(name)) &&
    (!filter.deviceId || run.device_id === filter.deviceId) &&
    (!filter.month || format.month(run.started) === filter.month) &&
    (!filter.outcome ||
      (filter.outcome === "failed_cancelled"
        ? outcome === "failed" || outcome === "cancelled"
        : outcome === filter.outcome)) &&
    (!filter.flagged || run.flags.length > 0) &&
    ((!filter.tags.length && !filter.untagged) ||
      (filter.untagged && !run.tags.length) ||
      run.tags.some((tag) => filter.tags.includes(tag)))
  );
}

export function filterOf(search: string): Filter {
  const params = new URLSearchParams(search);
  const outcome = params.get("outcome");
  return {
    name: params.get("q") ?? "",
    deviceId: params.get("device") ?? "",
    month: params.get("month") ?? "",
    outcome: OUTCOME_FILTERS.find((known) => known === outcome) ?? "",
    flagged: params.has("flagged"),
    tags: params.getAll("tag"),
    untagged: params.has("untagged"),
  };
}

/** The URL query of a filter, "" for none. */
export function searchOf(filter: Partial<Filter>) {
  const params = new URLSearchParams();
  if (filter.name) params.set("q", filter.name);
  if (filter.deviceId) params.set("device", filter.deviceId);
  if (filter.month) params.set("month", filter.month);
  if (filter.outcome) params.set("outcome", filter.outcome);
  if (filter.flagged) params.set("flagged", "1");
  for (const tag of filter.tags ?? []) params.append("tag", tag);
  if (filter.untagged) params.set("untagged", "1");
  const search = params.toString();
  return search && `?${search}`;
}

/** The Runs tab showing the Runs `filter` matches. */
export const runsPath = (basePath: string, filter: Partial<Filter> = {}) =>
  `${basePath}/runs${searchOf(filter)}`;
