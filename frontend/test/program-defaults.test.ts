import { describe, expect, it } from "vitest";
import type { Device } from "../src/api";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const LIST = "coinop/devices/list";
const SETTINGS = "coinop/devices/update_settings";
const SUGGESTIONS = "coinop/devices/measured_suggestions";
const [pods] = recorded.laundry.filter(({ id }) => id === "material-pods");
const sheets = { ...pods, id: "material-sheets", name: "Dryer sheets", type: "Dryer sheets" };

const backendWith = (device: Device) =>
  recordedBackend()
    .reply(LIST, () => ({ devices: [device] }))
    .subscription("coinop/catalog/subscribe", () => [
      { ...recorded.catalog.filled, materials: [...recorded.catalog.filled.materials, sheets] },
    ])
    .reply(SETTINGS, (msg) => ({
      settings: { ...device.settings, ...(msg.settings as object) },
    }));
const openDialog = async (panel: Element, device: Device) => {
  await click(panel, iconButton(panel, `Edit settings of ${device.name}`));
  return query(panel, ".settings-dialog");
};
const headers = (dialog: Element) => queryAll(dialog, ".program-defaults th").map(text);
const rows = (dialog: Element) => queryAll(dialog, ".program-defaults tbody tr").map(text);
const input = (root: Element, label: string) =>
  query(root, `input[aria-label="${label}"]`) as HTMLInputElement;

describe("Program Defaults of a Device with a Program and no Doses", () => {
  const { oven } = recorded;

  it("list their Program rows on the card, which has no Dose list", async () => {
    const panel = await mountPanel(backendWith(oven), { path: "/devices" });

    expect(queryAll(panel, ".device").map(text)).toEqual([
      "Oven " +
        "Status sensor.washer_status " +
        "Program sensor.washer_program " +
        "Consumption source Energy meter sensor.washer_plug_energy " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Program rows Fan plus 180° " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("are just the kWh per Program, without a Dose list or Dose columns", async () => {
    const panel = await mountPanel(backendWith(oven), { path: "/devices" });
    const dialog = await openDialog(panel, oven);

    expect(headers(dialog)).toEqual(["Program", "Electricity (kWh)"]);
    expect(rows(dialog)).toEqual(["Default", "Fan plus 180°", "Conventional heat Suggested"]);
    expect(input(dialog, "Default kWh").value).toBe("1");
    expect(input(dialog, "kWh for Fan plus 180°").value).toBe("1.6");
    expect(input(dialog, "kWh for Conventional heat").value).toBe("");
    expect(queryAll(dialog, ".doses")).toEqual([]);
    expect(text(query(dialog, ".program-defaults .hint"))).not.toMatch(/Dose|dosed|litres/);
  });

  it("store the kWh entered for a suggested Program and for one added by name", async () => {
    const backend = backendWith(oven);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, oven);

    await fill(panel, input(dialog, "kWh for Conventional heat"), "1.2");
    await fill(panel, query(dialog, ".program-defaults > input"), " Grill ");
    await fill(panel, input(dialog, "kWh for Grill"), "0.9");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([
      {
        type: SETTINGS,
        device_id: "device-oven",
        settings: {
          program_defaults: {
            default: { doses: {}, kwh: 1 },
            programs: {
              "Fan plus 180°": { doses: {}, kwh: 1.6 },
              "Conventional heat": { doses: {}, kwh: 1.2 },
              Grill: { doses: {}, kwh: 0.9 },
            },
          },
        },
      },
    ]);
    expect(text(query(panel, ".device .program-rows"))).toBe(
      "Fan plus 180°, Conventional heat, Grill",
    );
  });

  it("offer the mean kWh of a Program's measured Runs", async () => {
    const backend = backendWith(oven).reply(SUGGESTIONS, () => ({
      suggestions: recorded.ovenSuggestions,
    }));
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, oven);

    expect(backend.sent(SUGGESTIONS)).toEqual([{ type: SUGGESTIONS, device_id: "device-oven" }]);
    expect(queryAll(dialog, ".suggestion").map(text)).toEqual(["Ø 1.4 kWh · 1 Run"]);
    await click(panel, query(dialog, ".suggestion"));
    expect(input(dialog, "kWh for Fan plus 180°").value).toBe("1.4");
  });
});

describe("A tumble dryer's Program Defaults", () => {
  const { tumbleDryer } = recorded;

  it("show on a card without water", async () => {
    const panel = await mountPanel(backendWith(tumbleDryer), { path: "/devices" });

    expect(queryAll(panel, ".device").map(text)).toEqual([
      "Tumble dryer " +
        "Status sensor.washer_status " +
        "Program sensor.washer_program " +
        "Consumption source Energy meter sensor.washer_plug_energy " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Doses Dryer sheets 1 pcs " +
        "Program rows Cupboard dry " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("have a kWh column and a column per Dose, but no litres column", async () => {
    const panel = await mountPanel(backendWith(tumbleDryer), { path: "/devices" });
    const dialog = await openDialog(panel, tumbleDryer);

    expect(headers(dialog)).toEqual(["Program", "Electricity (kWh)", "Dryer sheets (pcs)"]);
    expect(rows(dialog)).toEqual(["Default", "Cupboard dry", "Iron dry Suggested"]);
    expect(input(dialog, "Dryer sheets for Cupboard dry").value).toBe("2");
    expect(queryAll(dialog, ".doses .dose-name").map(text)).toEqual(["Dryer sheets"]);
  });

  it("stay a kWh column once the Dose list is emptied", async () => {
    const backend = backendWith(tumbleDryer);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, tumbleDryer);

    await click(panel, iconButton(dialog, "Remove Dryer sheets"));

    expect(headers(dialog)).toEqual(["Program", "Electricity (kWh)"]);
    await click(panel, query(dialog, "ha-button.save"));
    expect(backend.sent(SETTINGS)[0]?.settings).toEqual({
      doses: [],
      program_defaults: {
        default: { doses: {}, kwh: 2 },
        programs: { "Cupboard dry": { doses: {}, kwh: 2.4 } },
      },
    });
  });
});

describe("A Tumble dryer set up from a washing machine's HA device", () => {
  const { dryerFromWasher } = recorded;
  const waterParts = (panel: Element) => queryAll(panel, ".device .water, .device .water-price");

  it("shows nothing about water on its card or in its Program Defaults", async () => {
    const panel = await mountPanel(backendWith(dryerFromWasher), { path: "/devices" });

    expect(queryAll(panel, ".device > dl:not(.settings)").map(text)).toEqual([
      "Status sensor.washing_machine_status " +
        "Program sensor.washing_machine_program " +
        "Consumption source Energy meter sensor.washing_machine_energy_consumption " +
        "Electricity price €0.30 per kWh",
    ]);
    expect(headers(await openDialog(panel, dryerFromWasher))).toEqual([
      "Program",
      "Electricity (kWh)",
    ]);
  });

  it("shows none either when a water source is stored for it", async () => {
    const stored = {
      ...dryerFromWasher,
      ha_settings: {
        ...dryerFromWasher.ha_settings,
        water: {
          source: "meter",
          entity_id: "sensor.washing_machine_water_consumption",
          attribute: null,
        },
        water_price: { source: "fixed", value: 4 },
      },
    } satisfies Device;
    const panel = await mountPanel(backendWith(stored), { path: "/devices" });

    expect(waterParts(panel)).toEqual([]);
    expect(headers(await openDialog(panel, stored))).toEqual(["Program", "Electricity (kWh)"]);
  });
});
