import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { change, click, fill, mountPanel, query, queryAll, text } from "./render";

const FILAMENTS = "coinop/spoolman/filaments";
const CATALOG = "coinop/catalog/subscribe";
const linked = recorded.linkSpoolman.material;
const withLinked = {
  ...recorded.catalog.filled,
  materials: [...recorded.catalog.filled.materials, linked],
};
const filamentRows = (panel: Element) => queryAll(panel, "tr.filament").map(text);
const button = (root: Element, label: string) => {
  const found = queryAll(root, "ha-button, ha-icon-button, button").find(
    (candidate) => text(candidate) === label || (candidate as { label?: string }).label === label,
  );
  if (!found) throw new Error(`no button "${label}"`);
  return found;
};
const row = (panel: Element, selector: string, name: string) => {
  const found = queryAll(panel, selector).find((candidate) => text(candidate).includes(name));
  if (!found) throw new Error(`no row "${name}"`);
  return found;
};
const DIALOG = ".material-dialog";
const UPDATE = "coinop/materials/update";
const field = (panel: Element, name: string) => query(panel, `${DIALOG} [name=${name}]`);
const save = (panel: Element) => click(panel, query(panel, `${DIALOG} ha-button.save`));

function spoolmanBackend(filaments = recorded.spoolman.filaments) {
  return recordedBackend()
    .subscription(CATALOG, () => [withLinked])
    .reply(FILAMENTS, () => filaments)
    .reply("coinop/materials/create_from_spoolman", () => recorded.createFromSpoolman)
    .reply(UPDATE, () => recorded.linkSpoolman);
}

describe("Spoolman in the Materials tab", () => {
  it("reads the Filaments every time the tab opens", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, query(panel, `a.tab[href$="/tags"]`));
    await click(panel, query(panel, `a.tab[href$="/materials"]`));

    expect(backend.calls.filter((call) => call.type === FILAMENTS)).toHaveLength(2);
  });

  it("lists the Filaments, marking those a Material is linked to", async () => {
    const panel = await mountPanel(spoolmanBackend(), { path: "/materials" });

    expect(text(query(panel, ".spoolman h3"))).toBe("Spoolman Filaments");
    expect(filamentRows(panel)).toEqual([
      "eSun PLA+ black PLA €20.00 / kg Linked to PLA black",
      "Prusament PETG Galaxy Black PETG €29.99 / kg Create Material",
      "eSun TPU clear TPU No price in Spoolman Create Material",
    ]);
  });

  it("creates a Material from a Filament", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "tr.filament", "PETG"), "Create Material"));

    expect(backend.calls.at(-1)).toEqual({
      type: "coinop/materials/create_from_spoolman",
      filament_id: 8,
    });
  });

  it("shows a linked Material's price as coming from Spoolman", async () => {
    const panel = await mountPanel(spoolmanBackend(), { path: "/materials" });

    expect(text(row(panel, "tr.material", "PLA black"))).toBe(
      "PLA black eSun Filament · PLA 1.24 g/cm³ · ⌀ 1.75 mm From Spoolman €20.00 / kg",
    );
  });

  it("links a Material to a Filament, which then supplies its details", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "eSun PLA+ black"), "Edit"));

    await change(panel, field(panel, "price_source"), "spoolman");
    expect(queryAll(panel, "[name=pack_price], [name=density], [name=type]")).toHaveLength(0);
    expect(text(query(panel, DIALOG))).toContain(
      "Type, density, diameter, colour and vendor come from the Spoolman Filament",
    );
    await change(panel, field(panel, "filament_id"), "7");
    expect(backend.sent(UPDATE)).toEqual([]);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        material_id: "material-1",
        material: {
          name: "eSun PLA+ black",
          default_for_type: true,
          price: { source: "spoolman", filament_id: 7 },
        },
      },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("asks for the Filament before linking", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "eSun PLA+ black"), "Edit"));
    await change(panel, field(panel, "price_source"), "spoolman");

    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(field(panel, "filament_id").getAttribute("aria-invalid")).toBe("true");
  });

  it("links nothing when the dialog is cancelled", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "eSun PLA+ black"), "Edit"));
    await change(panel, field(panel, "price_source"), "spoolman");
    await change(panel, field(panel, "filament_id"), "7");

    await click(panel, query(panel, `${DIALOG} ha-button.cancel`));

    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect(backend.sent(UPDATE)).toEqual([]);
  });

  it("keeps the dialog open and says so when Spoolman went away while linking", async () => {
    const backend = spoolmanBackend().reply(UPDATE, () => {
      throw new WsError("spoolman_unreachable");
    });
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "eSun PLA+ black"), "Edit"));
    await change(panel, field(panel, "price_source"), "spoolman");
    await change(panel, field(panel, "filament_id"), "7");

    await save(panel);

    expect(text(query(panel, `${DIALOG} .error`))).toBe(
      "Spoolman can't be reached right now. Linked Materials keep the last price read.",
    );
    expect(backend.sent(FILAMENTS)).toHaveLength(2);
  });

  it("edits a linked Material's own fields and can unlink it", async () => {
    const backend = spoolmanBackend();
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "PLA black"), "Edit"));
    expect((field(panel, "filament_id") as HTMLSelectElement).value).toBe("7");

    await change(panel, field(panel, "price_source"), "fixed");
    expect((field(panel, "type") as HTMLInputElement).value).toBe("PLA");
    await fill(panel, field(panel, "pack_price"), "24");
    await save(panel);

    expect(backend.sent(UPDATE)).toMatchObject([
      {
        type: UPDATE,
        material_id: "pla-black",
        material: {
          type: "PLA",
          price: { source: "fixed", pack_price: 24, pack_size: 1000, pack_unit: "g" },
        },
      },
    ]);
  });

  it("duplicates a linked Material as one with a pack price of its own", async () => {
    const CREATE = "coinop/materials/create";
    const backend = spoolmanBackend().reply(CREATE, () => recorded.linkSpoolman);
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "tr.material", "PLA black"), "Duplicate"));
    expect(queryAll(panel, `${DIALOG} [name=price_source]`)).toHaveLength(0);
    expect((field(panel, "type") as HTMLInputElement).value).toBe("PLA");
    await save(panel);
    expect(backend.sent(CREATE)).toEqual([]);
    await fill(panel, field(panel, "pack_price"), "24");
    await save(panel);

    expect(backend.sent(CREATE)).toMatchObject([
      {
        type: CREATE,
        material: {
          name: "PLA black",
          price: { source: "fixed", pack_price: 24, pack_size: 1000, pack_unit: "g" },
        },
      },
    ]);
  });

  it("creates linked Materials only from the Filament list", async () => {
    const panel = await mountPanel(spoolmanBackend(), { path: "/materials" });

    await click(panel, button(panel, "New Material"));

    expect(queryAll(panel, "[name=price_source]")).toHaveLength(0);
  });

  it("offers no link for a Material bought by the piece", async () => {
    const backend = spoolmanBackend().subscription(CATALOG, () => [
      { ...withLinked, materials: recorded.laundry },
    ]);
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "tr.material", "Liquid detergent"), "Edit"));
    expect(queryAll(panel, "[name=price_source]")).toHaveLength(1);
    await click(panel, query(panel, `${DIALOG} ha-button.cancel`));
    await click(panel, button(row(panel, "tr.material", "Colour pods"), "Edit"));
    expect(queryAll(panel, "[name=price_source]")).toHaveLength(0);
    await change(panel, field(panel, "pack_unit"), "g");
    expect(queryAll(panel, "[name=price_source]")).toHaveLength(0);
  });

  it("shows nothing of Spoolman while it isn't set up", async () => {
    const backend = spoolmanBackend(recorded.spoolman.notConfigured);
    const panel = await mountPanel(backend, { path: "/materials" });
    await click(panel, button(row(panel, "tr.material", "eSun PLA+ black"), "Edit"));

    expect(queryAll(panel, DIALOG)).toHaveLength(1);
    expect(queryAll(panel, ".spoolman, [name=price_source]")).toHaveLength(0);
  });

  it("says when Spoolman can't be reached", async () => {
    const panel = await mountPanel(spoolmanBackend(recorded.spoolman.unreachable), {
      path: "/materials",
    });

    expect(text(query(panel, ".spoolman"))).toBe(
      "Spoolman Filaments Spoolman can't be reached right now. Linked Materials keep the last price read.",
    );
  });

  it("says when creating from Spoolman fails because it went away", async () => {
    const backend = spoolmanBackend().reply("coinop/materials/create_from_spoolman", () => {
      throw new WsError("spoolman_unreachable");
    });
    const panel = await mountPanel(backend, { path: "/materials" });

    await click(panel, button(row(panel, "tr.filament", "PETG"), "Create Material"));

    expect(text(query(panel, ".notice"))).toBe(
      "Spoolman can't be reached right now. Linked Materials keep the last price read.",
    );
  });

  it("is in German when Home Assistant is", async () => {
    const backend = recordedBackend({ language: "de" })
      .subscription(CATALOG, () => [withLinked])
      .reply(FILAMENTS, () => recorded.spoolman.filaments);
    const panel = await mountPanel(backend, { path: "/materials" });

    expect(text(query(panel, ".spoolman h3"))).toBe("Spoolman-Filamente");
    expect(filamentRows(panel)).toEqual([
      "eSun PLA+ black PLA 20,00 € / kg Verknüpft mit PLA black",
      "Prusament PETG Galaxy Black PETG 29,99 € / kg Material erstellen",
      "eSun TPU clear TPU Kein Preis in Spoolman Material erstellen",
    ]);
  });
});
