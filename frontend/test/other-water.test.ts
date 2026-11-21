import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, iconButton, mountPanel, query, queryAll, text } from "./render";

const LIST = "coinop/devices/list";
const GET = "coinop/runs/get";
const { irrigation, watering } = recorded;

describe("An Other Device with water", () => {
  it.each([
    [
      "en",
      "Garden valve " +
        "Status sensor.garden_valve_status " +
        "Consumption source None " +
        "Water source Water meter sensor.garden_valve_water " +
        "Water price €4.00 per m³ " +
        "Reconfigure in Home Assistant " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ],
    [
      "de",
      "Garden valve " +
        "Status sensor.garden_valve_status " +
        "Verbrauchsquelle Keine " +
        "Wasserquelle Wasserzähler sensor.garden_valve_water " +
        "Wasserpreis 4,00 € pro m³ " +
        "In Home Assistant neu konfigurieren " +
        "Tags für neue Läufe Keine " +
        "Automatische Postenvorlagen Keine",
    ],
  ])(
    "shows its water source and price under its Type Name, and nothing it lacks (%s)",
    async (language, card) => {
      const backend = recordedBackend({ language }).reply(LIST, () => ({
        devices: [irrigation],
      }));

      const panel = await mountPanel(backend, { path: "/devices" });

      expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["Irrigation"]);
      expect(queryAll(panel, ".device").map(text)).toEqual([card]);
    },
  );

  it("has no Dose list, Program Defaults or default Material to edit", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [irrigation] }));
    const panel = await mountPanel(backend, { path: "/devices" });

    await click(panel, iconButton(panel, "Edit settings of Garden valve"));

    expect(queryAll(panel, ".settings-dialog .field .label").map(text)).toEqual([
      "Tags for new Runs",
      "Automatic templates",
    ]);
  });

  it("shows the Water card on its Run, which costs only its water", async () => {
    const backend = recordedBackend()
      .reply(LIST, () => ({ devices: [irrigation] }))
      .reply(GET, () => ({ run: watering }));

    const panel = await mountPanel(backend, { path: "/run/watering" });

    expect(text(query(panel, ".facts dl"))).toContain("Device Garden valve");
    expect(text(query(panel, ".facts dl"))).not.toMatch(/Program|Part Count/);
    expect(queryAll(panel, ".kind").map((card) => text(query(card, ".between")))).toEqual([
      "Water €0.48",
      "Material €0.00",
      "Other €0.00",
    ]);
    expect(queryAll(panel, ".kind .item .quantity").map(text)).toEqual(["120 L"]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.48");
  });
});
