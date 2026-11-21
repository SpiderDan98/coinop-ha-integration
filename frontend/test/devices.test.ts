import { describe, expect, it } from "vitest";
import type { Material } from "../src/api";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "coinop/runs/subscribe";
const LIST = "coinop/devices/list";
const [started] = recorded.changes;
const cards = (panel: Element) => queryAll(panel, ".device").map(text);
const tiles = (panel: Element) => queryAll(panel, ".tile").map(text);

const filterBy = async (panel: Element, deviceId: string) => {
  const select = query(panel, "select.device-filter") as HTMLSelectElement;
  select.value = deviceId;
  select.dispatchEvent(new Event("change"));
  await settle(panel);
};

describe("Devices tab", () => {
  it("opens from the toolbar, and the Runs tab leads back", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/devices"]`));

    expect(location.pathname).toBe("/coinop/devices");
    expect(cards(panel)).toHaveLength(1);
    await click(panel, query(panel, 'a.tab[title="Overview"]'));
    expect(location.pathname).toBe("/coinop");
  });

  it("shows each Device's HA-side settings and its own settings read-only", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Kobra " +
        "Status sensor.kobra_status " +
        "Job name sensor.kobra_job " +
        "Material used sensor.kobra_filament_used · mm " +
        "Not used Slots, Thumbnail, Camera " +
        "Consumption source Estimate from average power 120 W running · 8 W paused " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Default Material None " +
        "Tags for new Runs Batch 7 " +
        "Automatic templates Wear Kobra",
    ]);
    expect(queryAll(panel, ".device input, .device select")).toHaveLength(0);
    expect(query(panel, ".device a").getAttribute("href")).toBe(
      "/config/integrations/integration/coinop",
    );
  });

  it("groups the Devices by their Device Type", async () => {
    const [kobra] = recorded.devices;
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [kobra, { ...kobra, id: "device-mini", name: "Mini" }],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device-type").map((section) => text(query(section, "h2")))).toEqual([
      "3D printers",
    ]);
    expect(queryAll(panel, ".device-type .device h3").map(text)).toEqual(["Kobra", "Mini"]);
  });

  it("names the Status and job attribute and an unused job input", async () => {
    const [kobra] = recorded.devices;
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        {
          ...kobra,
          ha_settings: {
            ...kobra.ha_settings,
            status: { entity_id: "event.kobra_print", attribute: "event_type" },
            job: { entity_id: null, attribute: null },
            consumption: { source: "estimate", running_power: 95.5, paused_power: null },
          },
        },
      ],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device dl"))).toBe(
      "Status event.kobra_print · event_type " +
        "Not used Job name, Material used, Slots, Thumbnail, Camera " +
        "Consumption source Estimate from average power 95.5 W running " +
        "Electricity price €0.30 per kWh",
    );
  });

  it("names the Thumbnail and Camera and whether a Snapshot is taken", async () => {
    const [kobra] = recorded.devices;
    const images = { thumbnail: "image.kobra_preview", camera: "camera.kobra" };
    const withImages = (snapshot: boolean) =>
      recordedBackend().reply(LIST, () => ({
        devices: [
          { ...kobra, ha_settings: { ...kobra.ha_settings, images: { ...images, snapshot } } },
        ],
      }));

    const on = await mountPanel(withImages(true), { path: "/devices" });
    expect(text(query(on, ".device dl"))).toContain(
      "Thumbnail image.kobra_preview Camera camera.kobra · Snapshot when a Run ends Not used Slots",
    );
    on.remove();
    const off = await mountPanel(withImages(false), { path: "/devices" });
    expect(text(query(off, ".device dl"))).toContain(
      "Camera camera.kobra · No Snapshot Not used Slots",
    );
  });

  it("names each input's entity by its friendly name, its entity id as tooltip", async () => {
    const backend = recordedBackend();
    backend.hass.states = {
      "sensor.kobra_status": { attributes: { friendly_name: "Kobra Print status" } },
    };

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device dd"))).toBe("Kobra Print status");
    expect(query(panel, ".device dd .entity").title).toBe("sensor.kobra_status");
  });

  it("names the price, consumption and Slot entities too, their entity ids as tooltips", async () => {
    const [kobra] = recorded.devices;
    const named = {
      "sensor.tibber_price": "Tibber price",
      "sensor.plug_power": "Plug power",
      "sensor.ace_slot_1": "ACE Slot 1",
      "sensor.ace_loaded_slot": "ACE Loaded slot",
    };
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        {
          ...kobra,
          ha_settings: {
            ...kobra.ha_settings,
            job: {
              ...kobra.ha_settings.job,
              slots: ["sensor.ace_slot_1"],
              colour_attribute: null,
              loaded_slot: "sensor.ace_loaded_slot",
            },
            consumption: {
              source: "power",
              entity_id: "sensor.plug_power",
              attribute: null,
              running_power: null,
            },
            price: {
              source: "entity",
              entity_id: "sensor.tibber_price",
              attribute: null,
              unit: "€/kWh",
              factor: null,
            },
          },
        },
      ],
    }));
    backend.hass.states = Object.fromEntries(
      Object.entries(named).map(([id, name]) => [id, { attributes: { friendly_name: name } }]),
    );

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device .slots"))).toBe("ACE Slot 1 Loaded slot ACE Loaded slot");
    expect(text(query(panel, ".device .consumption"))).toBe("Power sensor Plug power");
    expect(text(query(panel, ".device .price"))).toBe("From Tibber price");
    expect(queryAll(panel, ".device .entity").map((name) => name.title)).toEqual([
      "sensor.kobra_status",
      "sensor.kobra_job",
      "sensor.kobra_filament_used",
      "sensor.ace_slot_1",
      "sensor.ace_loaded_slot",
      "sensor.plug_power",
      "sensor.tibber_price",
    ]);
  });

  it("shows no images for a Device added before they existed", async () => {
    const [kobra] = recorded.devices;
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [{ ...kobra, ha_settings: { ...kobra.ha_settings, images: undefined } }],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device dl"))).toContain("Not used Slots, Thumbnail, Camera");
  });

  it("names the Slots in order with their colour attribute and the Loaded slot", async () => {
    const [kobra] = recorded.devices;
    const slots = {
      slots: ["sensor.ace_slot_1", "sensor.ace_slot_2"],
      colour_attribute: "color_hex",
      loaded_slot: "sensor.ace_loaded_slot",
    };
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        {
          ...kobra,
          ha_settings: { ...kobra.ha_settings, job: { ...kobra.ha_settings.job, ...slots } },
        },
      ],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device .slots"))).toBe(
      "sensor.ace_slot_1 sensor.ace_slot_2 Colour from color_hex Loaded slot sensor.ace_loaded_slot",
    );
  });

  it("names the price entity of a dynamic tariff", async () => {
    const [kobra] = recorded.devices;
    const price = { attribute: "current", unit: "ct/kWh", factor: null };
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        {
          ...kobra,
          ha_settings: {
            ...kobra.ha_settings,
            price: { ...price, source: "entity", entity_id: "sensor.electricity_price" },
          },
        },
      ],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device dl"))).toContain(
      "Electricity price From sensor.electricity_price · current",
    );
  });

  it("names the entity of a measured consumption source", async () => {
    const [kobra] = recorded.devices;
    const meter = { attribute: null, unit: "kWh", factor: null };
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        {
          ...kobra,
          ha_settings: {
            ...kobra.ha_settings,
            consumption: { ...meter, source: "energy", entity_id: "sensor.plug_energy" },
          },
        },
        {
          ...kobra,
          id: "device-mini",
          name: "Mini",
          ha_settings: {
            ...kobra.ha_settings,
            consumption: {
              ...meter,
              source: "power",
              entity_id: "sensor.plug",
              attribute: "power",
              running_power: 60,
            },
          },
        },
      ],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device .consumption").map(text)).toEqual([
      "Energy meter sensor.plug_energy",
      "Power sensor sensor.plug · power · 60 W running",
    ]);
  });

  it("shows no card for a removed Device", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/devices" });

    expect(text(panel)).not.toContain("Mini");
  });

  it("says when there are no Devices yet", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(panel)).toContain("No Devices yet.");
  });

  it("adds a Device from the floating button on the integration's page in HA", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/devices" });

    await click(panel, query(panel, "ha-button.new-device.fab"));

    expect(location.pathname).toBe("/config/integrations/integration/coinop");
  });

  it("says when the Devices can't be loaded", async () => {
    const backend = recordedBackend().reply(LIST, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(panel)).toContain("Coin-op could not load its Devices.");
  });

  it("shows a washing machine without the printer-only parts", async () => {
    const [kobra] = recorded.devices;
    const backend = recordedBackend()
      .reply(LIST, () => ({ devices: [kobra, recorded.washer] }))
      .subscription("coinop/catalog/subscribe", () => [
        { ...recorded.catalog.filled, materials: recorded.laundry },
      ]);

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device-type h2").map(text)).toEqual([
      "3D printers",
      "Washing machines",
    ]);
    expect(cards(panel)[1]).toBe(
      "Washer " +
        "Status sensor.washer_status " +
        "Program sensor.washer_program " +
        "Consumption source Energy meter sensor.washer_plug_energy " +
        "Electricity price €0.30 per kWh " +
        "Water source None " +
        "Reconfigure in Home Assistant " +
        "Doses Liquid detergent 75 ml · measured by sensor.detergent_scale Colour pods Not dosed " +
        "Program rows Wool " +
        "Tags for new Runs None " +
        "Automatic templates None",
    );
    await click(panel, iconButton(panel, "Edit settings of Washer"));
    const dialog = query(panel, ".settings-dialog");
    expect(queryAll(dialog, ".default-material")).toHaveLength(0);
    expect(queryAll(dialog, ".new-run-tags, .automatic-templates")).toHaveLength(2);
  });

  // A recorded Device of each Device Type: its name, then its heading in English and German.
  const HEADINGS = [
    [recorded.washer, "Washer", "Washing machines", "Waschmaschinen"],
    [recorded.dishwasher, "Dishwasher", "Dishwashers", "Spülmaschinen"],
    [recorded.tumbleDryer, "Tumble dryer", "Tumble dryers", "Trockner"],
    [recorded.oven, "Oven", "Ovens", "Backöfen"],
    [recorded.coffeeMachine, "Coffee machine", "Coffee machines", "Kaffeemaschinen"],
    [recorded.wallbox, "Wallbox", "EV chargers", "Wallboxen"],
    [recorded.mower, "Mower", "Robotic mowers", "Mähroboter"],
  ] as const;

  it.each([
    ["en", 2],
    ["de", 3],
  ] as const)(
    "lists each Device under its Device Type's heading (%s)",
    async (language, column) => {
      const backend = recordedBackend({ language }).reply(LIST, () => ({
        devices: HEADINGS.map(([device]) => device),
      }));

      const panel = await mountPanel(backend, { path: "/devices" });

      expect(
        queryAll(panel, ".device-type").map((section) => [
          text(query(section, "h2")),
          ...queryAll(section, ".device h3").map(text),
        ]),
      ).toEqual(HEADINGS.map((row) => [row[column], row[1]]));
    },
  );

  it.each(["en", "de"] as const)(
    "lists Other Devices under their Type Name, one heading for each (%s)",
    async (language) => {
      const backend = recordedBackend({ language }).reply(LIST, () => ({
        devices: [recorded.wallbox, ...recorded.others, recorded.mower],
      }));

      const panel = await mountPanel(backend, { path: "/devices" });

      expect(
        queryAll(panel, ".device-type").map((section) => [
          text(query(section, "h2")),
          ...queryAll(section, ".device h3").map(text),
        ]),
      ).toEqual([
        [language === "en" ? "EV chargers" : "Wallboxen", "Wallbox"],
        ["Kiln", "Kiln"],
        ["Pump", "Pool pump", "Pond pump"],
        [language === "en" ? "Robotic mowers" : "Mähroboter", "Mower"],
      ]);
    },
  );

  it("keeps a Type Name that reads like a Device Type's heading a group of its own", async () => {
    const [kiln, pump] = recorded.others;
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [
        recorded.mower,
        { ...kiln, type_name: "Robotic mowers" },
        { ...pump, type_name: "other" },
        { ...recorded.mower, id: "device-second-mower", name: "Second mower" },
      ],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(
      queryAll(panel, ".device-type").map((section) => [
        text(query(section, "h2")),
        ...queryAll(section, ".device h3").map(text),
      ]),
    ).toEqual([
      ["Robotic mowers", "Mower", "Second mower"],
      ["Robotic mowers", "Kiln"],
      ["other", "Pool pump"],
    ]);
  });

  it("shows an Other Device that has nothing with what every Device has", async () => {
    const [kiln] = recorded.others;
    const backend = recordedBackend().reply(LIST, () => ({ devices: [kiln] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Kiln " +
        "Status sensor.kiln_status " +
        "Consumption source Estimate from average power 2,000 W running " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
    await click(panel, iconButton(panel, "Edit settings of Kiln"));
    expect(queryAll(panel, ".settings-dialog .field .label").map(text)).toEqual([
      "Tags for new Runs",
      "Automatic templates",
    ]);
  });

  it("shows a dishwasher with a washing machine's parts", async () => {
    const backend = recordedBackend()
      .reply(LIST, () => ({ devices: [recorded.dishwasher] }))
      .subscription("coinop/catalog/subscribe", () => [
        { ...recorded.catalog.filled, materials: recorded.dishwasherAndBeverage },
      ]);

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Dishwasher " +
        "Status sensor.washer_status " +
        "Program sensor.washer_program " +
        "Consumption source Energy meter sensor.washer_plug_energy " +
        "Electricity price €0.30 per kWh " +
        "Water source Per Program (litres in the Program Defaults) " +
        "Water price €4.00 per m³ " +
        "Reconfigure in Home Assistant " +
        "Doses All-in-one tabs 1 pcs " +
        "Program rows Eco 50° " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("shows a robotic mower, a Device without Capabilities, with what every Device has", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [recorded.mower] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Mower " +
        "Status sensor.mower_status " +
        "Consumption source Energy meter sensor.mower_station_energy " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
    await click(panel, iconButton(panel, "Edit settings of Mower"));
    const dialog = query(panel, ".settings-dialog");
    expect(queryAll(dialog, ".field .label").map(text)).toEqual([
      "Tags for new Runs",
      "Automatic templates",
    ]);
    expect(queryAll(dialog, "table")).toEqual([]);
    expect(backend.calls.map((call) => call.type)).not.toContain(
      "coinop/devices/measured_suggestions",
    );
  });

  it("shows an EV charger without Dose list, Program rows or water", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [recorded.wallbox] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Wallbox " +
        "Status sensor.wallbox_status " +
        "Consumption source Energy meter sensor.wallbox_session_energy " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("names a washing machine's water source and water price, or its unused Program input", async () => {
    const { perProgram } = recorded;
    const water = { attribute: "total", unit: "L", factor: null };
    const metered = {
      ...perProgram,
      id: "device-metered",
      name: "Metered",
      ha_settings: {
        ...perProgram.ha_settings,
        program: { entity_id: null, attribute: null },
        water: { ...water, source: "meter", entity_id: "sensor.washer_water" },
        water_price: {
          source: "entity",
          entity_id: "sensor.water_price",
          attribute: null,
          unit: null,
          factor: null,
        },
      },
    } satisfies typeof perProgram;
    const backend = recordedBackend().reply(LIST, () => ({ devices: [perProgram, metered] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device > dl:not(.settings)").map(text)).toEqual([
      "Status sensor.washer_status " +
        "Program sensor.washer_program " +
        "Consumption source Per Program (kWh in the Program Defaults) " +
        "Electricity price €0.30 per kWh " +
        "Water source Per Program (litres in the Program Defaults) " +
        "Water price €4.00 per m³",
      "Status sensor.washer_status " +
        "Not used Program " +
        "Consumption source Per Program (kWh in the Program Defaults) " +
        "Electricity price €0.30 per kWh " +
        "Water source Water meter sensor.washer_water · total " +
        "Water price From sensor.water_price",
    ]);
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/devices" });

    expect(text(query(panel, ".device dl"))).toBe(
      "Status sensor.kobra_status " +
        "Auftragsname sensor.kobra_job " +
        "Materialverbrauch sensor.kobra_filament_used · mm " +
        "Nicht verwendet Fächer, Vorschaubild, Kamera " +
        "Verbrauchsquelle Aus Durchschnittsleistung schätzen 120 W im Betrieb · 8 W in Pause " +
        "Strompreis 0,30 € pro kWh",
    );
  });
});

describe("Runs of removed Devices", () => {
  it("are marked as removed in the gallery and on their page", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Mini (removed) · Jan 14, 2026 · 30 min Cancelled €0.07",
    );
    await click(panel, queryAll(panel, ".tile")[0]);
    expect(text(query(panel, ".runbar"))).toContain("Mini (removed)");
  });

  it("can be filtered by in the gallery, like any Device", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/runs" });
    const options = queryAll(panel, "select.device-filter option").map(text);
    expect(options).toEqual(["All Devices", "Kobra", "Mini (removed)"]);

    await filterBy(panel, "device-mini");

    expect(tiles(panel)).toEqual([
      "No image Untitled Run Mini (removed) · Jan 14, 2026 · 30 min Cancelled €0.07",
    ]);
    expect(text(query(panel, "coinop-run-list .head"))).toBe("1 Run · €0.07");
    await filterBy(panel, "device-kobra");
    expect(tiles(panel).map((tile) => tile.split(" · ")[0])).toEqual([
      "⚑ 2 Helmet Kobra",
      "Benchy Kobra",
    ]);
    await filterBy(panel, "");
    expect(tiles(panel)).toHaveLength(3);
  });

  it("are not confused with Runs of a Device added while the panel is open", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [] }));
    const panel = await mountPanel(backend);
    backend.reply(LIST, () => ({ devices: recorded.devices }));

    backend.push(SUBSCRIBE, started);
    await settle(panel);

    expect(tiles(panel)[0]).toContain("Untitled Run Kobra ·");
  });
});

describe("A Device's settings dialog", () => {
  const SETTINGS = "coinop/devices/update_settings";
  const open = (panel: Element) => click(panel, iconButton(panel, "Edit settings of Kobra"));

  it("is titled after the Device and points to HA for its other settings", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/devices" });
    await open(panel);

    const dialog = query(panel, ".settings-dialog") as HTMLElement & { label: string };
    expect(dialog.label).toBe("Settings of Kobra");
    expect(text(query(dialog, ".ha-settings"))).toBe(
      "Device Inputs, consumption source and price are changed in Home Assistant. " +
        "Reconfigure in Home Assistant",
    );
  });

  it("closes without saving when nothing changed or on Cancel", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/devices" });

    await open(panel);
    await click(panel, query(panel, ".settings-dialog ha-button.save"));
    expect(queryAll(panel, ".settings-dialog")).toEqual([]);
    await open(panel);
    await click(panel, iconButton(panel, "Remove Wear Kobra"));
    await click(panel, query(panel, ".settings-dialog ha-button.cancel"));

    expect(queryAll(panel, ".settings-dialog")).toEqual([]);
    expect(backend.sent(SETTINGS)).toEqual([]);
    expect(text(query(panel, ".device .automatic-templates"))).toBe("Wear Kobra");
  });
});

describe("A washing machine's Doses", () => {
  const SETTINGS = "coinop/devices/update_settings";
  const [kobra] = recorded.devices;
  const whitener = {
    ...recorded.laundry[0],
    id: "material-whitener",
    name: "Whitener",
    price: { source: "fixed", pack_price: 4, pack_size: 1000, pack_unit: "g" },
  } as Material;
  const washerBackend = () => {
    const backend = recordedBackend()
      .reply(LIST, () => ({ devices: [kobra, recorded.washer] }))
      .subscription("coinop/catalog/subscribe", () => [
        {
          ...recorded.catalog.filled,
          materials: [...recorded.catalog.filled.materials, ...recorded.laundry, whitener],
        },
      ])
      .reply(SETTINGS, (msg) => ({
        settings: { ...recorded.washer.settings, ...(msg.settings as object) },
      }));
    backend.hass.states = {
      "sensor.washer_power": {
        attributes: { friendly_name: "Washer power", unit_of_measurement: "W" },
      },
      "sensor.softener_tank": {
        attributes: { friendly_name: "Softener tank", unit_of_measurement: "L", level: 0.4 },
      },
      "sensor.detergent_scale": {
        attributes: { friendly_name: "Detergent scale", unit_of_measurement: "g", model: "X1" },
      },
    };
    return backend;
  };
  const open = (panel: Element) => click(panel, iconButton(panel, "Edit settings of Washer"));
  const doses = (root: Element) => queryAll(root, ".doses li .dose-name").map(text);
  const amount = (root: Element, dose: string) =>
    query(root, `input[aria-label="Default amount of ${dose}"]`) as HTMLInputElement;
  const stockInput = (root: Element, dose: string, part = "Stock input") =>
    root.querySelector<HTMLSelectElement>(`select[aria-label="${part} of ${dose}"]`);

  it("shows the Doses on the card with their Default amounts and stock inputs", async () => {
    const panel = await mountPanel(washerBackend(), { path: "/devices" });

    const washer = queryAll(panel, ".device")[1] as HTMLElement;
    expect(text(query(washer, ".doses"))).toBe(
      "Liquid detergent 75 ml · measured by Detergent scale Colour pods Not dosed",
    );
    expect(queryAll(panel, ".device")[0]?.querySelector(".doses")).toBeNull();
  });

  it("measure a Dose in g or ml by a stock input with a mass or volume unit", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    await open(panel);
    const dialog = query(panel, ".settings-dialog");
    const detergent = stockInput(dialog, "Liquid detergent") as HTMLSelectElement;
    expect(detergent.value).toBe("sensor.detergent_scale");
    expect(queryAll(detergent, "option").map(text)).toEqual([
      "No stock input",
      "Detergent scale",
      "Softener tank",
    ]);
    expect(stockInput(dialog, "Colour pods")).toBeNull();
    expect(stockInput(dialog, "Liquid detergent", "Stock unit")).toBeNull();

    await fill(panel, detergent, "");
    await fill(panel, query(dialog, ".doses > select"), "material-whitener");
    await fill(panel, stockInput(dialog, "Whitener") as HTMLSelectElement, "sensor.softener_tank");
    const attribute = stockInput(dialog, "Whitener", "Stock attribute") as HTMLSelectElement;
    expect(queryAll(attribute, "option").map(text)).toEqual(["State", "level"]);
    await fill(panel, attribute, "level");
    const unit = stockInput(dialog, "Whitener", "Stock unit") as HTMLSelectElement;
    expect(unit.value).toBe("g");
    await fill(panel, unit, "L");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      doses: [
        { id: "dose-detergent", material_id: "material-detergent" },
        { id: "dose-pods", material_id: "material-pods" },
        {
          id: expect.any(String),
          material_id: "material-whitener",
          stock: { entity_id: "sensor.softener_tank", attribute: "level", unit: "L" },
        },
      ],
    });
    expect(text(query(queryAll(panel, ".device")[1] as HTMLElement, ".doses"))).toBe(
      "Liquid detergent 75 ml Colour pods Not dosed Whitener Not dosed · measured by Softener tank",
    );
  });

  it("are added, reordered and removed in the settings dialog", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    await open(panel);
    const dialog = query(panel, ".settings-dialog");
    expect(doses(dialog)).toEqual(["Liquid detergent", "Colour pods"]);
    const picker = query(dialog, ".doses > select") as HTMLSelectElement;
    expect(queryAll(picker, "option").map(text)).toContain("Whitener");

    await fill(panel, picker, "material-whitener");
    await click(panel, iconButton(dialog, "Move Whitener up"));
    await click(panel, iconButton(dialog, "Remove Colour pods"));
    expect(doses(dialog)).toEqual(["Liquid detergent", "Whitener"]);
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      doses: [
        {
          id: "dose-detergent",
          material_id: "material-detergent",
          stock: { entity_id: "sensor.detergent_scale", attribute: null, unit: null },
        },
        { id: expect.any(String), material_id: "material-whitener" },
      ],
    });
  });

  it("are named as Materials, with a way to the Materials tab", async () => {
    const panel = await mountPanel(washerBackend(), { path: "/devices" });
    await open(panel);
    const dialog = query(panel, ".settings-dialog");
    expect(text(query(dialog, ".doses > select option"))).toBe("+ Add a Material as a Dose");
    expect(text(query(dialog, ".doses .hint"))).toContain("a Material from the Materials tab");
    expect(query(dialog, ".doses .hint a").getAttribute("href")).toBe("/coinop/materials");
  });

  it("are dosed by the Default row of the Program Defaults", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    await open(panel);
    const dialog = query(panel, ".settings-dialog");
    expect(text(query(dialog, ".program-defaults thead"))).toBe(
      "Program Electricity (kWh) Liquid detergent (ml) Colour pods (pcs)",
    );
    expect(amount(dialog, "Liquid detergent").value).toBe("75");
    expect(amount(dialog, "Colour pods").value).toBe("");

    await fill(panel, amount(dialog, "Liquid detergent"), "");
    await fill(panel, amount(dialog, "Colour pods"), "1");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([
      {
        type: SETTINGS,
        device_id: "device-washer",
        settings: {
          program_defaults: {
            default: { doses: { "dose-pods": 1 } },
            programs: { Wool: { doses: { "dose-detergent": 40 } } },
          },
        },
      },
    ]);
    expect(text(query(queryAll(panel, ".device")[1] as HTMLElement, ".doses"))).toBe(
      "Liquid detergent Not dosed · measured by Detergent scale Colour pods 1 pcs",
    );
  });

  it("dose a new Dose in the same save", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    await open(panel);
    const dialog = query(panel, ".settings-dialog");

    await fill(panel, query(dialog, ".doses > select"), "material-whitener");
    await fill(panel, amount(dialog, "Whitener"), "20");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    const settings = sent?.settings as typeof recorded.washer.settings;
    const added = settings.doses[2]?.id ?? "";
    expect(settings.program_defaults.default.doses).toEqual({
      "dose-detergent": 75,
      [added]: 20,
    });
  });
});

describe("A washing machine's Program rows", () => {
  const SETTINGS = "coinop/devices/update_settings";
  const [kobra] = recorded.devices;
  const washerBackend = () =>
    recordedBackend()
      .reply(LIST, () => ({ devices: [kobra, recorded.washer] }))
      .subscription("coinop/catalog/subscribe", () => [
        {
          ...recorded.catalog.filled,
          materials: [...recorded.catalog.filled.materials, ...recorded.laundry],
        },
      ])
      .reply(SETTINGS, (msg) => ({
        settings: { ...recorded.washer.settings, ...(msg.settings as object) },
      }));
  const openDialog = async (panel: Element) => {
    await click(panel, iconButton(panel, "Edit settings of Washer"));
    return query(panel, ".settings-dialog");
  };
  const rows = (dialog: Element) => queryAll(dialog, ".program-defaults tbody tr").map(text);
  const amount = (root: Element, dose: string, program: string) =>
    query(root, `input[aria-label="${dose} for ${program}"]`) as HTMLInputElement;

  it("are suggested from the known Programs and stored once a value is entered", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);
    expect(rows(dialog)).toEqual([
      "Default",
      "Cotton 60° Suggested",
      "Wool",
      "Eco 40-60 Suggested",
    ]);
    expect(amount(dialog, "Liquid detergent", "Wool").value).toBe("40");
    expect(amount(dialog, "Liquid detergent", "Cotton 60°").value).toBe("");

    await fill(panel, amount(dialog, "Colour pods", "Eco 40-60"), "1");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: { "dose-detergent": 75 } },
        programs: {
          Wool: { doses: { "dose-detergent": 40 } },
          "Eco 40-60": { doses: { "dose-pods": 1 } },
        },
      },
    });
  });

  it("store nothing for a suggestion that stays empty", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    await fill(panel, amount(dialog, "Colour pods", "Cotton 60°"), "");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([]);
  });

  it("are added and removed by hand", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    await fill(panel, query(dialog, ".program-defaults > input"), " Rinse ");
    await click(panel, iconButton(dialog, "Remove the row of Wool"));
    expect(rows(dialog)).toEqual([
      "Default",
      "Cotton 60° Suggested",
      "Wool Suggested",
      "Eco 40-60 Suggested",
      "Rinse",
    ]);
    expect((query(dialog, ".program-defaults > input") as HTMLInputElement).value).toBe("");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: { "dose-detergent": 75 } },
        programs: { Rinse: { doses: {} } },
      },
    });
    expect(text(query(queryAll(panel, ".device")[1] as HTMLElement, ".program-rows"))).toBe(
      "Rinse",
    );
  });

  it("lose a removed Dose's amounts", async () => {
    const backend = washerBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    await click(panel, iconButton(dialog, "Remove Liquid detergent"));
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      doses: [{ id: "dose-pods", material_id: "material-pods" }],
      program_defaults: { default: { doses: {} }, programs: { Wool: { doses: {} } } },
    });
  });

  it("are listed on the card", async () => {
    const panel = await mountPanel(washerBackend(), { path: "/devices" });

    const washer = queryAll(panel, ".device")[1] as HTMLElement;
    expect(text(query(washer, ".program-rows"))).toBe("Wool");
    expect(queryAll(panel, ".device")[0]?.querySelector(".program-rows")).toBeNull();
  });

  const SUGGESTIONS = "coinop/devices/measured_suggestions";
  const suggesting = () =>
    washerBackend().reply(SUGGESTIONS, () => ({ suggestions: recorded.measuredSuggestions }));
  const cell = (dialog: Element, label: string) =>
    query(dialog, `input[aria-label="${label}"]`).closest("td") as HTMLElement;

  it("show the mean kWh of measured Runs beside the cells that have one", async () => {
    const backend = suggesting();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    expect(backend.sent(SUGGESTIONS)).toEqual([{ type: SUGGESTIONS, device_id: "device-washer" }]);
    expect(text(query(cell(dialog, "Default kWh"), ".suggestion"))).toBe("Ø 1.2 kWh · 1 Run");
    expect(text(query(cell(dialog, "kWh for Cotton 60°"), ".suggestion"))).toBe(
      "Ø 1.2 kWh · 1 Run",
    );
    expect(cell(dialog, "kWh for Wool").querySelector(".suggestion")).toBeNull();
    expect(
      (query(dialog, 'input[aria-label="kWh for Cotton 60°"]') as HTMLInputElement).value,
    ).toBe("");
  });

  it("apply a measured suggestion with a click, stored on save", async () => {
    const backend = suggesting();
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    await click(panel, query(cell(dialog, "kWh for Cotton 60°"), ".suggestion"));
    expect(
      (query(dialog, 'input[aria-label="kWh for Cotton 60°"]') as HTMLInputElement).value,
    ).toBe("1.2");
    await click(panel, query(dialog, "ha-button.save"));

    const [sent] = backend.sent(SETTINGS);
    expect(sent?.settings).toEqual({
      program_defaults: {
        default: { doses: { "dose-detergent": 75 } },
        programs: {
          Wool: { doses: { "dose-detergent": 40 } },
          "Cotton 60°": { doses: {}, kwh: 1.2 },
        },
      },
    });
  });

  it("go without measured suggestions when they can't be had", async () => {
    const backend = washerBackend().reply(SUGGESTIONS, () => {
      throw new WsError("not_found");
    });
    const panel = await mountPanel(backend, { path: "/devices" });
    const dialog = await openDialog(panel);

    expect(queryAll(dialog, ".suggestion")).toEqual([]);
    expect(rows(dialog)[0]).toBe("Default");
  });
});

describe("Device settings without a catalogue", () => {
  it("link to the Materials and Line Item Templates tabs instead of empty selects", async () => {
    const backend = recordedBackend().subscription("coinop/catalog/subscribe", () => [
      recorded.catalog.empty,
    ]);

    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Kobra"));

    expect(queryAll(panel, ".default-material select")).toEqual([]);
    expect(query(panel, ".no-materials a").getAttribute("href")).toBe("/coinop/materials");
    expect(queryAll(panel, ".automatic-templates select")).toEqual([]);
    expect(query(panel, ".no-templates a").getAttribute("href")).toBe("/coinop/templates");
  });
});
