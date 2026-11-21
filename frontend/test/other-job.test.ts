import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const LIST = "coinop/devices/list";
const GET = "coinop/runs/get";
const SETTINGS = "coinop/devices/update_settings";
const { cncRouter, sign, stock } = recorded;

const backendWith = (language = "en") =>
  recordedBackend({ language })
    .reply(LIST, () => ({ devices: [cncRouter] }))
    .subscription("coinop/catalog/subscribe", () => [stock])
    .reply(SETTINGS, (msg) => ({
      settings: { ...cncRouter.settings, ...(msg.settings as object) },
    }));

describe("An Other Device with Job and Material, Images and a Part Count", () => {
  it.each([
    [
      "en",
      "CNC router " +
        "Status sensor.router_status " +
        "Job name sensor.router_job " +
        "Material used sensor.router_stock_used · g " +
        "Not used Slots, Thumbnail, Camera " +
        "Consumption source Estimate from average power 300 W running " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Default Material MDF " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ],
    [
      "de",
      "CNC router " +
        "Status sensor.router_status " +
        "Auftragsname sensor.router_job " +
        "Materialverbrauch sensor.router_stock_used · g " +
        "Nicht verwendet Fächer, Vorschaubild, Kamera " +
        "Verbrauchsquelle Aus Durchschnittsleistung schätzen 300 W im Betrieb " +
        "Strompreis 0,30 € pro kWh " +
        "In Home Assistant neu konfigurieren " +
        "Standardmaterial MDF " +
        "Tags für neue Läufe Keine " +
        "Automatische Postenvorlagen Keine",
    ],
  ])(
    "shows its job inputs and default Material, and no Doses or Program rows (%s)",
    async (language, card) => {
      const panel = await mountPanel(backendWith(language), { path: "/devices" });

      expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["CNC router"]);
      expect(queryAll(panel, ".device").map(text)).toEqual([card]);
      expect(queryAll(panel, ".device .program-rows, .device .doses")).toEqual([]);
    },
  );

  it("picks its default Material in its settings, next to no Dose list or Program Defaults", async () => {
    const backend = backendWith();
    const panel = await mountPanel(backend, { path: "/devices" });

    await click(panel, iconButton(panel, "Edit settings of CNC router"));

    const dialog = query(panel, ".settings-dialog");
    expect(queryAll(dialog, ".field .label").map(text)).toEqual([
      "Default Material",
      "Tags for new Runs",
      "Automatic templates",
    ]);
    expect(text(query(dialog, ".default-material .hint"))).toBe(
      "Charged for a Run's measured usage, and pre-filled when the Device reports none.",
    );
    await fill(panel, query(dialog, ".default-material select"), "plywood");
    await click(panel, query(dialog, "ha-button.save"));
    expect(backend.sent(SETTINGS)).toEqual([
      { type: SETTINGS, device_id: "device-cnc-router", settings: { default_material: "plywood" } },
    ]);
    expect(text(query(panel, ".device .default-material"))).toBe("Plywood sheet");
  });

  it("shows its Run's job name, Material and cost per part", async () => {
    const backend = backendWith().reply(GET, () => ({ run: sign }));

    const panel = await mountPanel(backend, { path: "/run/sign" });

    expect(text(query(panel, ".facts dl"))).toBe(
      "Device CNC router Started Jan 15, 2026, 10:00 AM Ended Jan 15, 2026, 11:00 AM " +
        "Running time 1 h Part Count 3 Tags None",
    );
    expect(queryAll(panel, ".kind").map((card) => text(query(card, ".between")))).toEqual([
      "Electricity €0.09",
      "Material €0.60",
      "Other €0.00",
    ]);
    expect(queryAll(panel, ".kind .item .quantity").map(text)).toEqual(["0.3 kWh", "120 g"]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.69 Cost per part (3) €0.23");
    await click(panel, query(panel, ".facts ha-icon-button.edit"));
    expect(queryAll(panel, ".run-dialog [name=part_count]")).toHaveLength(1);
    expect(queryAll(panel, ".run-dialog [name=program]")).toEqual([]);
  });
});
