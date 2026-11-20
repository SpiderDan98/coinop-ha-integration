import { beforeEach, describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const RUNS = { path: "/runs" };
const [started] = recorded.changes;

const view = (panel: Element, name: "gallery" | "table") =>
  query(panel, `.view-toggle button.show-${name}`);
const head = (panel: Element) => queryAll(panel, "wattbill-run-list thead th").map(text);
const rows = (panel: Element) => queryAll(panel, "wattbill-run-list tbody tr.run").map(text);
const row = (panel: Element, name: string) =>
  queryAll(panel, "tr.run").find((candidate) => text(query(candidate, ".name")).startsWith(name)) ??
  panel;
const basket = (panel: Element) => text(query(panel, ".basket"));

beforeEach(() => localStorage.clear());

describe("Runs table", () => {
  it("shows the gallery until the table is chosen", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);
    expect(queryAll(panel, ".gallery")).toHaveLength(1);
    expect(view(panel, "gallery").getAttribute("aria-pressed")).toBe("true");

    await click(panel, view(panel, "table"));

    expect(queryAll(panel, ".gallery")).toEqual([]);
    expect(view(panel, "table").getAttribute("aria-pressed")).toBe("true");
    expect(head(panel)).toEqual([
      "",
      "",
      "Name",
      "Device",
      "Start",
      "Duration",
      "Outcome",
      "Tags",
      "Flags",
      "Total",
      "Per part",
    ]);
    expect(rows(panel)).toEqual([
      "No image Untitled Run Mini (removed) Jan 14, 2026, 10:00 AM 30 min Cancelled €0.07",
      "Helmet Kobra Jan 13, 2026, 10:00 AM 9 h Failed Cosplay helmet Gift ⚑ 2 €0.30",
      "Benchy Kobra Jan 12, 2026, 10:00 AM 1 h 15 min Completed Gift €0.86 €0.22",
    ]);
  });

  it("is remembered in the browser", async () => {
    const first = await mountPanel(recordedBackend(), RUNS);
    await click(first, view(first, "table"));
    first.remove();

    const panel = await mountPanel(recordedBackend(), RUNS);

    expect(rows(panel)).toHaveLength(3);
    await click(panel, view(panel, "gallery"));
    expect(queryAll(panel, ".gallery")).toHaveLength(1);
  });

  it("selects only final Runs, one by one or all ended at once", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, RUNS);
    await click(panel, view(panel, "table"));
    backend.push("wattbill/runs/subscribe", started);
    await settle(panel);

    expect(queryAll(panel, "tr.run input.pick")).toHaveLength(3);
    await fill(panel, query(row(panel, "Helmet"), "input.pick"), "on");
    expect(basket(panel)).toMatch(/^1 Run €0.30 Helmet/);
    expect(queryAll(panel, "tr.run.selected")).toHaveLength(1);

    await click(panel, query(panel, ".select-all"));
    expect(basket(panel)).toMatch(/^3 Runs €1.23 Benchy, Helmet, Untitled Run/);
  });

  it("keeps filter and selection when switching between gallery and table", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);
    await fill(panel, query(panel, ".outcome-filter"), "failed");
    await fill(panel, query(panel, "input.pick"), "on");

    await click(panel, view(panel, "table"));

    expect(rows(panel)).toHaveLength(1);
    expect((query(panel, "tr.run input.pick") as HTMLInputElement).checked).toBe(true);
    await click(panel, view(panel, "gallery"));
    expect((query(panel, ".pick-tile input.pick") as HTMLInputElement).checked).toBe(true);
    expect(basket(panel)).toMatch(/^1 Run €0.30 Helmet/);
  });

  it("opens a Run's page from its row, but not from its checkbox", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);
    await click(panel, view(panel, "table"));

    await click(panel, query(row(panel, "Helmet"), "input.pick"));
    expect(location.pathname).toBe("/wattbill/runs");

    await click(panel, query(row(panel, "Benchy"), ".outcome"));
    expect(location.pathname).toBe("/wattbill/run/benchy");
  });

  it("shows fewer columns on a phone", async () => {
    const panel = await mountPanel(recordedBackend(), { ...RUNS, narrow: true });
    await click(panel, view(panel, "table"));

    expect(head(panel)).toEqual(["", "Name", "Total"]);
    expect(rows(panel)[1]).toBe("Helmet Kobra · Jan 13, 2026 €0.30");
  });
});
