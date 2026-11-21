import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";
import { headers, input, openDialog } from "./settings-dialog";

const LIST = "coinop/devices/list";
const SETTINGS = "coinop/devices/update_settings";
const [kobra] = recorded.devices;

const backendWith = (washer = recorded.perProgram) =>
  recordedBackend()
    .reply(LIST, () => ({ devices: [kobra, washer] }))
    .subscription("coinop/catalog/subscribe", () => [
      {
        ...recorded.catalog.filled,
        materials: [...recorded.catalog.filled.materials, ...recorded.laundry],
      },
    ])
    .reply(SETTINGS, (msg) => ({
      settings: { ...washer.settings, ...(msg.settings as object) },
    }));
const washerCard = (panel: Element) => queryAll(panel, ".device")[1] as HTMLElement;

describe("Electricity and water per Program", () => {
  it("name the source on the card", async () => {
    const panel = await mountPanel(backendWith(), { path: "/devices" });

    expect(text(query(washerCard(panel), ".consumption"))).toBe(
      "Per Program (kWh in the Program Defaults)",
    );
  });

  it("have kWh and litres columns in the Program Defaults, Default row included", async () => {
    const panel = await mountPanel(backendWith(), { path: "/devices" });
    const dialog = await openDialog(panel, recorded.perProgram);

    expect(headers(dialog)).toEqual(["Program", "Electricity (kWh)", "Water (L)"]);
    expect(input(dialog, "Default kWh").value).toBe("0.9");
    expect(input(dialog, "Default litres").value).toBe("50");
    expect(input(dialog, "kWh for Wool").value).toBe("0.4");
    expect(input(dialog, "Litres for Wool").value).toBe("45");
    expect(text(query(dialog, ".program-defaults .hint"))).toBe(
      "Amounts per Run: kWh and litres when nothing measures them, and a column for each Dose " +
        "above, in its Material's unit. An empty cell means not set or not dosed. A Run uses " +
        "the row of its Program, else the Default row.",
    );
  });

  it("store a value entered and drop one cleared", async () => {
    const backend = backendWith();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, recorded.perProgram);

    await fill(panel, input(dialog, "kWh for Wool"), "0.5");
    await fill(panel, input(dialog, "Default litres"), "");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: {}, kwh: 0.9 },
        programs: { Wool: { doses: {}, kwh: 0.5, litres: 45 } },
      },
    });
  });

  it("leave out litres for a washing machine without water, keeping kWh beside the Doses", async () => {
    const backend = backendWith(recorded.washer);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, recorded.perProgram);
    expect(headers(dialog)).toEqual([
      "Program",
      "Electricity (kWh)",
      "Liquid detergent (ml)",
      "Colour pods (pcs)",
    ]);

    await fill(panel, input(dialog, "kWh for Wool"), "0.6");
    await fill(panel, input(dialog, "Liquid detergent for Wool"), "45");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toMatchObject({
      program_defaults: { programs: { Wool: { doses: { "dose-detergent": 45 }, kwh: 0.6 } } },
    });
  });

  it("take a Program's water to the millilitre", async () => {
    const backend = backendWith(recorded.coffeeMachine);
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Coffee machine"));
    const dialog = query(panel, ".settings-dialog");
    expect(input(dialog, "Default litres").value).toBe("0.125");
    expect(input(dialog, "Litres for Espresso").value).toBe("0.04");

    await fill(panel, input(dialog, "Litres for Cappuccino"), "0.06");
    await fill(panel, input(dialog, "Litres for Espresso"), "0.035");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: { "dose-beans": 8 }, kwh: 0.02, litres: 0.125 },
        programs: {
          Espresso: { doses: { "dose-beans": 8 }, kwh: 0.012, litres: 0.035 },
          Cappuccino: { doses: {}, litres: 0.06 },
        },
      },
    });
  });

  it("suggest a measured mean of under a litre to the millilitre", async () => {
    const backend = backendWith(recorded.coffeeMachine).reply(
      "coinop/devices/measured_suggestions",
      () => ({ suggestions: recorded.smallSuggestions }),
    );
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Coffee machine"));
    const dialog = query(panel, ".settings-dialog");
    const suggestion = query(
      input(dialog, "Default litres").closest("td") as HTMLElement,
      ".suggestion",
    );
    expect(text(suggestion)).toBe("Ø 0.045 L · 2 Runs");

    await click(panel, suggestion);

    expect(input(dialog, "Default litres").value).toBe("0.045");
  });

  it("show their method on the Run page", async () => {
    const backend = backendWith().reply("coinop/runs/get", () => ({
      run: recorded.perProgramWash,
    }));
    const panel = await mountPanel(backend, { path: "/run/wool" });

    expect(queryAll(panel, ".kind .evidence").map(text)).toEqual([
      "From the Program Defaults",
      "From the Program Defaults",
    ]);
  });

  it("flag a missing default", async () => {
    const backend = backendWith().reply("coinop/runs/get", () => ({
      run: { ...recorded.perProgramWash, flags: ["default_missing"] },
    }));
    const panel = await mountPanel(backend, { path: "/run/wool" });

    expect(text(panel)).toContain(
      "Neither a measurement nor a Program default was found: enter the quantity",
    );
  });
});
