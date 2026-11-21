import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { change, click, fill, mountPanel, query, queryAll, text } from "./render";

const READ = "coinop/spoolman/read";
const MERGE = "coinop/spoolman/merge";
const CATALOG = "coinop/catalog/subscribe";
const UPDATE = "coinop/materials/update";
const CREATE = "coinop/materials/create";
const DIALOG = ".material-dialog";
const MERGE_DIALOG = ".merge-dialog";
const withMaterials = (materials = recorded.spoolman.materials) => ({
  ...recorded.catalog.filled,
  materials,
});
const button = (root: Element, label: string) => {
  const found = queryAll(root, "ha-button, ha-icon-button, button").find(
    (candidate) => text(candidate) === label || (candidate as { label?: string }).label === label,
  );
  if (!found) throw new Error(`no button "${label}"`);
  return found;
};
const labels = (root: Element) =>
  queryAll(root, "ha-icon-button").map((candidate) => (candidate as { label?: string }).label);
const row = (panel: Element, name: string) => {
  const found = queryAll(panel, "tr.material").find((candidate) =>
    text(query(candidate, ".strong")).startsWith(name),
  );
  if (!found) throw new Error(`no row "${name}"`);
  return found;
};
const names = (panel: Element, selector = "") =>
  queryAll(panel, `${selector} tr.material .strong`).map(text);
const field = (panel: Element, name: string) => query(panel, `[name=${name}]`) as HTMLInputElement;

function spoolmanBackend(read = recorded.spoolman.read, materials = recorded.spoolman.materials) {
  return recordedBackend()
    .subscription(CATALOG, () => [withMaterials(materials)])
    .reply(READ, () => read)
    .reply(MERGE, () => recorded.spoolman.merged)
    .reply(UPDATE, () => ({ material: materials[0] }))
    .reply(CREATE, () => ({ material: materials[0] }));
}

const open = (backend = spoolmanBackend()) => mountPanel(backend, { path: "/materials" });

describe("Spoolman in the Materials tab", () => {
  it("reads Spoolman every time the tab opens", async () => {
    const backend = spoolmanBackend();
    const panel = await open(backend);
    await click(panel, query(panel, `a.tab[href$="/tags"]`));
    await click(panel, query(panel, `a.tab[href$="/materials"]`));

    expect(backend.sent(READ)).toHaveLength(2);
  });

  it("shows a Material from Spoolman with its pack, a badge and a missing price", async () => {
    const panel = await open();

    expect(queryAll(panel, ".spoolman, tr.filament")).toEqual([]);
    expect(text(row(panel, "Prusament PETG Galaxy Black"))).toBe(
      "Prusament PETG Galaxy Black Prusament Filament · PETG 1.27 g/cm³ · ⌀ 1.75 mm Spoolman €29.99 / 1 kg €29.99 / kg",
    );
    expect(text(row(panel, "eSun TPU clear"))).toBe(
      "eSun TPU clear eSun Filament · TPU 1.24 g/cm³ · ⌀ 1.75 mm Spoolman No price in Spoolman —",
    );
    expect(text(row(panel, "PLA black"))).toBe(
      "PLA black eSun Filament · PLA 1.24 g/cm³ · ⌀ 1.75 mm €20.00 / 1,000 g €20.00 / kg",
    );
  });

  it("says at the top when Spoolman can't be reached", async () => {
    const panel = await open(spoolmanBackend(recorded.spoolman.unreachable));

    expect(text(query(panel, ".spoolman-notice"))).toBe(
      "Spoolman can't be reached right now. Materials from Spoolman keep the last price read.",
    );
    expect(queryAll(panel, ".merge-notice")).toEqual([]);
  });

  it("offers a linked Material no delete and its details read-only", async () => {
    const backend = spoolmanBackend();
    const panel = await open(backend);
    const linked = row(panel, "Prusament PETG Galaxy Black");

    expect(labels(linked)).toEqual(["Default Material for PETG", "Edit", "Duplicate", "Archive"]);
    await click(panel, button(linked, "Edit"));
    expect(queryAll(panel, `${DIALOG} input:not([type=checkbox]), ${DIALOG} select`)).toEqual([]);
    expect(text(query(panel, DIALOG))).toContain(
      "Prusament PETG Galaxy Black Form · Type Filament · PETG Density · Diameter 1.27 g/cm³ · ⌀ 1.75 mm Vendor Prusament Colour #2b2b33 Pack Spoolman €29.99 / 1 kg",
    );
    await fill(panel, field(panel, "default_for_type"), "off");
    await click(panel, query(panel, `${DIALOG} ha-button.save`));

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        material_id: "material-filament-8",
        material: { default_for_type: false },
      },
    ]);
  });

  it("restores an archived linked Material but never deletes it", async () => {
    const [own, ...rest] = recorded.spoolman.materials;
    const archived = rest.map((material) => ({ ...material, archived: true }));
    const panel = await open(spoolmanBackend(undefined, [own, ...archived]));

    expect(labels(row(panel, "eSun TPU clear"))).toEqual(["Restore"]);
  });

  it("duplicates a linked Material as an own one at the current Spoolman price", async () => {
    const backend = spoolmanBackend();
    const panel = await open(backend);

    await click(panel, button(row(panel, "Prusament PETG Galaxy Black"), "Duplicate"));
    expect(field(panel, "pack_price").value).toBe("29.99");
    expect(field(panel, "pack_size").value).toBe("1000");
    await click(panel, query(panel, `${DIALOG} ha-button.save`));

    expect(backend.sent(CREATE)).toMatchObject([
      {
        material: {
          name: "Prusament PETG Galaxy Black",
          type: "PETG",
          default_for_type: false,
          price: { source: "fixed", pack_price: 29.99, pack_size: 1000, pack_unit: "g" },
        },
      },
    ]);
  });

  it("asks for a price when duplicating a Material Spoolman has none for", async () => {
    const panel = await open();

    await click(panel, button(row(panel, "eSun TPU clear"), "Duplicate"));

    expect(field(panel, "pack_price").value).toBe("");
  });

  it("filters both tables by where the Materials come from", async () => {
    const [last, ...others] = [...recorded.spoolman.mergedMaterials].reverse();
    const materials = [...others.reverse(), { ...last, archived: true }];
    const panel = await open(spoolmanBackend(recorded.spoolman.merged, materials));

    expect(names(panel, ".archived")).toEqual(["Prusament PLA Galaxy Black"]);
    await click(panel, button(panel, "Own"));
    expect(names(panel)).toEqual(["Any PLA"]);
    await click(panel, button(panel, "From Spoolman"));
    expect(names(panel)).toEqual([
      "eSun PLA+ black",
      "Prusament PETG Galaxy Black",
      "eSun TPU clear",
      "Prusament PLA Galaxy Black",
    ]);
    await click(panel, button(panel, "All"));
    expect(names(panel)).toHaveLength(5);
  });

  it("shows no filter and nothing of Spoolman while it isn't set up", async () => {
    const panel = await open(spoolmanBackend(recorded.spoolman.notConfigured));

    expect(queryAll(panel, ".origin, .spoolman-notice, .merge-notice")).toEqual([]);
    await click(panel, button(panel, "New Material"));
    expect(queryAll(panel, "[name=price_source]")).toEqual([]);
  });

  it("merges own Materials into the Filaments picked for them", async () => {
    const backend = spoolmanBackend();
    const panel = await open(backend);

    expect(text(query(panel, ".merge-notice"))).toBe(
      "2 of your Materials match Spoolman Filaments. Review",
    );
    await click(panel, button(query(panel, ".merge-notice"), "Review"));
    const dialog = query(panel, MERGE_DIALOG);
    // The best match first; a Filament picked for one Material can't be picked for another.
    expect(field(dialog, "merge-pla-black").value).toBe("7");
    expect(field(dialog, "merge-pla-any").value).toBe("10");
    const options = (name: string) =>
      [...(field(dialog, name) as unknown as HTMLSelectElement).options].map(
        (option) => `${option.text.trim()}${option.disabled ? " (taken)" : ""}`,
      );
    expect(options("merge-pla-any")).toEqual([
      "eSun PLA+ black (taken)",
      "Prusament PLA Galaxy Black",
      "Keep own",
    ]);
    await change(panel, field(dialog, "merge-pla-any"), "");
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent(MERGE)).toEqual([
      {
        type: MERGE,
        picks: [
          { material_id: "pla-black", filament_id: 7 },
          { material_id: "pla-any", filament_id: null },
        ],
      },
    ]);
    expect(queryAll(panel, `${MERGE_DIALOG}, .merge-notice`)).toEqual([]);
  });

  it("reads again and says so when the merge no longer fits Spoolman", async () => {
    const backend = spoolmanBackend().reply(MERGE, () => {
      throw new WsError("not_allowed");
    });
    const panel = await open(backend);
    await click(panel, button(query(panel, ".merge-notice"), "Review"));

    await click(panel, query(panel, `${MERGE_DIALOG} ha-button.save`));

    expect(text(query(panel, `${MERGE_DIALOG} .error`))).toBe(
      "Spoolman changed meanwhile: check the picks again.",
    );
    expect(backend.sent(READ)).toHaveLength(2);
  });

  it("is in German when Home Assistant is", async () => {
    const backend = recordedBackend({ language: "de" })
      .subscription(CATALOG, () => [withMaterials()])
      .reply(READ, () => recorded.spoolman.read);
    const panel = await open(backend);

    expect(text(query(panel, ".merge-notice"))).toBe(
      "2 deiner Materialien passen zu Spoolman-Filamenten. Prüfen",
    );
    expect(text(row(panel, "eSun TPU clear"))).toContain("Spoolman Kein Preis in Spoolman");
    expect(text(query(panel, ".origin"))).toBe("Alle Aus Spoolman Eigene");
  });
});
