import { describe, expect, it } from "vitest";
import type { Device } from "../src/api";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, text } from "./render";
import { headers, input, openDialog } from "./settings-dialog";

const LIST = "coinop/devices/list";
const SETTINGS = "coinop/devices/update_settings";
const SUGGESTIONS = "coinop/devices/measured_suggestions";
const GET = "coinop/runs/get";
const ADD = "coinop/line_items/add";

const NONE: Device["ha_settings"]["consumption"] = { source: "none" };
/** `device` with electricity source none, the way reconfigure leaves it: its price kept. */
const withoutElectricity = (device: Device): Device => ({
  ...device,
  ha_settings: { ...device.ha_settings, consumption: NONE },
});

const devicesBackend = (device: Device, language = "en") =>
  recordedBackend({ language })
    .reply(LIST, () => ({ devices: [device] }))
    .subscription("coinop/catalog/subscribe", () => [
      {
        ...recorded.catalog.filled,
        materials: [...recorded.catalog.filled.materials, ...recorded.laundry],
      },
    ])
    .reply(SETTINGS, (msg) => ({
      settings: { ...device.settings, ...(msg.settings as object) },
    }));

describe("A Device with electricity source none", () => {
  const { unpowered } = recorded;

  it.each([
    ["en", "Consumption source None", "Water price €4.00 per m³"],
    ["de", "Verbrauchsquelle Keine", "Wasserpreis 4,00 € pro m³"],
  ])(
    "names the source on its card, without an electricity price (%s)",
    async (language, source, water) => {
      const panel = await mountPanel(devicesBackend(unpowered, language), { path: "/devices" });

      const card = text(query(panel, ".device"));
      expect(card).toContain(source);
      expect(card).toContain(water);
      expect(queryAll(panel, ".device .price")).toEqual([]);
    },
  );

  it("shows no electricity price it kept from an earlier source either", async () => {
    const device = withoutElectricity(recorded.washer);
    const panel = await mountPanel(devicesBackend(device), { path: "/devices" });

    expect(text(query(panel, ".device .consumption"))).toBe("None");
    expect(queryAll(panel, ".device .price")).toEqual([]);
  });

  it("has Program Defaults without the kWh column, its litres as before", async () => {
    const panel = await mountPanel(devicesBackend(unpowered), { path: "/devices" });
    const dialog = await openDialog(panel, unpowered);

    expect(headers(dialog)).toEqual(["Program", "Water (L)"]);
    expect(input(dialog, "Default litres").value).toBe("50");
    expect(input(dialog, "Litres for Wool").value).toBe("45");
    expect(text(query(dialog, ".program-defaults .hint"))).toBe(
      "Amounts per Run: litres when nothing measures them, and a column for each Dose above, " +
        "in its Material's unit. An empty cell means not set or not dosed. A Run uses the row " +
        "of its Program, else the Default row.",
    );
  });

  it("keeps the kWh entered before while another cell changes", async () => {
    const backend = devicesBackend(unpowered);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, unpowered);

    await fill(panel, input(dialog, "Litres for Wool"), "40");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: {}, kwh: 0.9, litres: 50 },
        programs: { Wool: { doses: {}, kwh: 0.4, litres: 40 } },
      },
    });
  });

  it("is offered the measured litres but no measured kWh", async () => {
    const measured = { kwh: { mean: 1.2, runs: 3 }, litres: { mean: 48, runs: 2 } };
    const backend = devicesBackend(unpowered).reply(SUGGESTIONS, () => ({
      suggestions: { default: measured, programs: { Wool: measured } },
    }));
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, unpowered);

    expect(queryAll(dialog, ".suggestion").map(text)).toEqual([
      "Ø 48 L · 2 Runs",
      "Ø 48 L · 2 Runs",
    ]);
  });

  it("has just its Dose columns in the Program Defaults without water too", async () => {
    const device = withoutElectricity(recorded.washer);
    const panel = await mountPanel(devicesBackend(device), { path: "/devices" });
    const dialog = await openDialog(panel, device);

    expect(headers(dialog)).toEqual(["Program", "Liquid detergent (ml)", "Colour pods (pcs)"]);
    expect(text(query(dialog, ".program-defaults .hint"))).toBe(
      "Amounts per Run: a column for each Dose above, in its Material's unit. An empty cell " +
        "means not dosed. A Run uses the row of its Program, else the Default row.",
    );
  });

  it("has no Program Defaults when the kWh were all they held", async () => {
    const device = withoutElectricity(recorded.oven);
    const panel = await mountPanel(devicesBackend(device), { path: "/devices" });
    const dialog = await openDialog(panel, device);

    expect(queryAll(dialog, ".program-defaults")).toEqual([]);
    expect(text(query(panel, ".device .program-rows"))).toBe("Fan plus 180°");
  });
});

describe("A Run without an Electricity Line Item", () => {
  const runBackend = (language = "en") =>
    recordedBackend({ language })
      .reply(LIST, () => ({ devices: [recorded.unpowered] }))
      .reply(GET, () => ({ run: recorded.unpoweredWash }));
  const headings = (panel: Element) => queryAll(panel, ".kind h3").map(text);
  const field = (dialog: HTMLElement, name: string) =>
    query(dialog, `[name=${name}]`) as HTMLInputElement;
  const save = (panel: Element) => click(panel, query(panel, ".dialog ha-button.save"));

  it("has no electricity card, and a total of what it has", async () => {
    const panel = await mountPanel(runBackend(), { path: "/run/unpowered" });

    expect(headings(panel)).toEqual(["Water", "Material", "Other"]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.18");
  });

  it.each([
    ["en", "Add electricity"],
    ["de", "Strom hinzufügen"],
  ])("offers to add electricity (%s)", async (language, label) => {
    const panel = await mountPanel(runBackend(language), { path: "/run/unpowered" });

    expect(text(query(panel, "ha-button.add-electricity"))).toBe(label);
  });

  it("takes electricity by hand in kWh, which is then its entered Line Item", async () => {
    const backend = runBackend().reply(ADD, () => recorded.lineItemsAddElectricity);
    const panel = await mountPanel(backend, { path: "/run/unpowered" });

    await click(panel, query(panel, "ha-button.add-electricity"));
    const dialog = query(panel, ".new-item-dialog");
    expect(text(query(dialog, "h2"))).toBe("Add electricity");
    expect(queryAll(dialog, ".with-unit .unit").map(text)).toEqual(["kWh", "€/kWh"]);
    await save(panel);
    expect(backend.sent(ADD)).toEqual([]);
    await fill(panel, field(dialog, "quantity"), "0.4");
    await fill(panel, field(dialog, "unit_price"), "-0.3");
    await save(panel);
    expect(backend.sent(ADD)).toEqual([]);
    await fill(panel, field(dialog, "unit_price"), "0.3");
    await save(panel);

    expect(backend.sent(ADD)).toEqual([
      { type: ADD, run_id: "unpowered", kind: "electricity", quantity: 0.4, unit_price: 0.3 },
    ]);
    expect(headings(panel)).toEqual(["Electricity", "Water", "Material", "Other"]);
    const [card] = queryAll(panel, ".kind");
    expect(text(query(card, ".between"))).toBe("Electricity €0.12");
    const row = query(card, ".item");
    expect(text(query(row, ".evidence"))).toBe("Entered by hand");
    expect(
      ["quantity", "unit_price", "amount"].map((name) => text(query(row, `.${name}`))),
    ).toEqual(["0.4 kWh", "€0.30", "€0.12"]);
    expect(queryAll(row, "ha-icon-button.edit, ha-icon-button.delete")).toHaveLength(2);
    expect(queryAll(panel, "ha-button.add-electricity")).toEqual([]);
  });

  it("is not offered a second one", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(headings(panel)).toEqual(["Electricity", "Material", "Other"]);
    expect(queryAll(panel, "ha-button.add-electricity")).toEqual([]);
  });
});
