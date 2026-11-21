import { describe, expect, it } from "vitest";
import type { Device } from "../src/api";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const LIST = "coinop/devices/list";
const SETTINGS = "coinop/devices/update_settings";
const { sodaMaker, brewKettle, bottle, consumables } = recorded;

const backendWith = (device: Device, language = "en") =>
  recordedBackend({ language })
    .reply(LIST, () => ({ devices: [device] }))
    .subscription("coinop/catalog/subscribe", () => [consumables])
    .reply("coinop/devices/measured_suggestions", () => ({
      suggestions: { default: {}, programs: {} },
    }))
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

describe("An Other Device with Doses and no Program", () => {
  it.each([
    [
      "en",
      "Soda maker " +
        "Status sensor.soda_maker_status " +
        "Consumption source None " +
        "Reconfigure in Home Assistant " +
        "Doses CO₂ 8 g Cola syrup 40 ml " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ],
    [
      "de",
      "Soda maker " +
        "Status sensor.soda_maker_status " +
        "Verbrauchsquelle Keine " +
        "In Home Assistant neu konfigurieren " +
        "Dosierungen CO₂ 8 g Cola syrup 40 ml " +
        "Tags für neue Läufe Keine " +
        "Automatische Postenvorlagen Keine",
    ],
  ])(
    "lists its Doses with their Default amounts and no Program rows (%s)",
    async (language, card) => {
      const panel = await mountPanel(backendWith(sodaMaker, language), { path: "/devices" });

      expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["Soda maker"]);
      expect(queryAll(panel, ".device").map(text)).toEqual([card]);
      expect(queryAll(panel, ".device .program-rows")).toEqual([]);
    },
  );

  it("edits its Dose list and the Default row alone, with no Program to add", async () => {
    const panel = await mountPanel(backendWith(sodaMaker), { path: "/devices" });
    const dialog = await openDialog(panel, sodaMaker);

    expect(queryAll(dialog, ".doses .dose-name").map(text)).toEqual(["CO₂", "Cola syrup"]);
    expect(headers(dialog)).toEqual(["Program", "CO₂ (g)", "Cola syrup (ml)"]);
    expect(rows(dialog)).toEqual(["Default"]);
    expect(input(dialog, "Default amount of CO₂").value).toBe("8");
    expect(input(dialog, "Default amount of Cola syrup").value).toBe("40");
    expect(queryAll(dialog, ".program-defaults > input")).toEqual([]);
    expect(queryAll(dialog, ".program-defaults .suggestion")).toEqual([]);
  });

  it.each([
    [
      "en",
      "Amounts per Run: a column for each Dose above, in its Material's unit. An empty cell " +
        "means not dosed. This Device has no Program, so every Run uses the Default row.",
    ],
    [
      "de",
      "Mengen pro Lauf: eine Spalte für jede Dosierung oben, in der Einheit ihres Materials. " +
        "Ein leeres Feld heißt nicht dosiert. Dieses Gerät hat kein Programm, also verwendet " +
        "jeder Lauf die Standardzeile.",
    ],
  ])("says that every Run uses the Default row (%s)", async (language, hint) => {
    const panel = await mountPanel(backendWith(sodaMaker, language), { path: "/devices" });

    await click(panel, query(panel, ".device ha-icon-button.edit"));

    expect(text(query(panel, ".settings-dialog .program-defaults .hint"))).toBe(hint);
  });

  it("saves a changed Default amount and shows it on the card", async () => {
    const backend = backendWith(sodaMaker);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, sodaMaker);

    await fill(panel, input(dialog, "Default amount of CO₂"), "12");
    await fill(panel, input(dialog, "Default amount of Cola syrup"), "");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([
      {
        type: SETTINGS,
        device_id: "device-soda-maker",
        settings: { program_defaults: { default: { doses: { "dose-co2": 12 } }, programs: {} } },
      },
    ]);
    expect(text(query(panel, ".device .doses"))).toBe("CO₂ 12 g Cola syrup Not dosed");
  });

  it("keeps Program rows stored for it out of sight and untouched", async () => {
    const strong = { doses: { "dose-co2": 12 } };
    const stored = {
      ...sodaMaker,
      settings: {
        ...sodaMaker.settings,
        program_defaults: { ...sodaMaker.settings.program_defaults, programs: { Strong: strong } },
      },
    } satisfies Device;
    const backend = backendWith(stored);
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel, stored);

    expect(rows(dialog)).toEqual(["Default"]);
    await fill(panel, input(dialog, "Default amount of CO₂"), "9");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(SETTINGS)[0]?.settings).toEqual({
      program_defaults: {
        default: { doses: { "dose-co2": 9, "dose-syrup": 40 } },
        programs: { Strong: strong },
      },
    });
  });

  it("shows each Dose of a Run as a Material Line Item from the Default row", async () => {
    const backend = backendWith(sodaMaker).reply("coinop/runs/get", () => ({ run: bottle }));

    const panel = await mountPanel(backend, { path: "/run/bottle" });

    expect(text(query(panel, ".facts dl"))).toContain("Device Soda maker");
    expect(text(query(panel, ".facts dl"))).not.toMatch(/Program|Part Count/);
    expect(queryAll(panel, ".kind").map((card) => text(query(card, ".between")))).toEqual([
      "Material €0.56",
      "Other €0.00",
    ]);
    expect(queryAll(panel, ".kind .item .label").map(text)).toEqual([
      "CO₂ From the Default row",
      "Cola syrup From the Default row",
    ]);
    expect(queryAll(panel, ".kind .item .quantity").map(text)).toEqual(["8 g", "40 ml"]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.56");
  });

  it("asks for no Program on a manual Run", async () => {
    const panel = await mountPanel(backendWith(sodaMaker), { path: "/runs" });

    await click(panel, query(panel, "ha-button.manual-run"));

    expect(
      queryAll(panel, ".manual-dialog input[name], .manual-dialog select[name]").map((field) =>
        field.getAttribute("name"),
      ),
    ).toEqual(["name", "started", "ended", "outcome"]);
  });
});

describe("An Other Device with a Program, Doses and water", () => {
  it("lists its Doses, its Program rows and water per Program", async () => {
    const panel = await mountPanel(backendWith(brewKettle), { path: "/devices" });

    expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["Brew kettle"]);
    expect(queryAll(panel, ".device").map(text)).toEqual([
      "Brew kettle " +
        "Status sensor.brew_kettle_status " +
        "Program sensor.brew_kettle_program " +
        "Consumption source Per Program (kWh in the Program Defaults) " +
        "Electricity price €0.30 per kWh " +
        "Water source Per Program (litres in the Program Defaults) " +
        "Water price €4.00 per m³ " +
        "Reconfigure in Home Assistant " +
        "Doses Pale malt 4,000 g Hop pellets 30 g " +
        "Program rows Pale ale " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("has Program Defaults with kWh, litres and a column per Dose for each Program", async () => {
    const panel = await mountPanel(backendWith(brewKettle), { path: "/devices" });
    const dialog = await openDialog(panel, brewKettle);

    expect(headers(dialog)).toEqual([
      "Program",
      "Electricity (kWh)",
      "Water (L)",
      "Pale malt (g)",
      "Hop pellets (g)",
    ]);
    expect(rows(dialog)).toEqual(["Default", "Pale ale"]);
    expect(input(dialog, "Litres for Pale ale").value).toBe("30");
    expect(input(dialog, "Pale malt for Pale ale").value).toBe("4500");
    expect(input(dialog, "Hop pellets for Pale ale").value).toBe("");
    expect(queryAll(dialog, ".program-defaults > input")).toHaveLength(1);
    expect(text(query(dialog, ".program-defaults .hint"))).toBe(
      "Amounts per Run: kWh and litres when nothing measures them, and a column for each Dose " +
        "above, in its Material's unit. An empty cell means not set or not dosed. A Run uses " +
        "the row of its Program, else the Default row.",
    );
  });

  it("has no litres column while its water source is None", async () => {
    const dry = {
      ...brewKettle,
      ha_settings: { ...brewKettle.ha_settings, water: { source: "none" } },
    } satisfies Device;
    const panel = await mountPanel(backendWith(dry), { path: "/devices" });
    const dialog = await openDialog(panel, dry);

    expect(headers(dialog)).toEqual([
      "Program",
      "Electricity (kWh)",
      "Pale malt (g)",
      "Hop pellets (g)",
    ]);
  });
});
