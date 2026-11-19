import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { change, click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const sent = (backend: ReturnType<typeof recordedBackend>, type: string) =>
  backend.calls.filter((call) => call.type === type);
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
    expect(queryAll(panel, "a.tab").map(text)).toEqual([
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(text(query(panel, "h2"))).toBe("Line Item Templates");
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
    expect(text(panel)).toContain(
      "Adding a template copies its values into the Run. Editing or deleting a template never changes past Runs.",
    );
  });

  it("saves each field as it is changed", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    await change(panel, field(row(panel, "template-packaging"), "unit_price"), "0.6");
    await change(panel, field(row(panel, "template-inserts"), "label"), " M3 inserts ");
    await change(panel, field(row(panel, "template-inserts"), "basis"), "running_hours");

    expect(sent(backend, UPDATE)).toEqual([
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
    expect(sent(backend, UPDATE)).toEqual([]);
    expect(label.value).toBe("Threaded inserts");

    await change(panel, label, "M3 inserts");
    expect(label.value).toBe("Threaded inserts");
    expect(text(panel)).toContain("This change could not be saved.");
  });

  it("creates a template", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    await click(panel, query(panel, "button.new-template"));
    const form = query(panel, "form.new");
    await fill(panel, field(form, "label"), " Labour ");
    await fill(panel, field(form, "unit"), "h");
    await fill(panel, field(form, "unit_price"), "15");
    await fill(panel, field(form, "default_quantity"), "0.5");
    await click(panel, query(form, "button[type=submit]"));

    expect(sent(backend, "wattbill/templates/create")).toEqual([
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

  it("deletes a template", async () => {
    const backend = templatesBackend();
    const panel = await mountPanel(backend, { path: "/templates" });

    const remove = query(row(panel, "template-wear"), "button.delete");
    expect(remove.title).toBe("Delete (past Runs keep their copies)");
    await click(panel, remove);

    expect(sent(backend, "wattbill/templates/delete")).toEqual([
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

    expect(text(query(panel, "h2"))).toBe("Postenvorlagen");
    expect(text(row(panel, "template-wear"))).toContain("Aus der Laufzeit des Laufs");
  });
});
