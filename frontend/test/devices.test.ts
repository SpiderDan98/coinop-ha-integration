import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "wattbill/runs/subscribe";
const LIST = "wattbill/devices/list";
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

    expect(location.pathname).toBe("/wattbill/devices");
    expect(cards(panel)).toHaveLength(1);
    await click(panel, query(panel, 'a.tab[title="Runs"]'));
    expect(location.pathname).toBe("/wattbill");
  });

  it("shows each Device's HA-side settings read-only with a link to change them", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/devices" });

    expect(cards(panel)).toEqual([
      "Kobra " +
        "Print status sensor.kobra_status " +
        "Print job sensor.kobra_job " +
        "Material used sensor.kobra_filament_used mm " +
        "Not used Slots, Thumbnail, Camera " +
        "Consumption source Estimate from average power 120 W running · 8 W paused " +
        "Electricity price €0.30 per kWh " +
        "Device Inputs, consumption source and price are changed in Home Assistant. " +
        "Reconfigure in Home Assistant " +
        "Default Material None eSun PLA+ black Standard Resin grey " +
        "Charged for a Run's measured usage, and pre-filled when the printer reports none. " +
        "Tags for new Runs Batch 7 Copied onto every Run that starts on this Device. " +
        "Automatic templates Wear Kobra + Add template Threaded inserts Packaging " +
        "Added to every Run that starts on this Device. Changes affect future Runs only.",
    ]);
    expect(queryAll(panel, ".device dl input, .device dl select")).toHaveLength(0);
    expect(query(panel, ".device a").getAttribute("href")).toBe(
      "/config/integrations/integration/wattbill",
    );
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
      "Print status event.kobra_print event_type " +
        "Not used Print job, Material used, Slots, Thumbnail, Camera " +
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
      "Thumbnail image.kobra_preview Camera camera.kobra Snapshot when a Run ends Not used Slots",
    );
    on.remove();
    const off = await mountPanel(withImages(false), { path: "/devices" });
    expect(text(query(off, ".device dl"))).toContain(
      "Camera camera.kobra No Snapshot Not used Slots",
    );
  });

  it("names each input's entity by its friendly name, its entity id below", async () => {
    const backend = recordedBackend();
    backend.hass.states = {
      "sensor.kobra_status": { attributes: { friendly_name: "Kobra Print status" } },
    };

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(query(panel, ".device dd"))).toBe("Kobra Print status sensor.kobra_status");
  });

  it("names the price, consumption and Slot entities too, their entity ids below", async () => {
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

    expect(text(query(panel, ".device .slots"))).toBe(
      "ACE Slot 1 sensor.ace_slot_1 Loaded slot ACE Loaded slot sensor.ace_loaded_slot",
    );
    expect(text(query(panel, ".device .consumption"))).toBe(
      "Power sensor Plug power sensor.plug_power",
    );
    expect(text(query(panel, ".device .price"))).toBe("From Tibber price sensor.tibber_price");
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
      "Electricity price From sensor.electricity_price current",
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
      "Power sensor sensor.plug power · 60 W running",
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

    expect(location.pathname).toBe("/config/integrations/integration/wattbill");
  });

  it("says when the Devices can't be loaded", async () => {
    const backend = recordedBackend().reply(LIST, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(text(panel)).toContain("WattBill could not load its Devices.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/devices" });

    expect(text(query(panel, ".device dl"))).toBe(
      "Druckstatus sensor.kobra_status " +
        "Druckauftrag sensor.kobra_job " +
        "Materialverbrauch sensor.kobra_filament_used mm " +
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
    const panel = await mountPanel(recordedBackend());
    const options = queryAll(panel, "select.device-filter option").map(text);
    expect(options).toEqual(["All Devices", "Kobra", "Mini (removed)"]);

    await filterBy(panel, "device-mini");

    expect(tiles(panel)).toEqual([
      "No image Untitled Run Mini (removed) · Jan 14, 2026 · 30 min Cancelled €0.07",
    ]);
    expect(text(query(panel, ".head"))).toContain("1 · €0.07");
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

describe("Device settings without a catalogue", () => {
  it("link to the Materials and Line Item Templates tabs instead of empty selects", async () => {
    const backend = recordedBackend().subscription("wattbill/catalog/subscribe", () => [
      recorded.catalog.empty,
    ]);

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".default-material select")).toEqual([]);
    expect(query(panel, ".no-materials a").getAttribute("href")).toBe("/wattbill/materials");
    expect(queryAll(panel, ".automatic-templates select")).toEqual([]);
    expect(query(panel, ".no-templates a").getAttribute("href")).toBe("/wattbill/templates");
  });
});
