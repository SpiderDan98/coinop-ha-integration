import { describe, expect, it } from "vitest";
import type { Message } from "../src/hass";
import { recorded, recordedBackend } from "./fake-hass";
import { change, click, mountPanel, query, queryAll, text } from "./render";

const UPDATE = "wattbill/line_items/update";
const [started] = recorded.changes;
const overridden = recorded.lineItemsUpdate.run;

const sent = (backend: { calls: Message[] }, type: string) =>
  backend.calls.filter((call) => call.type === type);
const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);
const field = (row: HTMLElement, name: string) => query(row, `[name=${name}]`) as HTMLInputElement;
const values = (row: HTMLElement) =>
  ["quantity", "unit_price", "amount"].map((name) => field(row, name).value);

describe("Line Items", () => {
  it("are rows edited in place", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    const electricity = item(panel, "electricity");
    expect(text(electricity)).toContain("Electricity Estimated from average power");
    expect(values(electricity)).toEqual(["0.15", "0.3", "0.05"]);
    expect(queryAll(electricity, "[name=label]")).toHaveLength(0);
    const wear = item(panel, "benchy-wear");
    expect(field(wear, "label").value).toBe("Nozzle wear");
    expect(field(wear, "unit").value).toBe("pcs");
    expect(values(wear)).toEqual(["1", "0.5", "0.50"]);
  });

  it("override a computed value, marked manual with the computed one in a tooltip", async () => {
    const backend = recordedBackend().reply(UPDATE, () => recorded.lineItemsUpdate);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(item(panel, "electricity").classList.contains("manual")).toBe(false);
    expect(queryAll(panel, "button.reset")).toHaveLength(0);

    await change(panel, field(item(panel, "electricity"), "amount"), "0.1");

    expect(sent(backend, UPDATE)).toEqual([
      { type: UPDATE, run_id: "benchy", line_item_id: "electricity", amount: 0.1 },
    ]);
    const electricity = item(panel, "electricity");
    expect(electricity.classList.contains("manual")).toBe(true);
    expect(values(electricity)).toEqual(["0.15", "0.6667", "0.10"]);
    expect(query(electricity, "button.reset").title).toBe(
      "Manual value. Reset to the computed value: 0.15 kWh × €0.30 = €0.05",
    );
    expect(field(electricity, "unit_price").title).toBe("Computed: €0.30");
    expect(field(electricity, "quantity").title).toBe("");
    expect(text(query(panel, ".totals"))).toContain("Total €0.91");
  });

  it("reset to the computed value", async () => {
    const backend = recordedBackend()
      .reply("wattbill/runs/get", () => ({ run: overridden }))
      .reply("wattbill/line_items/reset", () => ({ run: recorded.run("benchy") }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await click(panel, query(item(panel, "electricity"), "button.reset"));

    expect(sent(backend, "wattbill/line_items/reset")).toEqual([
      { type: "wattbill/line_items/reset", run_id: "benchy", line_item_id: "electricity" },
    ]);
    expect(item(panel, "electricity").classList.contains("manual")).toBe(false);
    expect(values(item(panel, "electricity"))).toEqual(["0.15", "0.3", "0.05"]);
  });

  it("send labels, units and an emptied quantity as entered", async () => {
    const backend = recordedBackend().reply(UPDATE, () => ({ run: recorded.run("benchy") }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const wear = item(panel, "benchy-wear");

    await change(panel, field(wear, "label"), " Hotend wear ");
    await change(panel, field(wear, "unit"), "h");
    await change(panel, field(wear, "quantity"), "");

    expect(sent(backend, UPDATE)).toEqual([
      { type: UPDATE, run_id: "benchy", line_item_id: "benchy-wear", label: "Hotend wear" },
      { type: UPDATE, run_id: "benchy", line_item_id: "benchy-wear", unit: "h" },
      { type: UPDATE, run_id: "benchy", line_item_id: "benchy-wear", quantity: null },
    ]);
  });

  it("put back a price that is no number or could not be saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () =>
      Promise.reject(new Error("invalid_format")),
    );
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const amount = field(item(panel, "electricity"), "amount");

    await change(panel, amount, "");
    expect(sent(backend, UPDATE)).toEqual([]);
    expect(amount.value).toBe("0.05");

    await change(panel, amount, "-1");
    expect(amount.value).toBe("0.05");
    expect(text(query(panel, ".items"))).toContain("This change could not be saved.");
  });

  it("allow negative prices only on Other Line Items", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(field(item(panel, "electricity"), "unit_price").min).toBe("0");
    expect(field(item(panel, "benchy-pla"), "amount").min).toBe("0");
    expect(field(item(panel, "benchy-wear"), "unit_price").min).toBe("");
  });

  it("can be deleted, except Electricity", async () => {
    const backend = recordedBackend().reply("wattbill/line_items/delete", () => ({
      run: {
        ...recorded.run("benchy"),
        line_items: recorded.run("benchy").line_items.slice(0, 2),
      },
    }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(queryAll(item(panel, "electricity"), "button.delete")).toHaveLength(0);

    await click(panel, query(item(panel, "benchy-wear"), "button.delete"));

    expect(sent(backend, "wattbill/line_items/delete")).toEqual([
      { type: "wattbill/line_items/delete", run_id: "benchy", line_item_id: "benchy-wear" },
    ]);
    expect(queryAll(panel, ".item")).toHaveLength(2);
  });

  it("add Other items by hand, a refund too", async () => {
    const backend = recordedBackend().reply("wattbill/line_items/add", () => recorded.lineItemsAdd);
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    expect(queryAll(panel, ".add-item")).toHaveLength(1);

    await click(panel, query(panel, "button.add-other"));
    const form = query(panel, ".add-item form");
    expect(text(form)).toContain("Negative unit prices are allowed here, e.g. a refund.");
    await change(panel, field(form, "label"), "Refund for the failed print");
    await change(panel, field(form, "unit_price"), "-2");
    await click(panel, query(form, "button[type=submit]"));

    expect(sent(backend, "wattbill/line_items/add")).toEqual([
      {
        type: "wattbill/line_items/add",
        run_id: "helmet",
        kind: "other",
        label: "Refund for the failed print",
        quantity: 1,
        unit: "",
        unit_price: -2,
      },
    ]);
    expect(queryAll(panel, ".add-item form")).toHaveLength(0);
    expect(field(item(panel, "helmet-refund"), "label").value).toBe("Refund for the failed print");
    expect(text(query(panel, ".totals"))).toContain("Total -€1.70");
  });

  it("lock live values while the Run is open, but take Other items", async () => {
    const backend = recordedBackend().subscription("wattbill/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });
    const electricity = item(panel, "print-live-electricity");

    expect(electricity.classList.contains("locked")).toBe(true);
    for (const name of ["quantity", "unit_price", "amount"]) {
      expect(field(electricity, name).disabled).toBe(true);
    }
    expect(query(electricity, ".lock").title).toBe("Updates live until the Run is final.");
    expect(queryAll(panel, "button.add-other")).toHaveLength(1);
  });

  it("are labelled in German when Home Assistant is, user labels verbatim", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), {
      path: "/run/benchy",
    });

    expect(text(item(panel, "electricity"))).toContain("Strom");
    expect(field(item(panel, "benchy-wear"), "label").value).toBe("Nozzle wear");
    expect(text(query(panel, "button.add-other"))).toBe("+ Sonstigen Posten hinzufügen");
  });
});
