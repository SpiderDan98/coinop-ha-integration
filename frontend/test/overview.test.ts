import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Group } from "../src/api";
import type { Message } from "../src/hass";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const AGGREGATES = "wattbill/aggregates/get";
const SUBSCRIBE = "wattbill/runs/subscribe";
const [started, updated] = recorded.changes;

const sent = (backend: { calls: Message[] }, type: string) =>
  backend.calls.filter((call) => call.type === type);
const names = (panel: Element) => queryAll(panel, ".tile .strong").map(text);
const stats = (panel: Element) => queryAll(panel, ".stat").map(text);
const pick = (panel: Element, name: string) =>
  query(
    queryAll(panel, ".pick-tile").find((tile) => text(query(tile, ".strong")) === name) ?? panel,
    "input.pick",
  );
const basket = (panel: Element) => text(query(panel, ".basket"));

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

  it("filters the gallery by Outcome and Flags from the tiles", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, ".stat.failed"));
    expect(names(panel)).toEqual(["Untitled Run", "Helmet"]);
    expect((query(panel, ".outcome-filter") as HTMLSelectElement).value).toBe("failed_cancelled");

    await click(panel, query(panel, ".stat.flagged"));
    expect(names(panel)).toEqual(["Helmet"]);
    expect(text(query(panel, ".stat.flagged"))).toContain("Showing only these");

    await click(panel, query(panel, ".stat.failed"));
    await click(panel, query(panel, ".stat.flagged"));
    expect(names(panel)).toHaveLength(3);
  });

  it("charts the cost per month stacked by kind and filters by the month clicked", async () => {
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
    // Only the highest month and the one picked carry their value.
    expect(columns.map(text)).toEqual(["€2.00 Dec", "Jan"]);
    expect(columns[1].title).toBe(
      "January 2026\nElectricity: €0.42\nMaterial: €0.31\nOther: €0.50",
    );
    expect(columns.map((column) => queryAll(column, "rect, path").length)).toEqual([2, 3]);
    expect(text(query(panel, ".per-month .legend"))).toBe("Electricity Material Other");

    await click(panel, columns[1]);
    expect(queryAll(panel, ".per-month .column").map(text)).toEqual(["€2.00 Dec", "€1.23 Jan"]);
    await click(panel, queryAll(panel, ".per-month .column")[0]);
    expect(text(panel)).toContain("No Runs match the filters.");
    expect((query(panel, ".month-filter") as HTMLSelectElement).value).toBe("2025-12");

    await click(panel, queryAll(panel, ".per-month .column")[1]);
    expect(names(panel)).toHaveLength(3);
    await click(panel, queryAll(panel, ".per-month .column")[1]);
    expect((query(panel, ".month-filter") as HTMLSelectElement).value).toBe("");
  });

  it("charts the cost by Material", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(queryAll(panel, ".by-material .bar-row").map(text)).toEqual(["PLA Basic Black €0.31"]);
  });

  it("shows the Run running now at its live cost and reads the totals afresh", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);
    expect(queryAll(panel, ".running")).toHaveLength(0);
    const loaded = sent(backend, AGGREGATES).length;

    backend.push(SUBSCRIBE, started);
    backend.push(SUBSCRIBE, updated);
    await settle(panel);

    expect(text(query(panel, ".running"))).toBe(
      "Running now Untitled Run Kobra · 0 h 45 min €0.25 Provisional, updates live",
    );
    expect(query(panel, ".running a").getAttribute("href")).toBe("/wattbill/run/print-live");
    expect(sent(backend, AGGREGATES).length).toBeGreaterThan(loaded);
  });

  it("says when the totals can't be loaded and still shows the Runs", async () => {
    const backend = recordedBackend().reply(AGGREGATES, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend);

    expect(text(panel)).toContain("WattBill could not load its totals.");
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

describe("Gallery filters", () => {
  it("find Runs by name, Device, month, Outcome and Flags, all at once", async () => {
    const panel = await mountPanel(recordedBackend());

    await fill(panel, query(panel, ".name-filter"), "hel");
    expect(names(panel)).toEqual(["Helmet"]);
    await fill(panel, query(panel, ".name-filter"), "");

    await fill(panel, query(panel, ".outcome-filter"), "completed");
    expect(names(panel)).toEqual(["Benchy"]);
    await fill(panel, query(panel, ".device-filter"), "device-mini");
    expect(text(panel)).toContain("No Runs match the filters.");
    await fill(panel, query(panel, ".outcome-filter"), "");
    expect(names(panel)).toEqual(["Untitled Run"]);
    await fill(panel, query(panel, ".device-filter"), "");

    await fill(panel, query(panel, ".flagged-filter input"), "on");
    expect(names(panel)).toEqual(["Helmet"]);
    await fill(panel, query(panel, ".flagged-filter input"), "off");

    expect(queryAll(panel, ".month-filter option").map(text)).toEqual([
      "All months",
      "January 2026",
    ]);
    await fill(panel, query(panel, ".month-filter"), "2026-01");
    expect(names(panel)).toHaveLength(3);
  });

  it("offers the Runs in progress as an Outcome", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);
    backend.push(SUBSCRIBE, started);
    await settle(panel);

    await fill(panel, query(panel, ".outcome-filter"), "open");

    expect(names(panel)).toEqual(["Untitled Run"]);
  });
});

describe("Selection basket", () => {
  it("collects selected final Runs with their names and total", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);
    backend.push(SUBSCRIBE, started);
    await settle(panel);
    expect(queryAll(panel, ".basket")).toHaveLength(0);

    await fill(panel, pick(panel, "Helmet"), "on");
    await fill(panel, pick(panel, "Benchy"), "on");

    expect(basket(panel)).toBe("2 Runs €1.16 Benchy, Helmet Cost Statement… Delete Clear");
    expect(queryAll(panel, ".pick-tile.selected")).toHaveLength(2);
    // The open Run can't be selected.
    expect(queryAll(panel, "input.pick")).toHaveLength(3);

    await click(panel, query(panel, ".basket .clear"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
  });

  it("selects all ended Runs the filter shows, and clears them again", async () => {
    const panel = await mountPanel(recordedBackend());
    await click(panel, query(panel, ".stat.failed"));

    await click(panel, query(panel, ".select-all"));
    expect(basket(panel)).toMatch(/^2 Runs €0.37 Helmet, Untitled Run/);

    await fill(panel, query(panel, ".outcome-filter"), "");
    await click(panel, query(panel, ".select-all"));
    expect(basket(panel)).toMatch(/^3 Runs €1.23 Benchy, Helmet, Untitled Run/);

    await click(panel, query(panel, ".select-all"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
  });

  it("keeps filter and selection while a Run page is open", async () => {
    const panel = await mountPanel(recordedBackend());
    await fill(panel, query(panel, ".name-filter"), "e");
    await fill(panel, pick(panel, "Helmet"), "on");

    await click(panel, query(panel, ".tile[href='/wattbill/run/benchy']"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
    await click(panel, query(panel, ".title a"));

    expect((query(panel, ".name-filter") as HTMLInputElement).value).toBe("e");
    expect(basket(panel)).toMatch(/^1 Run €0.30 Helmet/);
  });

  it("deletes the selection after confirming what the sensor totals lose", async () => {
    const backend = recordedBackend()
      .reply("wattbill/runs/delete_preview", () => recorded.deletePreview)
      .reply("wattbill/runs/delete", () => recorded.deletePreview);
    const panel = await mountPanel(backend);
    await fill(panel, pick(panel, "Helmet"), "on");
    await fill(panel, pick(panel, "Benchy"), "on");

    await click(panel, query(panel, ".basket .delete"));
    expect(sent(backend, "wattbill/runs/delete_preview")).toEqual([
      { type: "wattbill/runs/delete_preview", run_ids: ["benchy", "helmet"] },
    ]);
    expect(text(query(panel, ".dialog"))).toBe(
      "Delete 2 Runs? The sensor totals drop at once by: Total cost €0.30 Energy in Runs 1.08 kWh " +
        "Material used 0 g Runs 1 Flagged Runs 1 Sensor history is not rewritten. " +
        "This cannot be undone. Cancel Delete",
    );
    await click(panel, query(panel, ".dialog .cancel"));
    expect(sent(backend, "wattbill/runs/delete")).toEqual([]);

    await click(panel, query(panel, ".basket .delete"));
    await click(panel, query(panel, ".dialog .confirm"));

    expect(sent(backend, "wattbill/runs/delete")).toEqual([
      { type: "wattbill/runs/delete", run_ids: ["benchy", "helmet"] },
    ]);
    expect(queryAll(panel, ".dialog, .basket")).toHaveLength(0);
  });

  it("says when the selection can't be deleted", async () => {
    const backend = recordedBackend().reply("wattbill/runs/delete_preview", () => {
      throw new WsError("not_allowed");
    });
    const panel = await mountPanel(backend);
    await fill(panel, pick(panel, "Helmet"), "on");

    await click(panel, query(panel, ".basket .delete"));

    expect(basket(panel)).toContain("The selected Runs could not be deleted.");
  });
});
