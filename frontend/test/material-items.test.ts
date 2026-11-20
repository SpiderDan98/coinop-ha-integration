import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { change, click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const UPDATE = "coinop/line_items/update";
const ADD = "coinop/line_items/add";
const SETTINGS = "coinop/devices/update_settings";
const [started] = recorded.changes;

const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);
const picker = (row: HTMLElement) => query(row, "select[name=material_id]") as HTMLSelectElement;
const options = (select: HTMLElement) => queryAll(select, "option").map(text);

describe("Material Line Items", () => {
  it("show the measured length and how it became grams", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    const pla = item(panel, "benchy-pla");
    expect(text(query(pla, ".evidence"))).toBe("4,191 mm at 1.75 mm and 1.24 g/cm³");
    expect(picker(pla).value).toBe("pla-black");
    expect(text(query(pla, ".unit"))).toBe("g");
    expect(queryAll(pla, "input[name=unit], input[name=label]")).toHaveLength(0);
  });

  it("pick a Material from the current ones and are re-priced by the backend", async () => {
    const backend = recordedBackend().reply(UPDATE, () => recorded.lineItemsMaterial);
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    const filament = item(panel, "helmet-filament");
    expect(options(picker(filament))).toEqual([
      "No Material",
      "eSun PLA+ black",
      "Standard Resin grey",
    ]);
    expect(text(query(filament, ".evidence"))).toBe(
      "30,000 mm measured; pick a Material to weigh it",
    );

    await change(panel, picker(filament), "material-1");

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        run_id: "helmet",
        line_item_id: "helmet-filament",
        material_id: "material-1",
      },
    ]);
    const priced = item(panel, "helmet-filament");
    expect(text(query(priced, ".evidence"))).toBe("30,000 mm at 1.75 mm and 1.27 g/cm³");
    expect((query(priced, "[name=quantity]") as HTMLInputElement).value).toBe("91.6412");
    const [, material] = queryAll(panel, ".kind .between").map(text);
    expect(material).toBe("Material €2.75");
  });

  it("stay locked while the Run is open", async () => {
    const backend = recordedBackend().subscription("coinop/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });

    const material = item(panel, "print-live-material");
    expect(material.classList.contains("locked")).toBe(true);
    expect(picker(material).disabled).toBe(true);
    expect(text(query(material, ".evidence"))).toBe("1,500 mm at 1.75 mm and 1.24 g/cm³");
    expect(queryAll(panel, "ha-button.add-material")).toHaveLength(1);
  });

  it("are added by hand as a Material plus grams or millilitres", async () => {
    const backend = recordedBackend().reply(ADD, () => recorded.lineItemsAddMaterial);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await click(panel, query(panel, "ha-button.add-material"));
    const form = query(panel, ".add-item form");
    expect(options(query(form, "select[name=material_id]"))).toEqual([
      "eSun PLA+ black",
      "Standard Resin grey",
    ]);
    await fill(panel, query(form, "select[name=material_id]"), "material-2");
    await fill(panel, query(form, "[name=quantity]"), "25");
    await fill(panel, query(form, "select[name=unit]"), "ml");
    await click(panel, query(form, "ha-button[type=submit]"));

    expect(backend.sent(ADD)).toEqual([
      {
        type: ADD,
        run_id: "benchy",
        kind: "material",
        material_id: "material-2",
        quantity: 25,
        unit: "ml",
      },
    ]);
    expect(queryAll(panel, ".add-item form")).toHaveLength(0);
    expect(picker(item(panel, "benchy-petg")).value).toBe("petg-white");
  });
});

describe("Default Material", () => {
  it("is picked per Device from the current Materials, or none", async () => {
    const [kobra] = recorded.devices;
    const backend = recordedBackend().reply(SETTINGS, (msg) => ({
      settings: { ...kobra.settings, ...(msg.settings as object) },
    }));
    const panel = await mountPanel(backend, { path: "/devices" });
    // "pla-black" is not in this catalogue, so no default applies.
    expect(text(query(panel, ".device .default-material"))).toBe("None");
    await click(panel, iconButton(panel, "Edit settings of Kobra"));
    const select = query(panel, ".settings-dialog .default-material select") as HTMLSelectElement;
    expect(options(select)).toEqual(["None", "eSun PLA+ black", "Standard Resin grey"]);
    expect(select.value).toBe("");

    await fill(panel, select, "material-1");
    await click(panel, query(panel, ".settings-dialog ha-button.save"));
    expect(text(query(panel, ".device .default-material"))).toBe("eSun PLA+ black");
    await click(panel, iconButton(panel, "Edit settings of Kobra"));
    await fill(panel, query(panel, ".settings-dialog .default-material select"), "");
    await click(panel, query(panel, ".settings-dialog ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([
      { type: SETTINGS, device_id: "device-kobra", settings: { default_material: "material-1" } },
      { type: SETTINGS, device_id: "device-kobra", settings: { default_material: null } },
    ]);
  });
});

describe("A new Material Line Item", () => {
  it("counts g or ml by the Material's form", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });
    await click(panel, query(panel, "ha-button.add-material"));
    const form = query(panel, ".add-item form");
    expect((query(form, "select[name=unit]") as HTMLSelectElement).value).toBe("g");

    await fill(panel, query(form, "select[name=material_id]"), "material-2");

    expect((query(form, "select[name=unit]") as HTMLSelectElement).value).toBe("ml");
  });

  it("counts pieces of a Material bought by the piece", async () => {
    const backend = recordedBackend()
      .subscription("coinop/catalog/subscribe", () => [
        { ...recorded.catalog.filled, materials: recorded.laundry },
      ])
      .reply(ADD, () => recorded.lineItemsAddMaterial);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    await click(panel, query(panel, "ha-button.add-material"));
    const form = query(panel, ".add-item form");
    expect((query(form, "select[name=unit]") as HTMLSelectElement).value).toBe("ml");

    await fill(panel, query(form, "select[name=material_id]"), "material-pods");
    expect(options(query(form, "select[name=unit]"))).toEqual(["pcs"]);
    await fill(panel, query(form, "[name=quantity]"), "2");
    await click(panel, query(form, "ha-button[type=submit]"));

    expect(backend.sent(ADD)).toEqual([
      {
        type: ADD,
        run_id: "benchy",
        kind: "material",
        material_id: "material-pods",
        quantity: 2,
        unit: "pcs",
      },
    ]);
  });

  it("points to the Materials tab while there are no Materials", async () => {
    const backend = recordedBackend().subscription("coinop/catalog/subscribe", () => [
      recorded.catalog.empty,
    ]);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await click(panel, query(panel, "ha-button.add-material"));

    expect(queryAll(panel, ".add-item form")).toEqual([]);
    expect(text(query(panel, ".no-materials"))).toContain(
      "A Material Line Item needs a Material from the catalogue.",
    );
    expect(query(panel, ".no-materials a").getAttribute("href")).toBe("/coinop/materials");
  });
});
