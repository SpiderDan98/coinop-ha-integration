// The Runs tab's filter and sort, kept in the URL's query so they survive a reload and the
// back button.
import { OUTCOMES, type Device, type RunSummary } from "./api";
import type { Format } from "./format";
import type { Localize } from "./localize";
import { deviceName, runName } from "./run-parts";

export const OUTCOME_FILTERS = ["open", ...OUTCOMES, "failed_cancelled"] as const;

/** Tags match any of `tags`, or no Tag at all with `untagged`; `noProgram` matches the Runs
 * without a Program of the Devices that record one. */
export const NO_FILTER = {
  name: "",
  deviceId: "",
  month: "",
  outcome: "" as "" | (typeof OUTCOME_FILTERS)[number],
  flagged: false,
  tags: [] as string[],
  untagged: false,
  program: "",
  noProgram: false,
};

export type Filter = typeof NO_FILTER;

/** Only final Runs go into a Cost Statement or can be deleted. */
export const selectable = (run: RunSummary) => run.finalised;

/** A Run of a Device that records Programs, or one that has a Program. */
export const programmed = (run: RunSummary, devices?: Device[]) =>
  run.program !== null ||
  !!devices?.some(
    (device) => device.id === run.device_id && device.capabilities.includes("program"),
  );

export function matches(
  run: RunSummary,
  filter: Filter,
  t: Localize,
  format: Format,
  devices?: Device[],
) {
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
      run.tags.some((tag) => filter.tags.includes(tag))) &&
    (!filter.program || run.program === filter.program) &&
    (!filter.noProgram || (run.program === null && programmed(run, devices)))
  );
}

export const SORTS = ["name", "device", "start", "duration", "total", "per_part"] as const;

export const DEFAULT_SORT = { by: "start" as (typeof SORTS)[number], descending: true };

export type Sort = typeof DEFAULT_SORT;

/** `runs` in the order of `sort`; ties newest first. */
export function sorted(runs: RunSummary[], sort: Sort, t: Localize, devices?: Device[]) {
  const text = (value: (run: RunSummary) => string) => (a: RunSummary, b: RunSummary) =>
    value(a).localeCompare(value(b));
  const number = (value: (run: RunSummary) => number) => (a: RunSummary, b: RunSummary) =>
    value(a) - value(b);
  const compare = {
    name: text((run) => runName(run, t)),
    device: text((run) => deviceName(run, devices, t)),
    start: text((run) => run.started),
    duration: number((run) => run.running_seconds),
    total: number((run) => run.total),
    per_part: number((run) => run.cost_per_part ?? run.total),
  }[sort.by];
  const newest = text((run) => run.started);
  return runs.toSorted((a, b) => (sort.descending ? compare(b, a) : compare(a, b)) || newest(b, a));
}

export function sortOf(search: string): Sort {
  const params = new URLSearchParams(search);
  const by = SORTS.find((known) => known === params.get("sort"));
  return by ? { by, descending: params.get("order") === "desc" } : DEFAULT_SORT;
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
    program: params.get("program") ?? "",
    noProgram: params.has("no_program"),
  };
}

/** The URL query of a filter and sort, "" for none and the default. */
export function searchOf(filter: Partial<Filter>, sort = DEFAULT_SORT) {
  const params = new URLSearchParams();
  if (filter.name) params.set("q", filter.name);
  if (filter.deviceId) params.set("device", filter.deviceId);
  if (filter.month) params.set("month", filter.month);
  if (filter.outcome) params.set("outcome", filter.outcome);
  if (filter.flagged) params.set("flagged", "1");
  for (const tag of filter.tags ?? []) params.append("tag", tag);
  if (filter.untagged) params.set("untagged", "1");
  if (filter.program) params.set("program", filter.program);
  if (filter.noProgram) params.set("no_program", "1");
  if (sort.by !== DEFAULT_SORT.by || sort.descending !== DEFAULT_SORT.descending) {
    params.set("sort", sort.by);
    params.set("order", sort.descending ? "desc" : "asc");
  }
  const search = params.toString();
  return search && `?${search}`;
}

/** The Runs tab showing the Runs `filter` matches. */
export const runsPath = (basePath: string, filter: Partial<Filter> = {}, sort = DEFAULT_SORT) =>
  `${basePath}/runs${searchOf(filter, sort)}`;
