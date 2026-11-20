import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Group } from "../src/api";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const AGGREGATES = "coinop/aggregates/get";
const SUBSCRIBE = "coinop/runs/subscribe";
const [started, updated] = recorded.changes;

const names = (panel: Element) => queryAll(panel, ".tile .strong").map(text);
const stats = (panel: Element) => queryAll(panel, ".stat").map(text);

/** The recorded groups of `group_by`, as the backend would answer with other Runs. */
const groups = (key: string) =>
  recorded.aggregates.find(({ group_by }) => group_by.join() === key)?.groups ?? [];
const zero = { ...groups("")[0], cost: 0, runs: 0 };
const month = (key: string, kind: Group["kind"], cost: number): Group => ({
  ...zero,
  month: key,
  kind,
  cost,
});

describe("Overview", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-01-20T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("shows this month, all time, failed + cancelled and flagged Runs", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(stats(panel)).toEqual([
      "January 2026 €1.23 3 Runs",
      "All time, all Devices €1.23 3 Runs",
      "Failed + cancelled €0.37 2 Runs · 30% of cost",
      "Flagged Runs ⚑ 1 Click to filter",
    ]);
  });

  it("counts nothing this month when no Run started in it", async () => {
    vi.setSystemTime(new Date("2026-03-02T12:00:00Z"));

    const panel = await mountPanel(recordedBackend());

    expect(stats(panel)[0]).toBe("March 2026 €0.00 0 Runs");
  });

  it("opens the Runs tab filtered by Outcome or Flags from the tiles", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, ".stat.failed"));
    expect(location.pathname + location.search).toBe("/coinop/runs?outcome=failed_cancelled");
    expect(names(panel)).toEqual(["Untitled Run", "Helmet"]);
    expect((query(panel, ".outcome-filter") as HTMLSelectElement).value).toBe("failed_cancelled");

    await click(panel, query(panel, `a.tab[href="/coinop"]`));
    await click(panel, query(panel, ".stat.flagged"));
    expect(location.pathname + location.search).toBe("/coinop/runs?flagged=1");
    expect(names(panel)).toEqual(["Helmet"]);
  });

  it("shows the most recent Runs without filters or selection, and leads to all of them", async () => {
    const runs = Array.from({ length: 22 }, (_, day) => ({
      ...recorded.snapshot.runs[0],
      id: `run-${day}`,
      name: `Run ${day + 1}`,
      started: `2026-01-${String(day + 1).padStart(2, "0")}T10:00:00Z`,
    }));
    const backend = recordedBackend().subscription(SUBSCRIBE, () => [{ runs }]);
    const panel = await mountPanel(backend);

    expect(text(query(panel, ".recent .head"))).toBe("Recent Runs All Runs");
    expect(names(panel)).toHaveLength(20);
    expect(names(panel).slice(0, 2)).toEqual(["Run 22", "Run 21"]);
    expect(queryAll(panel, ".name-filter, input.pick, .basket, .manual-run")).toEqual([]);

    await click(panel, query(panel, "a.all-runs"));
    expect(location.pathname + location.search).toBe("/coinop/runs");
    expect(names(panel)).toHaveLength(22);
  });

  it("charts the cost per month stacked by kind and opens the Runs of the month clicked", async () => {
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      if (key === "month")
        return { groups: [{ ...zero, month: "2025-12", cost: 2 }, ...groups("month")] };
      if (key === "month,kind")
        return {
          groups: [
            month("2025-12", "electricity", 0.5),
            month("2025-12", "material", 1.5),
            ...groups("month,kind"),
          ],
        };
      return { groups: groups(key) };
    });
    const panel = await mountPanel(backend);

    const columns = queryAll(panel, ".per-month .column");
    expect(columns.map(text)).toEqual(["€2.00 Dec", "€1.23 Jan"]);
    expect(columns[1].title).toBe(
      "January 2026\nElectricity: €0.42\nMaterial: €0.31\nOther: €0.50",
    );
    expect(columns.map((column) => queryAll(column, "rect, path").length)).toEqual([2, 3]);
    expect(text(query(panel, ".per-month .legend"))).toBe("Electricity Material Other");

    await click(panel, columns[0]);
    expect(location.pathname + location.search).toBe("/coinop/runs?month=2025-12");
    expect(text(panel)).toContain("No Runs match the filters.");
    expect((query(panel, ".month-filter") as HTMLSelectElement).value).toBe("2025-12");
  });

  it("labels only the highest month once the values would overlap", async () => {
    const months = ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"];
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      if (key === "month")
        return {
          groups: [
            ...months.map((key, index) => ({ ...zero, month: key, cost: index + 1 })),
            ...groups("month"),
          ],
        };
      if (key === "month,kind")
        return {
          groups: [
            ...months.map((key, index) => month(key, "material", index + 1)),
            ...groups("month,kind"),
          ],
        };
      return { groups: groups(key) };
    });
    const panel = await mountPanel(backend);

    expect(queryAll(panel, ".per-month .column").map(text)).toEqual([
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "€6.00 Dec",
      "Jan",
    ]);
  });

  it("charts the cost by Material", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(queryAll(panel, ".by-material .bar-row").map(text)).toEqual(["PLA Basic Black €0.31"]);
  });

  it("charts the cheapest Materials together as the backend totals them", async () => {
    const material = (id: string | null, cost: number): Group => ({
      ...zero,
      kind: "material",
      material_id: id,
      material_name: id,
      cost,
    });
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      if (key === "kind,material")
        return { groups: ["a", "b", "c", "d", "e", "f", null].map((id, i) => material(id, 7 - i)) };
      if (msg.material_ids) return { groups: [{ ...zero, kind: "material", cost: 1.5 }] };
      return { groups: groups(key) };
    });
    const panel = await mountPanel(backend);

    expect(queryAll(panel, ".by-material .bar-row").map(text)).toEqual([
      "a €7.00",
      "b €6.00",
      "c €5.00",
      "d €4.00",
      "e €3.00",
      "Other Materials €1.50",
    ]);
    expect(backend.sent(AGGREGATES).find((call) => call.material_ids)).toEqual({
      type: AGGREGATES,
      group_by: ["kind"],
      material_ids: ["f", null],
    });
  });

  it("shows the Run running now at its live cost and reads the totals afresh", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);
    expect(queryAll(panel, ".running")).toHaveLength(0);
    const loaded = backend.sent(AGGREGATES).length;

    backend.push(SUBSCRIBE, started);
    backend.push(SUBSCRIBE, updated);
    await settle(panel);

    expect(text(query(panel, ".running"))).toBe(
      "Running now Untitled Run Kobra · 45 min €0.25 Provisional, updates live",
    );
    expect(query(panel, ".running a").getAttribute("href")).toBe("/coinop/run/print-live");
    expect(backend.sent(AGGREGATES).length).toBeGreaterThan(loaded);
  });

  it("says when the totals can't be loaded and still shows the Runs", async () => {
    const backend = recordedBackend().reply(AGGREGATES, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend);

    expect(text(panel)).toContain("Coin-op could not load its totals.");
    expect(names(panel)).toHaveLength(3);
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }));

    expect(stats(panel)).toEqual([
      "Januar 2026 1,23 € 3 Läufe",
      "Gesamt, alle Geräte 1,23 € 3 Läufe",
      "Fehlgeschlagen + abgebrochen 0,37 € 2 Läufe · 30 % der Kosten",
      "Läufe mit Hinweisen ⚑ 1 Zum Filtern klicken",
    ]);
  });
});
