import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "coinop/runs/subscribe";
const GET = "coinop/runs/get";
const [started, updated, ended] = recorded.changes;
/** A Line Item row as a receipt line: "label evidence quantity × unit price = amount". */
const receiptLine = (item: HTMLElement) =>
  [
    ...queryAll(item, ".label > *").map(text),
    text(query(item, ".quantity")),
    "×",
    text(query(item, ".unit_price")),
    "=",
    text(query(item, ".amount")),
  ].join(" ");
const cards = (panel: Element) =>
  queryAll(panel, ".kind").map((card) => [
    text(query(card, ".between")),
    ...queryAll(card, ".item").map(receiptLine),
  ]);
const facts = (panel: Element) => text(query(panel, ".facts dl"));

describe("Run page", () => {
  it("opens from its gallery tile", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);
    const [, , benchy] = queryAll(panel, ".tile");
    expect(text(benchy)).toContain("Benchy");

    await click(panel, benchy);

    expect(location.pathname).toBe("/coinop/run/benchy");
    expect(text(query(panel, ".title"))).toBe("Coin-op › Runs › Benchy");
    expect(backend.calls.at(-1)).toEqual({ type: GET, run_id: "benchy" });
  });

  it("reads like a receipt: Line Items by kind with subtotals and a total", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(cards(panel)).toEqual([
      ["Electricity €0.05", "Estimated from average power 0.15 kWh × €0.30 = €0.05"],
      [
        "Material €0.31",
        "PLA Basic Black 4,191 mm at 1.75 mm and 1.24 g/cm³ 12.5 g × €0.025 = €0.31",
      ],
      ["Other €0.50", "Nozzle wear 1 pcs × €0.50 = €0.50"],
    ]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.86 Cost per part (4) €0.22");
  });

  it("shows the Run's facts next to its Line Items", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(text(query(panel, ".runbar"))).toBe("Completed Kobra · Jan 12, 2026, 10:00 AM Delete");
    expect(text(query(panel, ".facts h3"))).toBe("Benchy");
    expect(facts(panel)).toBe(
      "Device Kobra Started Jan 12, 2026, 10:00 AM Ended Jan 12, 2026, 11:15 AM " +
        "Running time 1 h 15 min Part Count 4 Tags Gift Note Four on one plate",
    );
    expect(
      queryAll(panel, "coinop-run-page input:not([type=file]), coinop-run-page select"),
    ).toEqual([]);
  });

  it("names the price segments of electricity and marks empty kinds", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/helmet" });

    expect(cards(panel)).toEqual([
      [
        "Electricity €0.30",
        "Estimated from average power · 2 price segments " +
          "10:00 AM – 4:00 PM · 0.6 kWh × €0.30 4:00 – 7:00 PM · 0.48 kWh × €0.25 " +
          "1.08 kWh × €0.2778 = €0.30",
      ],
      [
        "Material €0.00",
        "No Material 30,000 mm measured; pick a Material to weigh it — × €0.00 = €0.00",
      ],
      ["Other €0.00"],
    ]);
    const [, , other] = queryAll(panel, ".kind").map(text);
    expect(other).toBe("Other €0.00 None Add Other Line Item From template");
  });

  it("lists each price segment under the electricity evidence", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/helmet" });

    expect(queryAll(panel, ".segments li").map(text)).toEqual([
      "10:00 AM – 4:00 PM · 0.6 kWh × €0.30",
      "4:00 – 7:00 PM · 0.48 kWh × €0.25",
    ]);
  });

  it("leads back to all Runs", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    await click(panel, query(panel, ".title a.runs-link"));

    expect(location.pathname).toBe("/coinop/runs");
    expect(queryAll(panel, ".tile")).toHaveLength(3);
  });

  it("follows an open Run until it ends", async () => {
    const backend = recordedBackend().subscription(SUBSCRIBE, () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });
    expect(text(query(panel, ".runbar"))).toMatch(/^In progress/);
    expect(text(query(panel, ".facts .ended"))).toBe("—");
    expect(facts(panel)).toContain("Running time 45 min");
    const live = recorded.run("print-live");

    backend.reply(GET, () => ({ run: { ...live, ...ended.run } }));
    backend.push(SUBSCRIBE, updated);
    backend.push(SUBSCRIBE, ended);
    await settle(panel);

    expect(text(query(panel, ".runbar"))).toMatch(/^Completed/);
    expect(text(query(panel, ".facts .ended"))).toBe("Jan 15, 2026, 10:45 AM");
  });

  it("shows an open Run's Projected Total, its expected end and what it includes", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/print-live" });

    expect(text(query(panel, ".totals .projected"))).toBe("Projected Total ≈ €0.68");
    expect(text(query(panel, ".totals .projection"))).toBe(
      "Expected end Jan 15, 2026, 12:00 PM · Includes electricity, material, and running hours",
    );
  });

  it("names the drying among what the Projected Total includes", async () => {
    const backend = recordedBackend().reply(GET, () => ({ run: recorded.drying[1] }));
    const panel = await mountPanel(backend, { path: "/run/drying" });

    expect(text(query(panel, ".totals .projected"))).toBe("Projected Total ≈ €0.20");
    expect(text(query(panel, ".totals .projection"))).toBe(
      "Expected end Jan 15, 2026, 12:50 PM · Includes electricity and drying",
    );
  });

  it("says that drying isn't included yet while its power is still being learned", async () => {
    const backend = recordedBackend().reply(GET, () => ({ run: recorded.drying[0] }));
    const panel = await mountPanel(backend, { path: "/run/drying" });

    expect(text(query(panel, ".totals .projection"))).toBe(
      "Expected end Jan 15, 2026, 12:40 PM · Includes electricity · Drying isn't included yet",
    );
  });

  it("shows no Projected Total for an ended Run", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(queryAll(panel, ".totals .projected, .totals .projection")).toEqual([]);
  });

  it("says so when the Run is deleted while shown", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const benchy = recorded.summary("benchy");

    backend.reply(GET, () => Promise.reject(new Error("not_found")));
    backend.push(SUBSCRIBE, { change: "deleted", run: benchy });
    await settle(panel);

    expect(text(query(panel, "coinop-run-page"))).toBe(
      "This Run no longer exists. Back to all Runs",
    );
  });

  it("says so for a link to a Run that doesn't exist", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/nope" });

    expect(text(query(panel, "coinop-run-page"))).toContain("This Run no longer exists.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/run/benchy" });

    expect(cards(panel)[0]).toEqual([
      "Strom 0,05 €",
      "Aus der Durchschnittsleistung geschätzt 0,15 kWh × 0,30 € = 0,05 €",
    ]);
    expect(text(query(panel, ".totals"))).toBe("Gesamt 0,86 € Kosten pro Teil (4) 0,22 €");
  });

  it("names the Projected Total in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), {
      path: "/run/print-live",
    });

    expect(text(query(panel, ".totals .projected"))).toBe("Voraussichtlich ≈ 0,68 €");
    expect(text(query(panel, ".totals .projection"))).toBe(
      "Voraussichtliches Ende 15.01.2026, 12:00 · Enthält Strom, Material und Betriebsstunden",
    );
  });

  it("names the drying in German when Home Assistant is", async () => {
    const backend = recordedBackend({ language: "de" });
    backend.reply(GET, () => ({ run: recorded.drying[1] }));
    const included = await mountPanel(backend, { path: "/run/drying" });
    expect(text(query(included, ".totals .projection"))).toBe(
      "Voraussichtliches Ende 15.01.2026, 12:50 · Enthält Strom und Trocknen",
    );

    backend.reply(GET, () => ({ run: recorded.drying[0] }));
    const pending = await mountPanel(backend, { path: "/run/drying" });
    expect(text(query(pending, ".totals .projection"))).toBe(
      "Voraussichtliches Ende 15.01.2026, 12:40 · Enthält Strom · Trocknen noch nicht enthalten",
    );
  });

  it("has no Part Count for a washing machine Run", async () => {
    const backend = recordedBackend()
      .reply("coinop/devices/list", () => ({ devices: [recorded.washer] }))
      .reply(GET, () => ({ run: recorded.wash }));

    const panel = await mountPanel(backend, { path: "/run/wash" });

    expect(cards(panel)[0]).toEqual([
      "Electricity €0.36",
      "Measured by an energy meter 1.2 kWh × €0.30 = €0.36",
    ]);
    const material = cards(panel).find(([head]) => head.startsWith("Material"));
    expect(material?.[1]).toContain("From the Default row");
    expect(facts(panel)).not.toContain("Part Count");
    await click(panel, query(panel, ".facts ha-icon-button.edit"));
    expect(queryAll(panel, ".run-dialog [name=part_count]")).toHaveLength(0);
    expect(text(query(panel, ".totals"))).toBe("Total €0.75");
  });

  it("has no Program, Part Count or Water for a robotic mower's Run", async () => {
    const backend = recordedBackend()
      .reply("coinop/devices/list", () => ({ devices: [recorded.mower] }))
      .reply(GET, () => ({ run: recorded.mowing }));

    const panel = await mountPanel(backend, { path: "/run/mowing" });

    expect(facts(panel)).not.toMatch(/Program|Part Count/);
    expect(facts(panel)).toContain("Running time 1 h 5 min");
    expect(cards(panel)).toEqual([
      ["Electricity €0.08", "Measured by an energy meter 0.25 kWh × €0.30 = €0.08"],
      ["Material €0.00"],
      ["Other €0.00"],
    ]);
    await click(panel, query(panel, ".facts ha-icon-button.edit"));
    expect(queryAll(panel, ".run-dialog [name=program], .run-dialog [name=part_count]")).toEqual(
      [],
    );
    expect(text(query(panel, ".totals"))).toBe("Total €0.08");
  });

  it("has no Program, Part Count or Water for the Run of an Other Device that has nothing", async () => {
    const backend = recordedBackend()
      .reply("coinop/devices/list", () => ({ devices: recorded.others }))
      .reply(GET, () => ({ run: recorded.firing }));

    const panel = await mountPanel(backend, { path: "/run/firing" });

    expect(facts(panel)).not.toMatch(/Program|Part Count/);
    expect(facts(panel)).toContain("Device Kiln");
    expect(cards(panel)).toEqual([
      ["Electricity €0.90", "Estimated from average power 3 kWh × €0.30 = €0.90"],
      ["Material €0.00"],
      ["Other €0.00"],
    ]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.90");
  });

  it("collapses to one column on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy", narrow: true });

    expect(query(panel, "coinop-run-page").hasAttribute("narrow")).toBe(true);
  });
});
