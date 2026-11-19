import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const AGGREGATES = "wattbill/aggregates/get";

/** The recorded groups of `group_by`, as the backend would answer with other Runs. */
const groups = (key: string) =>
  recorded.aggregates.find(({ group_by }) => group_by.join() === key)?.groups ?? [];
const rows = (panel: Element, table: string) =>
  queryAll(panel, `.${table} tbody tr, .${table} tfoot tr`).map(text);

describe("Analysis tab", () => {
  it("opens from the toolbar as its first tab", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/analysis"]`));

    expect(location.pathname).toBe("/wattbill/analysis");
    expect(queryAll(panel, "a.tab").map(text)).toEqual([
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(text(query(panel, "a.tab.on"))).toBe("Analysis");
  });

  it("totals the cost by kind with each kind's share", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    expect(rows(panel, "by-kind")).toEqual([
      "Electricity €0.42 34%",
      "Material €0.31 25%",
      "Other €0.50 41%",
      "Total €1.23",
    ]);
  });

  it("totals each Device, a removed one marked as removed", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    expect(rows(panel, "by-device")).toEqual([
      "Kobra 2 10 h 15 min 1.23 kWh €1.16",
      "Mini (removed) 1 30 min 0.24 kWh €0.07",
    ]);
  });

  it("totals each month by kind, the latest first", async () => {
    const december = {
      ...groups("month")[0],
      month: "2025-12",
      cost: 2,
      electricity_cost: 0.5,
      material_cost: 1.5,
      other_cost: 0,
      runs: 1,
    };
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      return { groups: key === "month" ? [december, ...groups(key)] : groups(key) };
    });
    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(rows(panel, "by-month")).toEqual([
      "January 2026 3 €0.42 €0.31 €0.50 €1.23",
      "December 2025 1 €0.50 €1.50 €0.00 €2.00",
    ]);
  });

  it("totals each Material's usage and cost, Material Line Items without one apart", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    expect(rows(panel, "by-material")).toEqual([
      "PLA Basic Black 12.5 g €0.31 €24.80",
      "No Material 0 g €0.00 –",
    ]);
  });

  it("totals each Outcome with its share of the cost, open Runs last", async () => {
    const open = { ...groups("outcome")[0], outcome: null, cost: 0.2, runs: 1 };
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      return { groups: key === "outcome" ? [...groups(key), open] : groups(key) };
    });
    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(rows(panel, "by-outcome")).toEqual([
      "Completed 1 €0.86 70%",
      "Cancelled 1 €0.07 6%",
      "Failed 1 €0.30 24%",
      "In progress 1 €0.20 16%",
    ]);
  });

  it("totals each Tag, marked as overlapping since a Run counts in each of its Tags", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    expect(rows(panel, "by-tag")).toEqual([
      "Cosplay helmet 1 €0.30",
      "Gift 2 €1.16",
      "No tag 1 €0.07",
    ]);
    expect(text(query(panel, ".by-tag header"))).toBe(
      "By Tag A Run with several Tags counts in each of them.",
    );
    expect(queryAll(panel, ".by-tag tfoot")).toEqual([]);
  });

  it("reads the totals afresh when a Run changes", async () => {
    let extra = 0;
    const backend = recordedBackend().reply(AGGREGATES, (msg) => ({
      groups: groups((msg.group_by as string[]).join()).map((group) => ({
        ...group,
        cost: group.cost + extra,
      })),
    }));
    const panel = await mountPanel(backend, { path: "/analysis" });
    expect(rows(panel, "by-kind").at(-1)).toBe("Total €1.23");

    extra = 1;
    backend.push("wattbill/runs/subscribe", recorded.changes[0]);
    await settle(panel);

    expect(rows(panel, "by-kind").at(-1)).toBe("Total €2.23");
  });

  it("says when the totals can't be loaded", async () => {
    const backend = recordedBackend().reply(AGGREGATES, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(text(panel)).toContain("WattBill could not load its totals.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/analysis" });

    expect(queryAll(panel, "section h3").map(text)).toEqual([
      "Nach Art",
      "Nach Gerät",
      "Nach Monat",
      "Nach Material",
      "Nach Ausgang",
      "Nach Tag",
    ]);
    expect(rows(panel, "by-tag")).toContain("Ohne Tag 1 0,07 €");
  });
});

describe("An empty Analysis tab", () => {
  it("says there are no Runs instead of empty tables", async () => {
    const backend = recordedBackend()
      .subscription("wattbill/runs/subscribe", () => [{ runs: [] }])
      .reply(AGGREGATES, () => ({ groups: [] }));

    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(queryAll(panel, "table")).toEqual([]);
    expect(text(panel)).toContain("No Runs yet.");
  });

  it("says a table has nothing yet instead of showing only its head", async () => {
    const backend = recordedBackend().reply(AGGREGATES, (msg) => {
      const key = (msg.group_by as string[]).join();
      return { groups: key === "kind,material" ? [] : groups(key) };
    });

    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(rows(panel, "by-material")).toEqual(["No Material costs yet."]);
  });
});
