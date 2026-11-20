import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const CATALOG = "coinop/catalog/subscribe";
const CREATE = "coinop/materials/create";
const UPDATE = "coinop/materials/update";
const DELETE = "coinop/materials/delete";
const DIALOG = ".material-dialog";
const rows = (panel: Element, selector = ".active tr.material") =>
  queryAll(panel, selector).map(text);
const field = (panel: Element, name: string) => query(panel, `${DIALOG} [name=${name}]`);
const save = (panel: Element) => click(panel, query(panel, `${DIALOG} ha-button.save`));
const marked = (panel: Element) =>
  queryAll(panel, `${DIALOG} [aria-invalid="true"]`).map((control) => control.getAttribute("name"));
const button = (root: Element, label: string) => {
  const found = queryAll(root, "ha-button, ha-icon-button, button").find(
    (candidate) => text(candidate) === label || (candidate as { label?: string }).label === label,
  );
  if (!found) throw new Error(`no button "${label}"`);
  return found;
};
const row = (panel: Element, name: string) => {
  const found = queryAll(panel, "tr.material").find((candidate) =>
    text(candidate).startsWith(name),
  );
  if (!found) throw new Error(`no row "${name}"`);
  return found;
};
const lastCall = (backend: ReturnType<typeof recordedBackend>) => backend.calls.at(-1);
const confirmDelete = async (panel: Element, name: string) => {
  await click(panel, button(row(panel, name), "Delete"));
  return query(panel, ".delete-dialog");
};

/** A backend that answers Material commands with what the real one would. */
function catalogBackend() {
  const backend = recordedBackend();
  const pla = recorded.material("material-1");
  return backend
    .reply(CREATE, (msg) => ({
      material: { ...pla, ...(msg.material as object), id: "new" },
    }))
    .reply(UPDATE, (msg) => ({
      material: { ...pla, ...(msg.material as object) },
    }))
    .reply("coinop/materials/archive", () => ({ material: { ...pla, archived: true } }))
    .reply("coinop/materials/restore", () => ({ material: pla }))
    .reply(DELETE, () => ({ deleted: true }));
}

describe("Materials tab", () => {
  it("opens from the toolbar", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/materials"]`));

    expect(location.pathname).toBe("/coinop/materials");
    expect(query(panel, "a.tab.on").title).toBe("Materials");
    expect(text(query(panel, ".page-title"))).toBe("Materials");
  });

  it("lists the catalogue with each Material's price per kg, archived ones apart", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/materials" });

    expect(rows(panel)).toEqual([
      "eSun PLA+ black eSun Filament · PLA 1.24 g/cm³ · ⌀ 1.75 mm €19.99 / 1,000 g €19.99 / kg",
      "Standard Resin grey Resin · Standard resin 1.1 g/cm³ €29.99 / 1,000 ml €27.26 / kg",
    ]);
    expect(
      queryAll(panel, ".active ha-icon-button.star").map((star) => star.hasAttribute("selected")),
    ).toEqual([true, false]);
    expect(text(query(panel, ".archived summary"))).toBe("Archived (1)");
    expect(rows(panel, ".archived tr.material")).toEqual([
      "PLA red (old brand) Filament · PLA 1.24 g/cm³ · ⌀ 1.75 mm €15.99 / 1,000 g €15.99 / kg",
    ]);
    const labels = (selector: string) =>
      queryAll(panel, `${selector} .actions ha-icon-button`).map(
        (icon) => (icon as { label?: string }).label,
      );
    expect(labels(".active tr.material:first-child")).toEqual([
      "Edit",
      "Duplicate",
      "Archive",
      "Delete",
    ]);
    expect(labels(".archived tr.material")).toEqual(["Restore", "Delete"]);
  });

  it("shows the Materials read-only", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/materials" });

    const page = query(panel, "coinop-materials-page");
    expect(rows(panel)).toHaveLength(2);
    expect(queryAll(page, "form, input, select, textarea")).toEqual([]);
    expect(queryAll(page, "coinop-dialog")).toEqual([]);
  });

  it("says when the catalogue is empty", async () => {
    const backend = recordedBackend().subscription(CATALOG, () => [recorded.catalog.empty]);

    const panel = await mountPanel(backend, { path: "/materials" });

    expect(text(panel)).toContain("No Materials yet.");
  });

  it("creates a Material with its density pre-filled from the type", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));

    await fill(panel, field(panel, "name"), "Sunlu PETG white");
    await fill(panel, field(panel, "type"), "petg");
    expect((field(panel, "density") as HTMLInputElement).value).toBe("1.27");
    await fill(panel, field(panel, "vendor"), "Sunlu");
    await fill(panel, field(panel, "colour"), "#F5F5F5");
    await fill(panel, field(panel, "pack_price"), "21.99");
    await fill(panel, field(panel, "pack_size"), "1000");
    await fill(panel, field(panel, "default_for_type"), "on");
    expect(backend.sent(CREATE)).toEqual([]);
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        material: {
          name: "Sunlu PETG white",
          form: "filament",
          type: "petg",
          density: 1.27,
          vendor: "Sunlu",
          colour: "#F5F5F5",
          diameter: 1.75,
          default_for_type: true,
          price: { source: "fixed", pack_price: 21.99, pack_size: 1000, pack_unit: "g" },
        },
      },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("opens the dialog as a modal with the name focused", async () => {
    const panel = await mountPanel(catalogBackend(), { path: "/materials" });

    await click(panel, button(panel, "New Material"));

    const dialog = query(panel, DIALOG);
    expect(text(dialog)).toContain("New Material");
    expect((query(dialog, "dialog") as HTMLDialogElement).open).toBe(true);
    expect(dialog.getRootNode()).toHaveProperty("activeElement", field(panel, "name"));
  });

  it("saves with Enter in a field", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "eSun PLA+ black"), "Edit"));
    await fill(panel, field(panel, "name"), "eSun PLA+ matt black");

    field(panel, "name").dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        composed: true,
        cancelable: true,
      }),
    );
    await settle(panel);

    expect(backend.sent(UPDATE)).toMatchObject([
      { material_id: "material-1", material: { name: "eSun PLA+ matt black" } },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("offers the built-in types and suggests resin by the millilitre", async () => {
    const panel = await mountPanel(catalogBackend(), { path: "/materials" });
    await click(panel, button(panel, "New Material"));

    await fill(panel, field(panel, "type"), "Standard resin");

    const known = query(panel, `datalist#${field(panel, "type").getAttribute("list")}`);
    const options = queryAll(known, "option").map((option) => option.getAttribute("value"));
    expect(options).toContain("PLA");
    expect((field(panel, "form") as HTMLSelectElement).value).toBe("resin");
    expect((field(panel, "pack_unit") as HTMLSelectElement).value).toBe("ml");
    expect(queryAll(panel, "[name=diameter]")).toHaveLength(0);
  });

  it("edits a Material in a dialog", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "eSun PLA+ black"), "Edit"));
    expect(text(query(panel, DIALOG))).toContain("Edit Material");
    expect((field(panel, "name") as HTMLInputElement).value).toBe("eSun PLA+ black");
    expect((field(panel, "pack_price") as HTMLInputElement).value).toBe("19.99");

    await fill(panel, field(panel, "pack_size"), "2000");
    await fill(panel, field(panel, "colour"), "");
    expect(backend.sent(UPDATE)).toEqual([]);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        material_id: "material-1",
        material: {
          name: "eSun PLA+ black",
          form: "filament",
          type: "PLA",
          density: 1.24,
          vendor: "eSun",
          colour: null,
          diameter: 1.75,
          default_for_type: true,
          price: { source: "fixed", pack_price: 19.99, pack_size: 2000, pack_unit: "g" },
        },
      },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("duplicates a Material into the dialog for a new one, not as its type's default", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "eSun PLA+ black"), "Duplicate"));
    expect(text(query(panel, DIALOG))).toContain("New Material");
    expect((field(panel, "name") as HTMLInputElement).value).toBe("eSun PLA+ black");
    expect(backend.sent(CREATE)).toEqual([]);
    await fill(panel, field(panel, "name"), "eSun PLA+ white");
    await fill(panel, field(panel, "colour"), "#FFFFFF");
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        material: {
          name: "eSun PLA+ white",
          form: "filament",
          type: "PLA",
          density: 1.24,
          vendor: "eSun",
          colour: "#FFFFFF",
          diameter: 1.75,
          default_for_type: false,
          price: { source: "fixed", pack_price: 19.99, pack_size: 1000, pack_unit: "g" },
        },
      },
    ]);
    expect(backend.sent(UPDATE)).toEqual([]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("drops what was entered on cancel", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "eSun PLA+ black"), "Edit"));
    await fill(panel, field(panel, "name"), "Renamed");
    await fill(panel, field(panel, "pack_price"), "1");

    await click(panel, query(panel, `${DIALOG} ha-button.cancel`));

    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect([...backend.sent(UPDATE), ...backend.sent(CREATE)]).toEqual([]);
    await click(panel, button(row(panel, "eSun PLA+ black"), "Edit"));
    expect((field(panel, "name") as HTMLInputElement).value).toBe("eSun PLA+ black");
    expect((field(panel, "pack_price") as HTMLInputElement).value).toBe("19.99");
  });

  it("is cancelled with Escape or the close button too", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    await fill(panel, field(panel, "name"), "PLA");

    query(panel, `${DIALOG} dialog`).dispatchEvent(new Event("cancel", { cancelable: true }));
    await settle(panel);
    expect(queryAll(panel, DIALOG)).toEqual([]);

    await click(panel, button(panel, "New Material"));
    expect((field(panel, "name") as HTMLInputElement).value).toBe("");
    await click(panel, button(query(panel, DIALOG), "Close"));
    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect(backend.sent(CREATE)).toEqual([]);
  });

  it("keeps the dialog open and says so when the backend rejects it", async () => {
    const backend = catalogBackend().reply(CREATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    await fill(panel, field(panel, "name"), "PLA");
    await fill(panel, field(panel, "type"), "PLA");
    await fill(panel, field(panel, "pack_price"), "20");

    await save(panel);

    expect(backend.sent(CREATE)).toHaveLength(1);
    expect(text(query(panel, `${DIALOG} .error`))).toContain(
      "Check the fields: name, type, density, pack price and pack size are required",
    );
    expect((field(panel, "name") as HTMLInputElement).value).toBe("PLA");
  });

  it("marks what is missing instead of saving an empty pack price as free", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    await fill(panel, field(panel, "name"), "PLA");
    await fill(panel, field(panel, "colour"), "red");

    expect(marked(panel)).toEqual([]);
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([]);
    expect(marked(panel)).toEqual(["type", "density", "colour", "pack_price"]);
    expect(text(query(panel, `${DIALOG} .error`))).toContain("Check the fields");
    await fill(panel, field(panel, "type"), "PLA");
    await fill(panel, field(panel, "colour"), "");
    await fill(panel, field(panel, "pack_price"), "0");
    expect(marked(panel)).toEqual([]);
    expect(queryAll(panel, `${DIALOG} .error`)).toEqual([]);
  });

  it("picks a colour with the colour picker, kept in sync with its field", async () => {
    const panel = await mountPanel(catalogBackend(), { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    const picker = query(panel, `${DIALOG} input[type=color]`) as HTMLInputElement;
    expect(picker.getAttribute("aria-label")).toBe("Pick a colour");

    await fill(panel, picker, "#ff8800");
    expect((field(panel, "colour") as HTMLInputElement).value).toBe("#ff8800");
    await fill(panel, field(panel, "colour"), "#00AA11");
    expect(picker.value).toBe("#00aa11");

    await click(panel, query(panel, "ha-icon-button.clear-colour"));
    expect((field(panel, "colour") as HTMLInputElement).value).toBe("");
    expect(queryAll(panel, "ha-icon-button.clear-colour")).toHaveLength(0);
  });

  it("says so when every Material is archived", async () => {
    const backend = recordedBackend().subscription(CATALOG, () => [
      {
        ...recorded.catalog.empty,
        materials: [{ ...recorded.material("material-1"), archived: true }],
      },
    ]);

    const panel = await mountPanel(backend, { path: "/materials" });

    expect(queryAll(panel, ".table.active")).toHaveLength(0);
    expect(text(query(panel, ".none-active"))).toBe(
      "Every Material is archived. Restore one below or create a new one.",
    );
  });

  it("marks a Material as its type's default", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, query(row(panel, "Standard Resin grey"), "ha-icon-button.star"));

    expect(lastCall(backend)).toEqual({
      type: UPDATE,
      material_id: "material-2",
      material: { default_for_type: true },
    });
  });

  it("archives and restores", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "eSun PLA+ black"), "Archive"));
    expect(lastCall(backend)).toEqual({
      type: "coinop/materials/archive",
      material_id: "material-1",
    });
    await click(panel, button(row(panel, "PLA red (old brand)"), "Restore"));
    expect(lastCall(backend)).toEqual({
      type: "coinop/materials/restore",
      material_id: "material-3",
    });
  });

  it("deletes after confirmation in a dialog", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    const dialog = await confirmDelete(panel, "Standard Resin grey");
    expect(text(dialog)).toContain("Delete “Standard Resin grey”?");
    expect(text(dialog)).toContain("A Material that Runs use is archived instead");
    expect(queryAll(panel, "tr.material ha-button")).toEqual([]);
    expect(backend.sent(DELETE)).toEqual([]);
    await click(panel, button(dialog, "Delete for good"));

    expect(backend.sent(DELETE)).toEqual([{ type: DELETE, material_id: "material-2" }]);
    expect(queryAll(panel, ".delete-dialog")).toEqual([]);
  });

  it("keeps a Material whose deletion is cancelled", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    const dialog = await confirmDelete(panel, "Standard Resin grey");

    await click(panel, query(dialog, "ha-button.cancel"));

    expect(queryAll(panel, ".delete-dialog")).toEqual([]);
    expect(backend.sent(DELETE)).toEqual([]);
  });

  it("says when a Material is kept archived because Runs use it", async () => {
    const backend = catalogBackend().reply(DELETE, () => ({ deleted: false }));
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, query(await confirmDelete(panel, "eSun PLA+ black"), "ha-button.confirm"));

    expect(text(query(panel, ".notice"))).toBe(
      "“eSun PLA+ black” is used by Runs, so it was archived instead.",
    );
  });

  it("follows catalogue changes pushed by the backend", async () => {
    const backend = recordedBackend().subscription(CATALOG, () => [recorded.catalog.empty]);
    const panel = await mountPanel(backend, { path: "/materials" });

    backend.push(CATALOG, recorded.catalog.filled);
    await settle(panel);

    expect(rows(panel)).toHaveLength(2);
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/materials" });

    expect(rows(panel)[1]).toBe(
      "Standard Resin grey Harz · Standard resin 1,1 g/cm³ 29,99 € / 1.000 ml 27,26 € / kg",
    );
  });
});

describe("Laundry Materials", () => {
  const withLaundry = () =>
    catalogBackend().subscription(CATALOG, () => [
      { ...recorded.catalog.filled, materials: recorded.laundry },
    ]);

  it("are listed with their price per kg, or per piece when bought by the piece", async () => {
    const panel = await mountPanel(withLaundry(), { path: "/materials" });

    expect(rows(panel)).toEqual([
      "Liquid detergent Detergent · Liquid detergent 1.04 g/cm³ €7.80 / 1,500 ml €5.00 / kg",
      "Colour pods Detergent · Detergent pods €12.00 / 40 pcs €0.30 / pcs",
    ]);
  });

  it("are created with form, density and pack unit pre-filled from the type", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));

    await fill(panel, field(panel, "name"), "Liquid detergent");
    await fill(panel, field(panel, "type"), "Liquid detergent");
    expect((field(panel, "form") as HTMLSelectElement).value).toBe("detergent");
    expect((field(panel, "density") as HTMLInputElement).value).toBe("1.04");
    expect((field(panel, "pack_unit") as HTMLSelectElement).value).toBe("ml");
    expect(queryAll(panel, "[name=diameter]")).toHaveLength(0);
    await fill(panel, field(panel, "pack_price"), "7.80");
    await fill(panel, field(panel, "pack_size"), "1500");
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        material: {
          name: "Liquid detergent",
          form: "detergent",
          type: "Liquid detergent",
          density: 1.04,
          vendor: null,
          colour: null,
          diameter: null,
          default_for_type: false,
          price: { source: "fixed", pack_price: 7.8, pack_size: 1500, pack_unit: "ml" },
        },
      },
    ]);
  });

  it("are created by the piece without density or diameter", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));

    await fill(panel, field(panel, "name"), "Colour pods");
    await fill(panel, field(panel, "type"), "Detergent pods");
    expect((field(panel, "pack_unit") as HTMLSelectElement).value).toBe("pcs");
    expect(queryAll(panel, "[name=density], [name=diameter]")).toHaveLength(0);
    await fill(panel, field(panel, "pack_price"), "12");
    await fill(panel, field(panel, "pack_size"), "40");
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        material: {
          name: "Colour pods",
          form: "detergent",
          type: "Detergent pods",
          density: null,
          vendor: null,
          colour: null,
          diameter: null,
          default_for_type: false,
          price: { source: "fixed", pack_price: 12, pack_size: 40, pack_unit: "pcs" },
        },
      },
    ]);
  });

  it("ask for a density again when switched from pieces to millilitres", async () => {
    const backend = withLaundry();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "Colour pods"), "Edit"));

    await fill(panel, field(panel, "pack_unit"), "ml");
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(marked(panel)).toEqual(["density"]);
  });
});
