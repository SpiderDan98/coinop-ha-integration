import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import {
  change,
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
const field = (root: HTMLElement, name: string) =>
  query(root, `[name=${name}]`) as HTMLInputElement;
const UPDATE = "wattbill/templates/update";

describe("Line Item Templates tab", () => {
  const templatesBackend = () =>
    recordedBackend()
      .reply(UPDATE, () => recorded.templateUpdate)
      .reply("wattbill/templates/create", (msg) => ({
        template: { id: "template-new", ...(msg.template as object) },
      }))
      .reply("wattbill/templates/delete", () => ({}));

  it("opens from the toolbar between Materials and Tags", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/templates"]`));

    expect(location.pathname).toBe("/wattbill/templates");
    expect(queryAll(panel, "a.tab").map((tab) => tab.title)).toEqual([
      "Runs",
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(query(panel, "a.tab.on").title).toBe("Line Item Templates");
    expect(text(query(panel, ".title"))).toBe("Line Item Templates");
  });

  it("lists every template as an editable row with the Devices using it automatically", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/templates" });

    const wear = row(panel, "template-wear");
    expect(["label", "unit", "unit_price", "basis"].map((name) => field(wear, name).value)).toEqual(
      ["Wear Kobra", "h", "0.15", "running_hours"],
    );
    expect(queryAll(wear, "[name=default_quantity]")).toHaveLength(0);
    expect(text(wear)).toContain("From the Run's running time");
    expect(text(query(wear, ".automatic"))).toBe("Kobra");
    const inserts = row(panel, "template-inserts");
    expect(field(inserts, "default_quantity").value).toBe("8");
    expect(text(query(inserts, ".automatic"))).toBe("–");
    expect(text(panel)).toContain("Changes apply to future Runs only.");
  });

  it("saves each field as it is changed", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    await change(panel, field(row(panel, "template-packaging"), "unit_price"), "0.6");
    await change(panel, field(row(panel, "template-inserts"), "label"), " M3 inserts ");
    await change(panel, field(row(panel, "template-inserts"), "basis"), "running_hours");

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, template_id: "template-packaging", template: { unit_price: 0.6 } },
      { type: UPDATE, template_id: "template-inserts", template: { label: "M3 inserts" } },
      { type: UPDATE, template_id: "template-inserts", template: { basis: "running_hours" } },
    ]);
  });

  it("puts back a value that is no valid one or could not be saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/templates" });
    const label = field(row(panel, "template-inserts"), "label");

    await change(panel, label, "  ");
    expect(backend.sent(UPDATE)).toEqual([]);
    expect(label.value).toBe("Threaded inserts");

    await change(panel, label, "M3 inserts");
    expect(label.value).toBe("Threaded inserts");
    expect(text(panel)).toContain("This change could not be saved.");
  });

  it("creates a template", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    await click(panel, query(panel, "ha-button.new-template"));
    const form = query(panel, "form.new");
    await fill(panel, field(form, "label"), " Labour ");
    await fill(panel, field(form, "unit"), "h");
    await fill(panel, field(form, "unit_price"), "15");
    await fill(panel, field(form, "default_quantity"), "0.5");
    await click(panel, query(form, "ha-button[type=submit]"));

    expect(backend.sent("wattbill/templates/create")).toEqual([
      {
        type: "wattbill/templates/create",
        template: {
          label: "Labour",
          unit: "h",
          unit_price: 15,
          default_quantity: 0.5,
          basis: "entered",
        },
      },
    ]);
    expect(queryAll(panel, "form.new")).toHaveLength(0);
  });

  it("deletes a template once confirmed, naming the Devices that add it", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const remove = query(row(panel, "template-wear"), "ha-icon-button.delete");
    expect(label(remove)).toBe("Delete (past Runs keep their copies)");
    await click(panel, remove);
    expect(backend.sent("wattbill/templates/delete")).toEqual([]);
    expect(text(query(row(panel, "template-wear"), ".delete-hint"))).toContain(
      "No longer added automatically for: Kobra.",
    );
    await click(panel, query(row(panel, "template-wear"), "ha-button.confirm-delete"));

    expect(backend.sent("wattbill/templates/delete")).toEqual([
      { type: "wattbill/templates/delete", template_id: "template-wear" },
    ]);
  });

  it("follows the catalogue and says when there are no templates", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    backend.push("wattbill/catalog/subscribe", { templates: [] });
    await settle(panel);

    expect(queryAll(panel, "tr.template")).toHaveLength(0);
    expect(text(panel)).toContain("No Line Item Templates yet.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/templates" });

    expect(text(query(panel, ".title"))).toBe("Postenvorlagen");
    expect(text(row(panel, "template-wear"))).toContain("Aus der Laufzeit des Laufs");
  });
});

describe("Line Item Templates on a Run", () => {
  const SAVE = "wattbill/line_items/save_as_template";
  const ADD = "wattbill/line_items/add_template";
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

    await click(panel, query(panel, "ha-button.add-template"));
    const form = query(panel, ".add-item form.template");
    const options = queryAll(form, "select[name=template] option").map(text);
    expect(options).toEqual([
      "Wear Kobra · €0.15/h",
      "Threaded inserts · €0.08/pcs",
      "Packaging · €0.60",
    ]);
    expect(text(form)).toContain("Quantity: the Run's running hours (1.25 h)");
    await fill(panel, field(form, "template"), "template-inserts");
    expect(field(form, "quantity").placeholder).toBe("Quantity (default 8)");
    await click(panel, query(form, "ha-button[type=submit]"));
    await click(panel, query(panel, "ha-button.add-template"));
    await fill(panel, field(query(panel, "form.template"), "template"), "template-packaging");
    await fill(panel, field(query(panel, "form.template"), "quantity"), "2");
    await click(panel, query(panel, "form.template ha-button[type=submit]"));

    expect(backend.sent(ADD)).toEqual([
      { type: ADD, run_id: "benchy", template_id: "template-inserts" },
      { type: ADD, run_id: "benchy", template_id: "template-packaging", quantity: 2 },
    ]);
    expect(queryAll(panel, ".add-item form")).toHaveLength(0);
    expect(field(item(panel, "benchy-nozzle"), "label").value).toBe("Nozzle wear");
    expect(text(query(panel, ".totals"))).toContain("Total €1.91");
  });

  it("shows a running-hours template live and locked while the Run is open", async () => {
    const backend = recordedBackend().subscription("wattbill/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, recorded.changes[1].run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });

    const wear = item(panel, "print-live-wear");
    expect(wear.classList.contains("locked")).toBe(true);
    expect(text(wear)).toContain("From a template · running hours, pauses excluded");
    expect(field(wear, "quantity").value).toBe("0.75");
    expect(queryAll(wear, "[name=unit]")).toHaveLength(0);
    expect(queryAll(wear, "ha-icon-button.delete")).toHaveLength(0);
  });
});

describe("Automatic templates", () => {
  const SETTINGS = "wattbill/devices/update_settings";
  const settingsBackend = () =>
    recordedBackend().reply(SETTINGS, (msg) => ({
      settings: { ...recorded.devices[0]?.settings, ...(msg.settings as object) },
    }));
  const chosen = (panel: Element) => queryAll(panel, ".template-chip .template-name").map(text);

  it("are picked per Device in the Devices tab and saved at once", async () => {
    const backend = settingsBackend();
    const panel = await mountPanel(backend, { path: "/devices" });
    const section = query(panel, ".device .automatic-templates");
    expect(text(section)).toContain(
      "Added to every Run that starts on this Device. Changes affect future Runs only.",
    );
    expect(chosen(panel)).toEqual(["Wear Kobra"]);
    const picker = query(section, "select") as HTMLSelectElement;
    expect(queryAll(picker, "option").map(text)).toEqual([
      "+ Add template",
      "Threaded inserts",
      "Packaging",
    ]);

    await fill(panel, picker, "template-inserts");
    expect(chosen(panel)).toEqual(["Wear Kobra", "Threaded inserts"]);
    await click(panel, iconButton(panel, "Remove Wear Kobra"));

    expect(backend.sent(SETTINGS)).toEqual([
      {
        type: SETTINGS,
        device_id: "device-kobra",
        settings: { automatic_templates: ["template-wear", "template-inserts"] },
      },
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

    await click(panel, iconButton(panel, "Remove Wear Kobra"));

    expect(chosen(panel)).toEqual(["Wear Kobra"]);
    expect(text(query(panel, ".device .error"))).toBe("This change could not be saved.");
  });
});
