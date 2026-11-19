import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const CATALOG = "wattbill/catalog/subscribe";
const rows = (panel: Element, selector = ".active tr.material") =>
  queryAll(panel, selector).map(text);
const field = (panel: Element, name: string) => query(panel, `[name=${name}]`);
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

/** A backend that answers Material commands with what the real one would. */
function catalogBackend() {
  const backend = recordedBackend();
  const pla = recorded.material("material-1");
  return backend
    .reply("wattbill/materials/create", (msg) => ({
      material: { ...pla, ...(msg.material as object), id: "new" },
    }))
    .reply("wattbill/materials/update", (msg) => ({
      material: { ...pla, ...(msg.material as object) },
    }))
    .reply("wattbill/materials/archive", () => ({ material: { ...pla, archived: true } }))
    .reply("wattbill/materials/restore", () => ({ material: pla }))
    .reply("wattbill/materials/delete", () => ({ deleted: true }));
}

describe("Materials tab", () => {
  it("opens from the toolbar", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/materials"]`));

    expect(location.pathname).toBe("/wattbill/materials");
    expect(text(query(panel, "a.tab.on"))).toBe("Materials");
    expect(text(query(panel, "h2"))).toBe("Materials");
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
    expect(labels(".active tr.material:first-child")).toEqual(["Edit", "Archive", "Delete"]);
    expect(labels(".archived tr.material")).toEqual(["Restore", "Delete"]);
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
    await click(panel, button(panel, "Save"));

    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/create",
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
    });
    expect(queryAll(panel, "form.material")).toHaveLength(0);
  });

  it("offers the built-in types and suggests resin by the millilitre", async () => {
    const panel = await mountPanel(catalogBackend(), { path: "/materials" });
    await click(panel, button(panel, "New Material"));

    await fill(panel, field(panel, "type"), "Standard resin");

    const options = queryAll(panel, "datalist option").map((option) =>
      option.getAttribute("value"),
    );
    expect(options).toContain("PLA");
    expect((field(panel, "form") as HTMLSelectElement).value).toBe("resin");
    expect((field(panel, "pack_unit") as HTMLSelectElement).value).toBe("ml");
    expect(queryAll(panel, "[name=diameter]")).toHaveLength(0);
  });

  it("edits a Material in place of the form", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "eSun PLA+ black"), "Edit"));
    expect((field(panel, "name") as HTMLInputElement).value).toBe("eSun PLA+ black");
    expect((field(panel, "pack_price") as HTMLInputElement).value).toBe("19.99");

    await fill(panel, field(panel, "pack_size"), "2000");
    await fill(panel, field(panel, "colour"), "");
    await click(panel, button(panel, "Save"));

    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/update",
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
    });
  });

  it("keeps the form open and says so when the backend rejects it", async () => {
    const backend = catalogBackend().reply("wattbill/materials/create", () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    await fill(panel, field(panel, "name"), "PLA");
    await fill(panel, field(panel, "type"), "PLA");
    await fill(panel, field(panel, "pack_price"), "20");

    await click(panel, button(panel, "Save"));

    expect(lastCall(backend)?.type).toBe("wattbill/materials/create");
    expect(text(query(panel, "form.material"))).toContain(
      "Check the fields: name, type, density, pack price and pack size are required",
    );
  });

  it("marks what is missing instead of saving an empty pack price as free", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    await fill(panel, field(panel, "name"), "PLA");
    await fill(panel, field(panel, "colour"), "red");

    await click(panel, button(panel, "Save"));

    expect(backend.sent("wattbill/materials/create")).toEqual([]);
    const marked = queryAll(panel, 'form.material [aria-invalid="true"]').map((input) =>
      input.getAttribute("name"),
    );
    expect(marked).toEqual(["type", "density", "colour", "pack_price"]);
    await fill(panel, field(panel, "type"), "PLA");
    await fill(panel, field(panel, "colour"), "");
    await fill(panel, field(panel, "pack_price"), "0");
    expect(queryAll(panel, 'form.material [aria-invalid="true"]')).toHaveLength(0);
  });

  it("picks a colour with the colour picker, kept in sync with its field", async () => {
    const panel = await mountPanel(catalogBackend(), { path: "/materials" });
    await click(panel, button(panel, "New Material"));
    const picker = query(panel, "input.colour-picker") as HTMLInputElement;
    expect(picker.type).toBe("color");

    await fill(panel, picker, "#ff8800");
    expect((field(panel, "colour") as HTMLInputElement).value).toBe("#ff8800");
    await fill(panel, field(panel, "colour"), "#00AA11");
    expect((query(panel, "input.colour-picker") as HTMLInputElement).value).toBe("#00aa11");

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

    expect(queryAll(panel, ".card.active")).toHaveLength(0);
    expect(text(query(panel, ".none-active"))).toBe(
      "Every Material is archived. Restore one below or create a new one.",
    );
  });

  it("marks a Material as its type's default", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, query(row(panel, "Standard Resin grey"), "ha-icon-button.star"));

    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/update",
      material_id: "material-2",
      material: { default_for_type: true },
    });
  });

  it("archives and restores", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "eSun PLA+ black"), "Archive"));
    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/archive",
      material_id: "material-1",
    });
    await click(panel, button(row(panel, "PLA red (old brand)"), "Restore"));
    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/restore",
      material_id: "material-3",
    });
  });

  it("deletes after confirmation", async () => {
    const backend = catalogBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "Standard Resin grey"), "Delete"));
    expect(backend.calls.map((call) => call.type)).not.toContain("wattbill/materials/delete");
    await click(panel, button(row(panel, "Standard Resin grey"), "Delete for good"));

    expect(lastCall(backend)).toEqual({
      type: "wattbill/materials/delete",
      material_id: "material-2",
    });
  });

  it("says when a Material is kept archived because Runs use it", async () => {
    const backend = catalogBackend().reply("wattbill/materials/delete", () => ({
      deleted: false,
    }));
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "eSun PLA+ black"), "Delete"));
    await click(panel, button(row(panel, "eSun PLA+ black"), "Delete for good"));

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
