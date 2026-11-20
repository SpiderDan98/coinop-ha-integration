import { describe, expect, it } from "vitest";
import { FakeBackend, WsError, recorded, recordedBackend } from "./fake-hass";
import { mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "coinop/runs/subscribe";
const CATALOG = "coinop/catalog/subscribe";
const tiles = (panel: Element) => queryAll(panel, ".tile").map(text);
const [started, updated, ended] = recorded.changes;

describe("Run gallery", () => {
  it("shows a tile per Run, newest first", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/runs" });

    expect(tiles(panel)).toEqual([
      "No image Untitled Run Mini (removed) · Jan 14, 2026 · 30 min Cancelled €0.07",
      "⚑ 2 Helmet Kobra · Jan 13, 2026 · 9 h Failed €0.30 Cosplay helmet Gift",
      "Benchy Kobra · Jan 12, 2026 · 1 h 15 min Completed €0.86 €0.22 per part × 4 Gift",
    ]);
    expect(text(query(panel, "coinop-run-list .head"))).toBe("3 Runs · €1.23");
  });

  it("follows Runs as they start, progress, end and are deleted", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    backend.push(SUBSCRIBE, started);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 0 min In progress €0.00 Batch 7",
    );
    backend.push(SUBSCRIBE, updated);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 45 min In progress €0.25 Batch 7",
    );
    backend.push(SUBSCRIBE, ended);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 45 min Completed €0.26 Batch 7",
    );
    backend.push(SUBSCRIBE, { ...ended, change: "deleted" });
    await settle(panel);
    expect(tiles(panel)).toHaveLength(3);
  });

  it("subscribes once to Runs and catalogue, loads Devices and totals once and never polls", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    panel.hass = backend.update({});
    await settle(panel);

    expect(backend.calls).toEqual([
      { type: SUBSCRIBE },
      { type: CATALOG },
      { type: "coinop/devices/list" },
      ...[[], ["month"], ["month", "kind"], ["kind", "material"]].map((group_by) => ({
        type: "coinop/aggregates/get",
        group_by,
      })),
      // Failed + cancelled.
      { type: "coinop/aggregates/get", group_by: [], run_ids: ["helmet", "cancelled"] },
    ]);
  });

  it("stops listening when HA removes the panel", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    panel.remove();
    await settle(panel);

    expect(backend.openSubscriptions(SUBSCRIBE)).toBe(0);
    expect(backend.openSubscriptions(CATALOG)).toBe(0);
  });

  it("says when there are no Runs yet", async () => {
    const backend = new FakeBackend().subscription(SUBSCRIBE, () => [{ runs: [] }]);

    const panel = await mountPanel(backend);

    expect(text(panel)).toContain("No Runs yet.");
  });

  it("says when Coin-op can't be reached", async () => {
    const backend = new FakeBackend().subscription(SUBSCRIBE, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend);

    expect(text(panel)).toContain("Coin-op could not load its Runs.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }));

    expect(tiles(panel)[1]).toBe(
      "⚑ 2 Helmet Kobra · 13. Jan. 2026 · 9 Std. Fehlgeschlagen 0,30 € Cosplay helmet Gift",
    );
  });

  it("falls back to English for other languages", async () => {
    const panel = await mountPanel(recordedBackend({ language: "fr" }));

    expect(text(query(panel, ".recent .head"))).toBe("Recent Runs All Runs");
  });

  it("collapses to one column on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/runs", narrow: true });

    expect(query(panel, "coinop-run-list").hasAttribute("narrow")).toBe(true);
  });

  it("offers HA's sidebar on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { narrow: true });
    let toggled = false;
    window.addEventListener("hass-toggle-menu", () => (toggled = true), { once: true });

    query(panel, "ha-icon-button.menu").click();

    expect(toggled).toBe(true);
  });
});
