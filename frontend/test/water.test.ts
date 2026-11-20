import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Group } from "../src/api";
import { recorded, recordedBackend } from "./fake-hass";
import { change, click, mountPanel, query, queryAll, text } from "./render";

const GET = "coinop/runs/get";
const ADD = "coinop/line_items/add";
const UPDATE = "coinop/line_items/update";
const AGGREGATES = "coinop/aggregates/get";

const field = (row: HTMLElement, name: string) => query(row, `[name=${name}]`) as HTMLInputElement;
const values = (row: HTMLElement) =>
  ["quantity", "unit_price", "amount"].map((name) => field(row, name).value);
const headings = (panel: Element) => queryAll(panel, ".kind h3").map(text);
/** Second, after Electricity. */
const waterCard = (panel: Element) => queryAll(panel, ".kind")[1];

/** The washer's Runs: "water-wash" measured, "basement-wash" with water added by hand. */
const washerBackend = (run = recorded.waterWash) =>
  recordedBackend()
    .reply("coinop/devices/list", () => ({
      devices: [recorded.washer, { ...recorded.washer, id: "device-basement", name: "Basement" }],
    }))
    .reply(GET, () => ({ run }));

describe("Water", () => {
  it("has its card between Electricity and Material, priced per m³", async () => {
    const panel = await mountPanel(washerBackend(), { path: "/run/water-wash" });

    expect(headings(panel)).toEqual(["Electricity", "Water", "Material", "Other"]);
    const card = waterCard(panel);
    expect(text(query(card, ".between"))).toBe("Water €0.23");
    const row = query(card, ".item");
    expect(text(query(row, ".evidence"))).toBe("Measured by a water meter · 2 price segments");
    expect(queryAll(row, ".segments li").map(text)).toEqual([
      "10:00 – 10:30 AM · 20 L × €4.00/m³",
      "10:30 – 11:00 AM · 30 L × €5.00/m³",
    ]);
    expect(values(row)).toEqual(["50", "4.6", "0.23"]);
    expect(text(query(row, ".unit.per"))).toBe("€/m³");
    expect(queryAll(row, "ha-icon-button.delete")).toHaveLength(0);
  });

  it("is added by hand to a washing machine Run without a water source", async () => {
    const backend = washerBackend(recorded.wash).reply(ADD, () => recorded.lineItemsAddWater);
    const panel = await mountPanel(backend, { path: "/run/wash" });
    expect(text(waterCard(panel))).toContain("None");

    await click(panel, query(panel, "ha-button.add-water"));
    const form = query(waterCard(panel), ".add-item form");
    expect(text(form)).toContain("L");
    expect(text(form)).toContain("€/m³");
    await change(panel, field(form, "quantity"), "60");
    await change(panel, field(form, "unit_price"), "4.5");
    await click(panel, query(form, "ha-button[type=submit]"));

    expect(backend.sent(ADD)).toEqual([
      { type: ADD, run_id: "wash", kind: "water", quantity: 60, unit_price: 0.0045 },
    ]);
    const row = query(waterCard(panel), ".item");
    expect(text(query(row, ".evidence"))).toBe("Entered by hand");
    expect(values(row)).toEqual(["60", "4.5", "0.27"]);
    expect(queryAll(waterCard(panel), "ha-button.add-water")).toHaveLength(0);
    expect(queryAll(row, "ha-icon-button.delete")).toHaveLength(1);

    backend.reply(UPDATE, () => recorded.lineItemsAddWater);
    await change(panel, field(row, "unit_price"), "5");
    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        run_id: "wash",
        line_item_id: "basement-wash-water",
        unit_price: 0.005,
      },
    ]);
  });

  it("has no card on a printer's Run", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(headings(panel)).toEqual(["Electricity", "Material", "Other"]);
  });
});

describe("Water in the Overview", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-01-20T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  const groups = (key: string) =>
    recorded.aggregates.find(({ group_by }) => group_by.join() === key)?.groups ?? [];

  it("is a cost kind of the chart per month once a Device has water", async () => {
    const water: Group = {
      ...groups("month,kind")[0],
      kind: "water",
      cost: 0.2,
      water_cost: 0.2,
      water_litres: 50,
    };
    const backend = recordedBackend()
      .reply("coinop/devices/list", () => ({ devices: [recorded.washer] }))
      .reply(AGGREGATES, (msg) => {
        const key = (msg.group_by as string[]).join();
        return { groups: key === "month,kind" ? [...groups(key), water] : groups(key) };
      });
    const panel = await mountPanel(backend);

    const [column] = queryAll(panel, ".per-month .column");
    expect(column.title).toBe(
      "January 2026\nElectricity: €0.42\nWater: €0.20\nMaterial: €0.31\nOther: €0.50",
    );
    expect(text(query(panel, ".per-month .legend"))).toBe("Electricity Water Material Other");
  });
});
