import { describe, expect, it } from "vitest";
import { FakeBackend, WsError, recorded, recordedBackend } from "./fake-hass";
import { mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "wattbill/runs/subscribe";
const CATALOG = "wattbill/catalog/subscribe";
const tiles = (panel: Element) => queryAll(panel, ".tile").map(text);
const [started, updated, ended] = recorded.changes;

describe("Run gallery", () => {
  it("shows a tile per Run, newest first", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(tiles(panel)).toEqual([
      "No image Untitled Run Mini (removed) · Jan 14, 2026 · 0 h 30 min Cancelled €0.07",
      "No image ⚑ 1 Helmet Kobra · Jan 13, 2026 · 9 h 0 min Failed €0.30 Cosplay helmet Gift",
      "No image Benchy Kobra · Jan 12, 2026 · 1 h 15 min Completed €0.86 €0.22 per part × 4 Gift",
    ]);
    expect(text(query(panel, ".head"))).toBe("Runs 3 · €1.23");
  });

  it("follows Runs as they start, progress, end and are deleted", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    backend.push(SUBSCRIBE, started);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 0 h 0 min In progress €0.00 Batch 7",
    );
    backend.push(SUBSCRIBE, updated);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 0 h 45 min In progress €0.03 Batch 7",
    );
    backend.push(SUBSCRIBE, ended);
    await settle(panel);
    expect(tiles(panel)[0]).toBe(
      "No image Untitled Run Kobra · Jan 15, 2026 · 0 h 45 min Completed €0.03 Batch 7",
    );
    backend.push(SUBSCRIBE, { ...ended, change: "deleted" });
    await settle(panel);
    expect(tiles(panel)).toHaveLength(3);
  });

  it("subscribes once to Runs and catalogue, loads the Devices once and never polls", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    panel.hass = backend.update({});
    await settle(panel);

    expect(backend.calls).toEqual([
      { type: SUBSCRIBE },
      { type: CATALOG },
      { type: "wattbill/devices/list" },
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

  it("says when WattBill can't be reached", async () => {
    const backend = new FakeBackend().subscription(SUBSCRIBE, () => {
      throw new WsError("not_loaded");
    });

    const panel = await mountPanel(backend);

    expect(text(panel)).toContain("WattBill could not load its Runs.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }));

    expect(tiles(panel)[1]).toBe(
      "Kein Bild ⚑ 1 Helmet Kobra · 13. Jan. 2026 · 9 Std. 0 Min. Fehlgeschlagen 0,30 € Cosplay helmet Gift",
    );
  });

  it("falls back to English for other languages", async () => {
    const panel = await mountPanel(recordedBackend({ language: "fr" }));

    expect(text(query(panel, ".head"))).toMatch(/^Runs 3/);
  });

  it("collapses to one column on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { narrow: true });

    expect(query(panel, "wattbill-run-gallery").hasAttribute("narrow")).toBe(true);
  });

  it("offers HA's sidebar on narrow screens", async () => {
    const panel = await mountPanel(recordedBackend(), { narrow: true });
    let toggled = false;
    window.addEventListener("hass-toggle-menu", () => (toggled = true), { once: true });

    query(panel, "button.menu").click();

    expect(toggled).toBe(true);
  });
});
