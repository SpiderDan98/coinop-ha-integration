import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const UPDATE = "coinop/line_items/update";
const ADD = "coinop/line_items/add";
const SETTINGS = "coinop/devices/update_settings";
const [started] = recorded.changes;

const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);
const field = (dialog: HTMLElement, name: string) =>
  query(dialog, `[name=${name}]`) as HTMLSelectElement;
const options = (select: HTMLElement) => queryAll(select, "option").map(text);
const edit = async (panel: Element, id: string) => {
  await click(panel, query(item(panel, id), "ha-icon-button.edit"));
  return query(panel, ".item-dialog");
};
const add = async (panel: Element) => {
  await click(panel, query(panel, "ha-button.add-material"));
  return query(panel, ".new-item-dialog");
};
const save = (panel: Element) => click(panel, query(panel, ".dialog ha-button.save"));

describe("Material Line Items", () => {
  it("show the measured length and how it became grams", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    const pla = item(panel, "benchy-pla");
    expect(text(query(pla, ".name"))).toBe("PLA Basic Black");
    expect(text(query(pla, ".evidence"))).toBe("4,191 mm at 1.75 mm and 1.24 g/cm³");
    expect(text(query(pla, ".quantity"))).toBe("12.5 g");
    const dialog = await edit(panel, "benchy-pla");
    expect(field(dialog, "material_id").value).toBe("pla-black");
    expect(queryAll(dialog, ".with-unit .unit").map(text)).toEqual(["g", "€/g", "€"]);
    expect(queryAll(dialog, "[name=unit], [name=label]")).toHaveLength(0);
  });

  it("pick a Material from the current ones and are re-priced by the backend", async () => {
    const backend = recordedBackend().reply(UPDATE, () => recorded.lineItemsMaterial);
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    const filament = item(panel, "helmet-filament");
    expect(text(query(filament, ".name"))).toBe("No Material");
    expect(text(query(filament, ".evidence"))).toBe(
      "30,000 mm measured; pick a Material to weigh it",
    );
    const dialog = await edit(panel, "helmet-filament");
    expect(options(field(dialog, "material_id"))).toEqual([
      "No Material",
      "eSun PLA+ black",
      "Standard Resin grey",
    ]);

    await fill(panel, field(dialog, "material_id"), "material-1");
    expect(backend.sent(UPDATE)).toEqual([]);
    await save(panel);

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
    expect(text(query(priced, ".quantity"))).toBe("91.6 g");
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
    expect(queryAll(material, "ha-icon-button.edit")).toHaveLength(0);
    expect(text(query(material, ".evidence"))).toBe("1,500 mm at 1.75 mm and 1.24 g/cm³");
    expect(queryAll(panel, "ha-button.add-material")).toHaveLength(1);
  });

  it("are added by hand as a Material plus grams or millilitres", async () => {
    const backend = recordedBackend().reply(ADD, () => recorded.lineItemsAddMaterial);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    const dialog = await add(panel);
    expect(text(query(dialog, "h2"))).toBe("Add Material Line Item");
    expect(options(field(dialog, "material_id"))).toEqual([
      "eSun PLA+ black",
      "Standard Resin grey",
    ]);
    await fill(panel, field(dialog, "material_id"), "material-2");
    await fill(panel, field(dialog, "quantity"), "25");
    await fill(panel, field(dialog, "unit"), "ml");
    await save(panel);

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
    expect(queryAll(panel, ".new-item-dialog")).toHaveLength(0);
    expect(text(query(item(panel, "benchy-petg"), ".name"))).toBe("PETG White");
  });

  it("are not added without a quantity", async () => {
    const backend = recordedBackend().reply(ADD, () => recorded.lineItemsAddMaterial);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    const dialog = await add(panel);
    await save(panel);

    expect(backend.sent(ADD)).toEqual([]);
    expect(field(dialog, "quantity").getAttribute("aria-invalid")).toBe("true");
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
    const dialog = await add(panel);
    expect(field(dialog, "unit").value).toBe("g");

    await fill(panel, field(dialog, "material_id"), "material-2");

    expect(field(dialog, "unit").value).toBe("ml");
  });

  it("counts pieces of a Material bought by the piece", async () => {
    const backend = recordedBackend()
      .subscription("coinop/catalog/subscribe", () => [
        { ...recorded.catalog.filled, materials: recorded.laundry },
      ])
      .reply(ADD, () => recorded.lineItemsAddMaterial);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await add(panel);
    expect(field(dialog, "unit").value).toBe("ml");

    await fill(panel, field(dialog, "material_id"), "material-pods");
    expect(options(field(dialog, "unit"))).toEqual(["pcs"]);
    await fill(panel, field(dialog, "quantity"), "2");
    await save(panel);

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

    const dialog = await add(panel);

    expect(queryAll(dialog, "input, select")).toEqual([]);
    expect(text(query(dialog, ".no-materials"))).toContain(
      "A Material Line Item needs a Material from the catalogue.",
    );
    expect(query(dialog, ".no-materials a").getAttribute("href")).toBe("/coinop/materials");
    expect(query(dialog, "ha-button.save").hasAttribute("disabled")).toBe(true);
  });
});
