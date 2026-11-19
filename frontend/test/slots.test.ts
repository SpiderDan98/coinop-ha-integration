import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { mountPanel, query, queryAll, text } from "./render";

const split = recorded.splitRun;
const showing = (run = split, language = "en") =>
  recordedBackend({ language })
    .subscription("wattbill/runs/subscribe", () => [{ runs: [run] }])
    .reply("wattbill/runs/get", () => ({ run }));
const item = (panel: Element, id: string) => query(panel, `.item[data-id="${id}"]`);

describe("A Run split across Slots", () => {
  it("is flagged as an estimated split", async () => {
    const run = { ...split, flags: ["estimated_split", "slot_fallback"] };
    for (const [language, labels] of [
      [
        "en",
        "The material was split across Slots by running time: check the quantities|" +
          "A Slot matched no Material: the default Material was charged",
      ],
      [
        "de",
        "Das Material wurde nach Laufzeit auf die Fächer aufgeteilt: Mengen prüfen|" +
          "Ein Fach passte zu keinem Material: das Standardmaterial wurde berechnet",
      ],
    ]) {
      const panel = await mountPanel(showing(run, language), { path: "/run/keychain" });

      expect(queryAll(panel, ".flag .text").map(text).join("|")).toBe(labels);
      panel.remove();
    }
  });

  it("shows each Line Item's Slot as reported and its share", async () => {
    const panel = await mountPanel(showing(), { path: "/run/keychain" });

    const pla = item(panel, "keychain-pla");
    expect(queryAll(pla, ".evidence").map(text)).toEqual([
      "3,000 mm at 1.75 mm and 1.24 g/cm³ · ≈ 75% of the measured total",
      "Slot 1: PLA #1a1a1a",
    ]);
    expect(query(pla, ".slot .swatch").getAttribute("style")).toContain("#1a1a1a");
    expect(text(query(item(panel, "keychain-petg"), ".slot"))).toBe("Slot 2: PETG #ffffff");
  });

  it("shows how far the corrected Line Items are from the measured total", async () => {
    const panel = await mountPanel(showing(), { path: "/run/keychain" });

    expect(text(query(panel, ".split-hint"))).toBe(
      "Estimated split of 12 g measured. The split Line Items add up to 12.9 g (+0.9 g).",
    );
  });

  it("names only the measured total while the split is uncorrected", async () => {
    const run = {
      ...split,
      line_items: split.line_items.map((line) =>
        line.computed ? { ...line, ...line.computed, computed: null } : line,
      ),
    };

    const panel = await mountPanel(showing(run, "de"), { path: "/run/keychain" });

    expect(text(query(panel, ".split-hint"))).toBe("Geschätzte Aufteilung von 12 g gemessen.");
  });

  it("shows no hint for a Run that wasn't split", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    expect(queryAll(panel, ".split-hint, .slot")).toHaveLength(0);
  });
});
