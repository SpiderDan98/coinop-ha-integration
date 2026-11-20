import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "coinop/runs/subscribe";
const GET = "coinop/runs/get";
const [started, updated, ended] = recorded.changes;
/** A Line Item row as a receipt line: "label evidence quantity unit × unit price = amount". */
const receiptLine = (item: HTMLElement) => {
  const shown = (selector: string) => {
    const element = queryAll(item, selector)[0];
    if (!element) return undefined;
    if (element instanceof HTMLSelectElement)
      return text(query(element, `option[value="${element.value}"]`));
    return element instanceof HTMLInputElement ? element.value : text(element);
  };
  return [
    shown(".label > :not(.evidence)"),
    ...queryAll(item, ".evidence").map(text),
    shown("[name=quantity]"),
    shown(".unit"),
    "×",
    shown("[name=unit_price]"),
    "=",
    shown("[name=amount]"),
  ]
    .filter((part) => part !== undefined)
    .join(" ");
};
const cards = (panel: Element) =>
  queryAll(panel, ".kind").map((card) => [
    text(query(card, ".between")),
    ...queryAll(card, ".item").map(receiptLine),
  ]);
const endedField = (panel: Element) => query(panel, "input[name=ended]") as HTMLInputElement;

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
      ["Electricity €0.05", "Estimated from average power 0.15 kWh × 0.3 = 0.05"],
      [
        "Material €0.31",
        "PLA Basic Black 4,191 mm at 1.75 mm and 1.24 g/cm³ 12.5 g × 0.025 = 0.31",
      ],
      ["Other €0.50", "Nozzle wear 1 pcs × 0.5 = 0.50"],
    ]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.86 Cost per part (4) €0.22");
  });

  it("shows the Run's facts next to its Line Items", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(text(query(panel, ".runbar"))).toBe(
      "Completed Kobra · Jan 12, 2026, 10:00 AM Every change saves at once. Delete",
    );
    expect(text(query(panel, ".facts dl"))).toBe("Device Kobra Running time 1 h 15 min");
  });

  it("names the price segments of electricity and marks empty kinds", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/helmet" });

    expect(cards(panel)).toEqual([
      [
        "Electricity €0.30",
        "Estimated from average power · 2 price segments " +
          "10:00 AM – 4:00 PM · 0.6 kWh × €0.30 4:00 – 7:00 PM · 0.48 kWh × €0.25 " +
          "1.08 kWh × 0.2778 = 0.30",
      ],
      [
        "Material €0.00",
        "No Material 30,000 mm measured; pick a Material to weigh it  g × 0 = 0.00",
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
    expect(endedField(panel).value).toBe("");
    expect(text(query(panel, ".facts dl"))).toContain("Running time 45 min");
    const live = recorded.run("print-live");

    backend.reply(GET, () => ({ run: { ...live, ...ended.run } }));
    backend.push(SUBSCRIBE, updated);
    backend.push(SUBSCRIBE, ended);
    await settle(panel);

    expect(text(query(panel, ".runbar"))).toMatch(/^Completed/);
    expect(endedField(panel).value).toBe("2026-01-15T10:45");
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
      "Aus der Durchschnittsleistung geschätzt 0.15 kWh × 0.3 = 0.05",
    ]);
    expect(text(query(panel, ".totals"))).toBe("Gesamt 0,86 € Kosten pro Teil (4) 0,22 €");
  });

  it("collapses to one column on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy", narrow: true });

    expect(query(panel, "coinop-run-page").hasAttribute("narrow")).toBe(true);
  });
});
