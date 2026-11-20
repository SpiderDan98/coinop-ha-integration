import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const AGGREGATES = "coinop/aggregates/get";

/** The recorded groups of `group_by`, as the backend would answer with other Runs. */
const groups = (key: string) =>
  recorded.aggregates.find(({ group_by }) => group_by.join() === key)?.groups ?? [];
const rows = (panel: Element, table: string) =>
  queryAll(panel, `.${table} tbody tr, .${table} tfoot tr`).map(text);

describe("Analysis tab", () => {
  it("opens from the toolbar as its first tab", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/analysis"]`));

    expect(location.pathname).toBe("/coinop/analysis");
    expect(queryAll(panel, "a.tab").map((tab) => tab.title)).toEqual([
      "Overview",
      "Runs",
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(query(panel, "a.tab.on").title).toBe("Analysis");
    expect(text(query(panel, ".page-title"))).toBe("Analysis");
  });

  it("on a phone, names its tabs and leads back through the title", async () => {
    const panel = await mountPanel(recordedBackend(), { narrow: true });

    await click(panel, query(panel, `a.tab[href$="/analysis"]`));

    expect(queryAll(panel, "a.tab").map(text)).toEqual([
      "Runs",
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(text(query(panel, "a.tab.on"))).toBe("Analysis");
    await click(panel, query(panel, ".title a"));
    expect(location.pathname).toBe("/coinop");
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
    backend.push("coinop/runs/subscribe", recorded.changes[0]);
    await settle(panel);

    expect(rows(panel, "by-kind").at(-1)).toBe("Total €2.23");
  });

  it("says when the totals can't be loaded", async () => {
    const backend = recordedBackend().reply(AGGREGATES, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend, { path: "/analysis" });

    expect(text(panel)).toContain("Coin-op could not load its totals.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/analysis" });

    expect(queryAll(panel, ".table h3").map(text)).toEqual([
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

describe("Analysis rows", () => {
  const links = (panel: Element, table: string) =>
    queryAll(panel, `.${table} tbody a`).map((link) => link.getAttribute("href"));

  it("link to the Runs of their Device, month, Outcome or Tag", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    expect(links(panel, "by-device")).toEqual([
      "/coinop/runs?device=device-kobra",
      "/coinop/runs?device=device-mini",
    ]);
    expect(links(panel, "by-month")).toEqual(["/coinop/runs?month=2026-01"]);
    expect(links(panel, "by-outcome")).toEqual([
      "/coinop/runs?outcome=completed",
      "/coinop/runs?outcome=cancelled",
      "/coinop/runs?outcome=failed",
    ]);
    expect(links(panel, "by-tag")).toEqual([
      "/coinop/runs?tag=Cosplay+helmet",
      "/coinop/runs?tag=Gift",
      "/coinop/runs?untagged=1",
    ]);
    expect(queryAll(panel, ".by-kind a, .by-material a")).toEqual([]);
  });

  it("open the Runs tab filtered, a removed Device's too", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/analysis" });

    await click(panel, queryAll(panel, ".by-device tbody a")[1]);

    expect(location.pathname + location.search).toBe("/coinop/runs?device=device-mini");
    expect(queryAll(panel, ".tile .strong").map(text)).toEqual(["Untitled Run"]);
  });
});

describe("An empty Analysis tab", () => {
  it("says there are no Runs instead of empty tables", async () => {
    const backend = recordedBackend()
      .subscription("coinop/runs/subscribe", () => [{ runs: [] }])
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
