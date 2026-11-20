import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, label, mountPanel, query, queryAll, text } from "./render";

const UPDATE = "coinop/line_items/update";
const [started] = recorded.changes;
const overridden = recorded.lineItemsUpdate.run;

const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);
const field = (root: HTMLElement, name: string) =>
  query(root, `[name=${name}]`) as HTMLInputElement;
const VALUES = ["quantity", "unit_price", "amount"];
/** What a row reads. */
const values = (row: HTMLElement) => VALUES.map((name) => text(query(row, `.${name}`)));
/** What a dialog's fields hold. */
const entered = (dialog: HTMLElement) => VALUES.map((name) => field(dialog, name).value);
const edit = async (panel: Element, id: string) => {
  await click(panel, query(item(panel, id), "ha-icon-button.edit"));
  return query(panel, ".item-dialog");
};
const save = (panel: Element) => click(panel, query(panel, ".dialog ha-button.save"));

describe("Line Items", () => {
  it("are read as rows and edited in a dialog", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    const electricity = item(panel, "electricity");
    expect(text(query(electricity, ".label"))).toBe("Estimated from average power");
    expect(text(query(panel, ".item-head"))).toBe("Quantity Unit price Amount");
    expect(values(electricity)).toEqual(["0.15 kWh", "€0.30", "€0.05"]);
    expect(text(query(item(panel, "benchy-wear"), ".name"))).toBe("Nozzle wear");
    expect(values(item(panel, "benchy-wear"))).toEqual(["1 pcs", "€0.50", "€0.50"]);
    expect(queryAll(panel, ".items input, .items select")).toHaveLength(0);

    const dialog = await edit(panel, "electricity");
    expect(text(query(dialog, "h2"))).toBe("Edit Line Item");
    expect(entered(dialog)).toEqual(["0.15", "0.3", "0.05"]);
    expect(queryAll(dialog, ".with-unit .unit").map(text)).toEqual(["kWh", "€/kWh", "€"]);
    expect(queryAll(dialog, "[name=label], [name=unit]")).toHaveLength(0);
    await click(panel, query(dialog, "ha-button.cancel"));

    const wear = await edit(panel, "benchy-wear");
    expect(field(wear, "label").value).toBe("Nozzle wear");
    expect(field(wear, "unit").value).toBe("pcs");
    expect(entered(wear)).toEqual(["1", "0.5", "0.50"]);
  });

  it("override a computed value, marked manual with the computed one in a tooltip", async () => {
    const backend = recordedBackend().reply(UPDATE, () => recorded.lineItemsUpdate);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(item(panel, "electricity").classList.contains("manual")).toBe(false);
    expect(queryAll(panel, "ha-icon-button.reset")).toHaveLength(0);

    const dialog = await edit(panel, "electricity");
    await fill(panel, field(dialog, "amount"), "0.1");
    expect(backend.sent(UPDATE)).toEqual([]);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, run_id: "benchy", line_item_id: "electricity", amount: 0.1 },
    ]);
    expect(queryAll(panel, ".item-dialog")).toHaveLength(0);
    const electricity = item(panel, "electricity");
    expect(electricity.classList.contains("manual")).toBe(true);
    expect(values(electricity)).toEqual(["0.15 kWh", "€0.6667", "€0.10"]);
    expect(label(query(electricity, "ha-icon-button.reset"))).toBe(
      "Manual value. Reset to the computed value: 0.15 kWh × €0.30 = €0.05",
    );
    expect(query(electricity, ".unit_price").title).toBe("Computed: €0.30");
    expect(query(electricity, ".quantity").title).toBe("");
    expect(text(query(panel, ".totals"))).toContain("Total €0.91");
  });

  it("show the amount or the unit price following the one typed last", async () => {
    const backend = recordedBackend().reply(UPDATE, () => ({ run: recorded.run("benchy") }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await edit(panel, "electricity");

    await fill(panel, field(dialog, "amount"), "0.1");
    expect(entered(dialog)).toEqual(["0.15", "0.6667", "0.1"]);
    await fill(panel, field(dialog, "quantity"), "0.2");
    expect(entered(dialog)).toEqual(["0.2", "0.5", "0.1"]);
    await fill(panel, field(dialog, "unit_price"), "0.4");
    expect(entered(dialog)).toEqual(["0.2", "0.4", "0.08"]);
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        run_id: "benchy",
        line_item_id: "electricity",
        quantity: 0.2,
        unit_price: 0.4,
      },
    ]);
  });

  it("send nothing when the dialog is cancelled or nothing was changed", async () => {
    const backend = recordedBackend().reply(UPDATE, () => recorded.lineItemsUpdate);
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    const dialog = await edit(panel, "electricity");
    await fill(panel, field(dialog, "amount"), "0.1");
    await click(panel, query(dialog, "ha-button.cancel"));
    expect(queryAll(panel, ".item-dialog")).toHaveLength(0);
    await edit(panel, "electricity");
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(queryAll(panel, ".item-dialog")).toHaveLength(0);
    expect(values(item(panel, "electricity"))).toEqual(["0.15 kWh", "€0.30", "€0.05"]);
  });

  it("reset to the computed value", async () => {
    const backend = recordedBackend()
      .reply("coinop/runs/get", () => ({ run: overridden }))
      .reply("coinop/line_items/reset", () => ({ run: recorded.run("benchy") }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await click(panel, query(item(panel, "electricity"), "ha-icon-button.reset"));

    expect(backend.sent("coinop/line_items/reset")).toEqual([
      { type: "coinop/line_items/reset", run_id: "benchy", line_item_id: "electricity" },
    ]);
    expect(item(panel, "electricity").classList.contains("manual")).toBe(false);
    expect(values(item(panel, "electricity"))).toEqual(["0.15 kWh", "€0.30", "€0.05"]);
  });

  it("send labels, units and an emptied quantity as entered, in one change", async () => {
    const backend = recordedBackend().reply(UPDATE, () => ({ run: recorded.run("benchy") }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await edit(panel, "benchy-wear");

    await fill(panel, field(dialog, "label"), " Hotend wear ");
    await fill(panel, field(dialog, "unit"), "h");
    await fill(panel, field(dialog, "quantity"), "");
    await save(panel);

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        run_id: "benchy",
        line_item_id: "benchy-wear",
        label: "Hotend wear",
        unit: "h",
        quantity: null,
      },
    ]);
  });

  it("keep the dialog open for a price that is no number or could not be saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () =>
      Promise.reject(new Error("invalid_format")),
    );
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await edit(panel, "electricity");

    await fill(panel, field(dialog, "amount"), "");
    await save(panel);
    expect(backend.sent(UPDATE)).toEqual([]);
    expect(field(dialog, "amount").getAttribute("aria-invalid")).toBe("true");

    await fill(panel, field(dialog, "amount"), "-1");
    await save(panel);
    expect(backend.sent(UPDATE)).toHaveLength(1);
    expect(text(query(panel, ".item-dialog .error"))).toBe("This change could not be saved.");
    expect(field(dialog, "amount").value).toBe("-1");
    expect(values(item(panel, "electricity"))).toEqual(["0.15 kWh", "€0.30", "€0.05"]);
  });

  it("allow negative prices only on Other Line Items", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });
    const min = async (id: string, name: string) => {
      const value = field(await edit(panel, id), name).min;
      await click(panel, query(panel, ".item-dialog ha-button.cancel"));
      return value;
    };

    expect(await min("electricity", "unit_price")).toBe("0");
    expect(await min("benchy-pla", "amount")).toBe("0");
    expect(await min("benchy-wear", "unit_price")).toBe("");
  });

  it("can be deleted once confirmed, except Electricity", async () => {
    const backend = recordedBackend().reply("coinop/line_items/delete", () => ({
      run: {
        ...recorded.run("benchy"),
        line_items: recorded.run("benchy").line_items.slice(0, 2),
      },
    }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(queryAll(item(panel, "electricity"), "ha-icon-button.delete")).toHaveLength(0);
    const remove = () => click(panel, query(item(panel, "benchy-wear"), "ha-icon-button.delete"));

    await remove();
    expect(text(query(panel, ".delete-item-dialog"))).toBe(
      "Delete “Nozzle wear”? It no longer counts towards the Run's total. " +
        "This cannot be undone. Cancel Delete",
    );
    await click(panel, query(panel, ".delete-item-dialog ha-button.cancel"));
    expect(queryAll(panel, ".delete-item-dialog")).toHaveLength(0);
    expect(backend.sent("coinop/line_items/delete")).toEqual([]);

    await remove();
    await click(panel, query(panel, ".delete-item-dialog ha-button.confirm"));

    expect(backend.sent("coinop/line_items/delete")).toEqual([
      { type: "coinop/line_items/delete", run_id: "benchy", line_item_id: "benchy-wear" },
    ]);
    expect(queryAll(panel, ".delete-item-dialog")).toHaveLength(0);
    expect(queryAll(panel, ".item")).toHaveLength(2);
  });

  it("add Other items by hand, a refund too", async () => {
    const backend = recordedBackend().reply("coinop/line_items/add", () => recorded.lineItemsAdd);
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    expect(queryAll(panel, ".add-item ha-button").map((button) => button.className)).toEqual([
      "small add-material",
      "small add-other",
      "small add-template",
    ]);

    await click(panel, query(panel, "ha-button.add-other"));
    const dialog = query(panel, ".new-item-dialog");
    expect(text(query(dialog, "h2"))).toBe("Add Other Line Item");
    expect(text(dialog)).toContain("Negative unit prices are allowed here, e.g. a refund.");
    expect(field(dialog, "quantity").value).toBe("1");
    await fill(panel, field(dialog, "label"), "Refund for the failed print");
    await fill(panel, field(dialog, "unit_price"), "-2");
    expect(backend.sent("coinop/line_items/add")).toEqual([]);
    await save(panel);

    expect(backend.sent("coinop/line_items/add")).toEqual([
      {
        type: "coinop/line_items/add",
        run_id: "helmet",
        kind: "other",
        label: "Refund for the failed print",
        quantity: 1,
        unit: "",
        unit_price: -2,
      },
    ]);
    expect(queryAll(panel, ".new-item-dialog")).toHaveLength(0);
    expect(text(query(item(panel, "helmet-refund"), ".name"))).toBe("Refund for the failed print");
    expect(text(query(panel, ".totals"))).toContain("Total -€1.70");
  });

  it("are not added without a unit price", async () => {
    const backend = recordedBackend().reply("coinop/line_items/add", () => recorded.lineItemsAdd);
    const panel = await mountPanel(backend, { path: "/run/helmet" });

    await click(panel, query(panel, "ha-button.add-other"));
    await save(panel);

    expect(backend.sent("coinop/line_items/add")).toEqual([]);
    const dialog = query(panel, ".new-item-dialog");
    expect(field(dialog, "unit_price").getAttribute("aria-invalid")).toBe("true");
    expect(field(dialog, "quantity").getAttribute("aria-invalid")).toBe("false");
  });

  it("lock live values while the Run is open, but take Other items", async () => {
    const backend = recordedBackend().subscription("coinop/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });
    const electricity = item(panel, "print-live-electricity");

    expect(electricity.classList.contains("locked")).toBe(true);
    expect(queryAll(electricity, "ha-icon-button.edit")).toHaveLength(0);
    expect(query(electricity, ".lock").title).toBe("Updates live until the Run is final.");
    expect(queryAll(panel, "ha-button.add-other")).toHaveLength(1);
  });

  it("are labelled in German when Home Assistant is, user labels verbatim", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), {
      path: "/run/benchy",
    });

    expect(text(query(item(panel, "electricity"), ".label"))).toBe(
      "Aus der Durchschnittsleistung geschätzt",
    );
    expect(text(query(panel, ".item-head"))).toBe("Menge Stückpreis Betrag");
    expect(text(query(item(panel, "benchy-wear"), ".name"))).toBe("Nozzle wear");
    expect(text(query(panel, "ha-button.add-other"))).toBe("Sonstigen Posten hinzufügen");
    expect(text(query(await edit(panel, "benchy-wear"), "h2"))).toBe("Posten bearbeiten");
  });
});
