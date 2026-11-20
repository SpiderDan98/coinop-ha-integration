import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import {
  click,
  fill,
  iconButton,
  label,
  mountPanel,
  query,
  queryAll,
  settle,
  text,
} from "./render";

const row = (panel: Element, id: string) => query(panel, `tr.template[data-id="${id}"]`);
const cells = (panel: Element, id: string) => queryAll(row(panel, id), "td").slice(0, 6).map(text);
const field = (root: HTMLElement, name: string) =>
  query(root, `[name=${name}]`) as HTMLInputElement;
const invalid = (root: HTMLElement, name: string) =>
  field(root, name).getAttribute("aria-invalid") === "true";
const UPDATE = "coinop/templates/update";
const CREATE = "coinop/templates/create";
const DELETE = "coinop/templates/delete";
const DIALOG = ".template-dialog";

const edit = async (panel: HTMLElement, id: string) => {
  await click(panel, query(row(panel, id), "ha-icon-button.edit"));
  return query(panel, DIALOG);
};
const add = async (panel: HTMLElement) => {
  await click(panel, query(panel, "ha-button.new-template"));
  return query(panel, DIALOG);
};
const save = (panel: HTMLElement) => click(panel, query(panel, `${DIALOG} ha-button.save`));

describe("Line Item Templates tab", () => {
  const templatesBackend = () =>
    recordedBackend()
      .reply(UPDATE, () => recorded.templateUpdate)
      .reply(CREATE, (msg) => ({
        template: { id: "template-new", ...(msg.template as object) },
      }))
      .reply(DELETE, () => ({}));

  it("opens from the toolbar between Materials and Tags", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/templates"]`));

    expect(location.pathname).toBe("/coinop/templates");
    expect(queryAll(panel, "a.tab").map((tab) => tab.title)).toEqual([
      "Overview",
      "Runs",
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(query(panel, "a.tab.on").title).toBe("Line Item Templates");
    expect(text(query(panel, ".page-title"))).toBe("Line Item Templates");
  });

  it("lists every template read-only with the Devices using it automatically", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/templates" });

    expect(cells(panel, "template-wear")).toEqual([
      "Wear Kobra",
      "h",
      "€0.15/h",
      "From the Run's running time",
      "Per running hour",
      "Kobra",
    ]);
    expect(cells(panel, "template-inserts")).toEqual([
      "Threaded inserts",
      "pcs",
      "€0.08/pcs",
      "8 pcs",
      "Fixed",
      "–",
    ]);
    expect(cells(panel, "template-packaging")).toEqual([
      "Packaging",
      "–",
      "€0.60",
      "1",
      "Fixed",
      "–",
    ]);
    expect(text(query(row(panel, "template-wear"), ".automatic"))).toBe("Kobra");
    expect(queryAll(query(panel, ".table.templates"), "input, select, textarea")).toEqual([]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect(text(panel)).toContain("Changes apply to future Runs only.");
  });

  it("edits a template in a dialog and saves only the fields that changed", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const pencil = query(row(panel, "template-packaging"), "ha-icon-button.edit");
    expect(label(pencil)).toBe("Edit");
    await click(panel, pencil);
    const packaging = query(panel, DIALOG);
    expect(text(packaging)).toContain("Edit Line Item Template");
    expect(
      ["label", "unit_price", "unit", "basis", "default_quantity"].map(
        (name) => field(packaging, name).value,
      ),
    ).toEqual(["Packaging", "0.6", "", "entered", "1"]);
    await fill(panel, field(packaging, "label"), " Boxes ");
    await fill(panel, field(packaging, "unit_price"), "0.75");
    expect(backend.sent(UPDATE)).toEqual([]);
    await save(panel);
    expect(queryAll(panel, DIALOG)).toEqual([]);

    const inserts = await edit(panel, "template-inserts");
    await fill(panel, field(inserts, "basis"), "running_hours");
    expect(queryAll(inserts, "[name=default_quantity]")).toEqual([]);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        template_id: "template-packaging",
        template: { label: "Boxes", unit_price: 0.75 },
      },
      { type: UPDATE, template_id: "template-inserts", template: { basis: "running_hours" } },
    ]);
  });

  it("takes a negative unit price but no negative default quantity", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });
    const dialog = await edit(panel, "template-inserts");
    expect(field(dialog, "unit_price").hasAttribute("min")).toBe(false);
    expect(field(dialog, "default_quantity").min).toBe("0");

    await fill(panel, field(dialog, "unit_price"), "-2");
    await fill(panel, field(dialog, "default_quantity"), "-1");
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(invalid(dialog, "unit_price")).toBe(false);
    expect(invalid(dialog, "default_quantity")).toBe(true);

    await fill(panel, field(dialog, "default_quantity"), "0");
    expect(invalid(dialog, "default_quantity")).toBe(false);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        template_id: "template-inserts",
        template: { unit_price: -2, default_quantity: 0 },
      },
    ]);
  });

  it("sends nothing when the dialog is cancelled or nothing changed", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const cancelled = await edit(panel, "template-inserts");
    await fill(panel, field(cancelled, "label"), "M3 inserts");
    await click(panel, query(cancelled, "ha-button.cancel"));
    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect(cells(panel, "template-inserts")[0]).toBe("Threaded inserts");

    const unchanged = await edit(panel, "template-inserts");
    expect(field(unchanged, "label").value).toBe("Threaded inserts");
    await fill(panel, field(unchanged, "label"), " Threaded inserts ");
    await fill(panel, field(unchanged, "unit_price"), "0.080");
    await save(panel);
    expect(queryAll(panel, DIALOG)).toEqual([]);

    const created = await add(panel);
    await fill(panel, field(created, "label"), "Labour");
    await fill(panel, field(created, "unit_price"), "15");
    await click(panel, query(created, "ha-button.cancel"));
    expect(queryAll(panel, DIALOG)).toEqual([]);
    expect(field(await add(panel), "label").value).toBe("");

    expect(backend.calls.filter(({ type }) => [UPDATE, CREATE, DELETE].includes(type))).toEqual([]);
  });

  it("keeps the dialog open on a value that is no valid one", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });
    const dialog = await edit(panel, "template-inserts");

    await fill(panel, field(dialog, "label"), "  ");
    await fill(panel, field(dialog, "unit_price"), "");
    expect(invalid(dialog, "label")).toBe(false);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(query(panel, DIALOG)).toBe(dialog);
    expect(
      ["label", "unit_price", "default_quantity"].map((name) => invalid(dialog, name)),
    ).toEqual([true, true, false]);
    expect(cells(panel, "template-inserts")[0]).toBe("Threaded inserts");

    await fill(panel, field(dialog, "label"), "M3 inserts");
    expect(invalid(dialog, "label")).toBe(false);
    await fill(panel, field(dialog, "unit_price"), "0.08");
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, template_id: "template-inserts", template: { label: "M3 inserts" } },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("keeps the dialog open with a message when a change could not be saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/templates" });
    const dialog = await edit(panel, "template-inserts");
    expect(queryAll(dialog, ".error")).toEqual([]);

    await fill(panel, field(dialog, "label"), "M3 inserts");
    await save(panel);

    expect(backend.sent(UPDATE)).toHaveLength(1);
    expect(query(panel, DIALOG)).toBe(dialog);
    expect(text(query(dialog, ".error"))).toBe("This change could not be saved.");
    expect(field(dialog, "label").value).toBe("M3 inserts");
    expect(cells(panel, "template-inserts")[0]).toBe("Threaded inserts");
  });

  it("creates a template", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const dialog = await add(panel);
    expect(text(dialog)).toContain("New template");
    expect(dialog.getRootNode()).toHaveProperty("activeElement", field(dialog, "label"));
    expect(
      ["label", "unit_price", "unit", "basis", "default_quantity"].map(
        (name) => field(dialog, name).value,
      ),
    ).toEqual(["", "", "", "entered", "1"]);
    await fill(panel, field(dialog, "label"), " Labour ");
    await fill(panel, field(dialog, "unit"), "h");
    await fill(panel, field(dialog, "unit_price"), "15");
    await fill(panel, field(dialog, "default_quantity"), "0.5");
    expect(backend.sent(CREATE)).toEqual([]);
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        template: {
          label: "Labour",
          unit: "h",
          unit_price: 15,
          default_quantity: 0.5,
          basis: "entered",
        },
      },
    ]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("duplicates a template into the dialog for a new one", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const copy = query(row(panel, "template-inserts"), "ha-icon-button.duplicate");
    expect(label(copy)).toBe("Duplicate");
    await click(panel, copy);
    const dialog = query(panel, DIALOG);
    expect(text(dialog)).toContain("New template");
    expect(
      ["label", "unit_price", "unit", "basis", "default_quantity"].map(
        (name) => field(dialog, name).value,
      ),
    ).toEqual(["Threaded inserts", "0.08", "pcs", "entered", "8"]);
    expect(backend.sent(CREATE)).toEqual([]);
    await fill(panel, field(dialog, "label"), "Threaded inserts M4");
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        template: {
          label: "Threaded inserts M4",
          unit: "pcs",
          unit_price: 0.08,
          default_quantity: 8,
          basis: "entered",
        },
      },
    ]);
    expect(backend.sent(UPDATE)).toEqual([]);
    expect(queryAll(panel, DIALOG)).toEqual([]);
  });

  it("creates a running-hours template, which has no default quantity to enter", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });
    const dialog = await add(panel);

    await save(panel);
    expect(backend.sent(CREATE)).toEqual([]);
    expect(["label", "unit_price"].map((name) => invalid(dialog, name))).toEqual([true, true]);

    await fill(panel, field(dialog, "label"), "Wear Mini");
    await fill(panel, field(dialog, "unit"), "h");
    await fill(panel, field(dialog, "unit_price"), "0.1");
    await fill(panel, field(dialog, "basis"), "running_hours");
    expect(queryAll(dialog, "[name=default_quantity]")).toEqual([]);
    await save(panel);

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        template: {
          label: "Wear Mini",
          unit: "h",
          unit_price: 0.1,
          default_quantity: 1,
          basis: "running_hours",
        },
      },
    ]);
  });

  it("keeps the dialog open with a message when a template could not be created", async () => {
    const backend = recordedBackend().reply(CREATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/templates" });
    const dialog = await add(panel);

    await fill(panel, field(dialog, "label"), "Labour");
    await fill(panel, field(dialog, "unit_price"), "15");
    await save(panel);

    expect(query(panel, DIALOG)).toBe(dialog);
    expect(text(query(dialog, ".error"))).toBe("This change could not be saved.");
  });

  it("deletes a template once confirmed, naming the Devices that add it", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const remove = query(row(panel, "template-wear"), "ha-icon-button.delete");
    expect(label(remove)).toBe("Delete (past Runs keep their copies)");
    await click(panel, remove);
    const confirmation = query(panel, ".delete-template-dialog");
    expect(text(confirmation)).toContain("Delete “Wear Kobra”?");
    expect(text(confirmation)).toContain("Deletes “Wear Kobra”. Past Runs keep their copies.");
    expect(text(confirmation)).toContain("No longer added automatically for: Kobra.");
    await click(panel, query(confirmation, "ha-button.cancel"));
    expect(queryAll(panel, ".delete-template-dialog")).toEqual([]);
    expect(backend.sent(DELETE)).toEqual([]);

    await click(panel, remove);
    const confirm = query(panel, ".delete-template-dialog ha-button.confirm");
    expect(text(confirm)).toBe("Delete for good");
    await click(panel, confirm);

    expect(backend.sent(DELETE)).toEqual([{ type: DELETE, template_id: "template-wear" }]);
    expect(queryAll(panel, ".delete-template-dialog")).toEqual([]);
  });

  it("names no Devices when deleting a template none adds, and says when that failed", async () => {
    const backend = recordedBackend().reply(DELETE, () => {
      throw new WsError("not_found");
    });
    const panel = await mountPanel(backend, { path: "/templates" });

    await click(panel, query(row(panel, "template-inserts"), "ha-icon-button.delete"));
    expect(text(query(panel, ".delete-template-dialog"))).not.toContain("automatically");
    await click(panel, query(panel, ".delete-template-dialog ha-button.confirm"));

    expect(backend.sent(DELETE)).toEqual([{ type: DELETE, template_id: "template-inserts" }]);
    expect(text(query(panel, "coinop-templates-page p.error"))).toBe(
      "This change could not be saved.",
    );
  });

  it("follows the catalogue and says when there are no templates", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    backend.push("coinop/catalog/subscribe", { templates: [] });
    await settle(panel);

    expect(queryAll(panel, "tr.template")).toHaveLength(0);
    expect(text(panel)).toContain("No Line Item Templates yet.");
    expect(queryAll(panel, "ha-button.new-template.fab")).toHaveLength(1);
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/templates" });

    expect(text(query(panel, ".page-title"))).toBe("Postenvorlagen");
    expect(text(row(panel, "template-wear"))).toContain("Aus der Laufzeit des Laufs");
    expect(text(await edit(panel, "template-wear"))).toContain("Postenvorlage bearbeiten");
  });
});

describe("Line Item Templates on a Run", () => {
  const SAVE = "coinop/line_items/save_as_template";
  const ADD = "coinop/line_items/add_template";
  const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);

  it("saves any Line Item as a template, a computed one under its kind's name", async () => {
    const backend = recordedBackend().reply(SAVE, () => recorded.saveAsTemplate);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    const save = query(item(panel, "benchy-wear"), "ha-icon-button.save-template");
    expect(label(save)).toBe("Save as Line Item Template");
    await click(panel, save);
    expect(text(query(panel, ".items"))).toContain("Saved “Nozzle wear” as a Line Item Template.");
    await click(panel, query(item(panel, "electricity"), "ha-icon-button.save-template"));

    expect(backend.sent(SAVE)).toEqual([
      { type: SAVE, run_id: "benchy", line_item_id: "benchy-wear" },
      { type: SAVE, run_id: "benchy", line_item_id: "electricity", label: "Electricity" },
    ]);
  });

  it("adds a template with its default or an entered quantity", async () => {
    const backend = recordedBackend().reply(ADD, () => recorded.lineItemsAddTemplate);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const add = async () => {
      await click(panel, query(panel, "ha-button.add-template"));
      return query(panel, ".new-item-dialog");
    };

    const dialog = await add();
    expect(text(query(dialog, "h2"))).toBe("Add from a Line Item Template");
    const options = queryAll(dialog, "select[name=template] option").map(text);
    expect(options).toEqual([
      "Wear Kobra · €0.15/h",
      "Threaded inserts · €0.08/pcs",
      "Packaging · €0.60",
    ]);
    expect(text(dialog)).toContain("Quantity: the Run's running hours (1.25 h)");
    await fill(panel, field(dialog, "template"), "template-inserts");
    expect(field(dialog, "quantity").placeholder).toBe("Quantity (default 8)");
    await click(panel, query(dialog, "ha-button.save"));
    await fill(panel, field(await add(), "template"), "template-packaging");
    await fill(panel, field(query(panel, ".new-item-dialog"), "quantity"), "2");
    await click(panel, query(panel, ".new-item-dialog ha-button.save"));

    expect(backend.sent(ADD)).toEqual([
      { type: ADD, run_id: "benchy", template_id: "template-inserts" },
      { type: ADD, run_id: "benchy", template_id: "template-packaging", quantity: 2 },
    ]);
    expect(queryAll(panel, ".new-item-dialog")).toHaveLength(0);
    expect(text(query(item(panel, "benchy-nozzle"), ".name"))).toBe("Nozzle wear");
    expect(text(query(panel, ".totals"))).toContain("Total €1.91");
  });

  it("shows a running-hours template live and locked while the Run is open", async () => {
    const backend = recordedBackend().subscription("coinop/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, recorded.changes[1].run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });

    const wear = item(panel, "print-live-wear");
    expect(wear.classList.contains("locked")).toBe(true);
    expect(text(wear)).toContain("From a template · running hours, pauses excluded");
    expect(text(query(wear, ".quantity"))).toBe("0.75 h");
    expect(queryAll(wear, "ha-icon-button.edit, ha-icon-button.delete")).toHaveLength(0);
  });
});

describe("Automatic templates", () => {
  const SETTINGS = "coinop/devices/update_settings";
  const settingsBackend = () =>
    recordedBackend().reply(SETTINGS, (msg) => ({
      settings: { ...recorded.devices[0]?.settings, ...(msg.settings as object) },
    }));
  const chosen = (panel: Element) => queryAll(panel, ".template-chip .template-name").map(text);

  it("are picked per Device in its settings dialog and saved with it", async () => {
    const backend = settingsBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Kobra"));
    const section = query(panel, ".settings-dialog .automatic-templates");
    expect(text(section)).toContain(
      "Added to every Run that starts on this Device. Changes affect future Runs only.",
    );
    expect(chosen(section)).toEqual(["Wear Kobra"]);
    const picker = query(section, "select") as HTMLSelectElement;
    expect(queryAll(picker, "option").map(text)).toEqual([
      "+ Add template",
      "Threaded inserts",
      "Packaging",
    ]);

    await fill(panel, picker, "template-inserts");
    expect(chosen(section)).toEqual(["Wear Kobra", "Threaded inserts"]);
    await click(panel, iconButton(panel, "Remove Wear Kobra"));
    await click(panel, query(panel, ".settings-dialog ha-button.save"));

    expect(backend.sent(SETTINGS)).toEqual([
      {
        type: SETTINGS,
        device_id: "device-kobra",
        settings: { automatic_templates: ["template-inserts"] },
      },
    ]);
    expect(chosen(panel)).toEqual(["Threaded inserts"]);
  });

  it("say when they could not be saved", async () => {
    const backend = recordedBackend().reply(SETTINGS, () => {
      throw new WsError("not_found");
    });
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Kobra"));

    await click(panel, iconButton(panel, "Remove Wear Kobra"));
    await click(panel, query(panel, ".settings-dialog ha-button.save"));

    expect(text(query(panel, ".settings-dialog .error"))).toBe("This change could not be saved.");
    expect(text(query(panel, ".device .automatic-templates"))).toBe("Wear Kobra");
  });
});
