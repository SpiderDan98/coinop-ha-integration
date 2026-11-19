import { describe, expect, it } from "vitest";
import type { Message } from "../src/hass";
import { recorded, recordedBackend } from "./fake-hass";
import { change, click, mountPanel, query, queryAll, text } from "./render";

const UPDATE = "wattbill/runs/update";
const SUBSCRIBE = "wattbill/runs/subscribe";
const [started] = recorded.changes;

/** Answers corrections with the recorded Run plus what was changed. */
const correcting = (options?: Parameters<typeof recordedBackend>[0]) =>
  recordedBackend(options).reply(UPDATE, (msg) => {
    const changes: Partial<Message> = { ...msg };
    delete changes.type;
    return { run: { ...recorded.run(String(msg.run_id)), ...changes } };
  });

describe("Correcting a Run", () => {
  it("names every kind of Flag", async () => {
    const flags = [
      "consumption_gap",
      "meter_reset",
      "price_gap",
      "usage_missing",
      "spoolman_unreachable",
      "spoolman_no_price",
    ];
    const run = { ...recorded.run("benchy"), flags };
    for (const [language, labels] of [
      [
        "en",
        "The energy meter or power sensor reported nothing for part of the Run|" +
          "The energy meter was reset during the Run|" +
          "The electricity price was unavailable for part of the Run|" +
          "No material usage was reported: enter the quantity|" +
          "Spoolman couldn't be reached at the end of the Run: the last price read applies|" +
          "Spoolman has no price for the Filament: enter the unit price",
      ],
      [
        "de",
        "Der Energiezähler oder Leistungssensor hat während eines Teils des Laufs nichts gemeldet|" +
          "Der Energiezähler wurde während des Laufs zurückgesetzt|" +
          "Der Strompreis war während eines Teils des Laufs nicht verfügbar|" +
          "Es wurde kein Materialverbrauch gemeldet: Menge eintragen|" +
          "Spoolman war am Ende des Laufs nicht erreichbar: Es gilt der zuletzt gelesene Preis|" +
          "Spoolman hat keinen Preis für das Filament: Stückpreis eintragen",
      ],
    ]) {
      const backend = recordedBackend({ language }).reply("wattbill/runs/get", () => ({ run }));
      const panel = await mountPanel(backend, { path: "/run/benchy" });

      expect(queryAll(panel, ".flag .text").map(text).join("|")).toBe(labels);
      panel.remove();
    }
  });

  it("saves each field as soon as it changes", async () => {
    const backend = correcting();
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await change(panel, query(panel, "input[name=name]"), "Benchy XL");
    await change(panel, query(panel, "textarea[name=note]"), "Printed for a friend");
    await change(panel, query(panel, "select[name=outcome]"), "failed");

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, run_id: "benchy", name: "Benchy XL" },
      { type: UPDATE, run_id: "benchy", note: "Printed for a friend" },
      { type: UPDATE, run_id: "benchy", outcome: "failed" },
    ]);
    expect(text(query(panel, ".runbar"))).toMatch(/^Failed/);
  });

  it("shows the stored fields and says times never recalculate costs", async () => {
    const panel = await mountPanel(correcting(), { path: "/run/benchy" });

    expect((query(panel, "input[name=name]") as HTMLInputElement).value).toBe("Benchy");
    expect((query(panel, "textarea[name=note]") as HTMLTextAreaElement).value).toBe(
      "Four on one plate",
    );
    expect((query(panel, "input[name=part_count]") as HTMLInputElement).value).toBe("4");
    expect((query(panel, "input[name=started]") as HTMLInputElement).value).toBe(
      "2026-01-12T10:00",
    );
    expect(text(query(panel, ".facts"))).toContain(
      "Changing start, end or Outcome never recalculates costs.",
    );
  });

  it("enters times in Home Assistant's time zone", async () => {
    const backend = correcting({ timeZone: "Europe/Berlin" });
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect((query(panel, "input[name=ended]") as HTMLInputElement).value).toBe("2026-01-12T12:15");

    await change(panel, query(panel, "input[name=started]"), "2026-01-12T10:30");

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, run_id: "benchy", started: "2026-01-12T09:30:00.000Z" },
    ]);
  });

  it("divides the total by the Part Count", async () => {
    const backend = correcting();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(text(query(panel, ".totals"))).toBe("Total €0.86 Cost per part (4) €0.22");

    backend.reply(UPDATE, () => ({
      run: { ...recorded.run("benchy"), part_count: 2, cost_per_part: 0.43 },
    }));
    await change(panel, query(panel, "input[name=part_count]"), "2");

    expect(backend.sent(UPDATE)).toEqual([{ type: UPDATE, run_id: "benchy", part_count: 2 }]);
    expect(text(query(panel, ".totals"))).toBe("Total €0.86 Cost per part (2) €0.43");
  });

  it("keeps the Part Count a whole number of at least one", async () => {
    const backend = correcting();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const input = query(panel, "input[name=part_count]") as HTMLInputElement;

    await change(panel, input, "0");
    await change(panel, input, "1.5");

    expect(backend.sent(UPDATE)).toEqual([]);
    expect(input.value).toBe("4");
  });

  it("locks times and Outcome of an open Run and offers End Run now", async () => {
    const backend = correcting().subscription(SUBSCRIBE, () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    backend.reply("wattbill/runs/end", () => ({
      run: { ...recorded.run("print-live"), ended: "2026-01-15T10:45:00+00:00" },
    }));
    const panel = await mountPanel(backend, { path: "/run/print-live" });

    for (const name of ["started", "ended", "outcome"]) {
      expect(query(panel, `[name=${name}]`).hasAttribute("disabled")).toBe(true);
    }
    expect(query(panel, "input[name=name]").hasAttribute("disabled")).toBe(false);

    await click(panel, query(panel, "ha-button.end-run"));

    expect(backend.calls.at(-1)).toEqual({ type: "wattbill/runs/end", run_id: "print-live" });
    expect(queryAll(panel, "ha-button.end-run")).toHaveLength(0);
  });

  it("lists open Flags until they are marked checked", async () => {
    const backend = correcting().reply("wattbill/runs/clear_flag", () => ({
      run: { ...recorded.run("helmet"), flags: [] },
    }));
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    expect(text(query(panel, ".flags"))).toBe(
      "⚑ The Device reported a fault Mark checked ⚑ No Material was known for the usage: pick the Material Mark checked",
    );

    await click(panel, query(panel, ".flag ha-button"));

    expect(backend.calls.at(-1)).toEqual({
      type: "wattbill/runs/clear_flag",
      run_id: "helmet",
      flag: "fault",
    });
    expect(queryAll(panel, ".flag")).toHaveLength(0);
  });

  it("shows when a correction could not be saved", async () => {
    const backend = correcting().reply(UPDATE, () => Promise.reject(new Error("invalid_format")));
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await change(panel, query(panel, "input[name=ended]"), "2026-01-01T10:00");

    expect(text(query(panel, ".facts"))).toContain("This change could not be saved.");
  });
});

describe("Deleting a Run", () => {
  const deleting = () =>
    correcting()
      .reply("wattbill/runs/delete_preview", () => recorded.deletePreview)
      .reply("wattbill/runs/delete", () => recorded.deletePreview);

  it("says how much the sensor totals drop before deleting", async () => {
    const backend = deleting();
    const panel = await mountPanel(backend, { path: "/run/helmet" });

    await click(panel, query(panel, "ha-button.delete-run"));

    expect(backend.calls.at(-1)).toEqual({
      type: "wattbill/runs/delete_preview",
      run_ids: ["helmet"],
    });
    expect(text(query(panel, ".dialog"))).toBe(
      "Delete “Helmet”? The sensor totals drop at once by: " +
        "Total cost €0.30 Energy in Runs 1.08 kWh Material used 0 g Runs 1 Flagged Runs 1 " +
        "Sensor history is not rewritten. This cannot be undone. Cancel Delete",
    );
  });

  it("deletes only when confirmed and then returns to all Runs", async () => {
    const backend = deleting();
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    await click(panel, query(panel, "ha-button.delete-run"));

    await click(panel, query(panel, ".dialog ha-button.cancel"));
    expect(queryAll(panel, ".dialog")).toHaveLength(0);
    expect(backend.sent("wattbill/runs/delete")).toEqual([]);

    await click(panel, query(panel, "ha-button.delete-run"));
    await click(panel, query(panel, ".dialog ha-button.confirm"));
    expect(backend.sent("wattbill/runs/delete")).toEqual([
      { type: "wattbill/runs/delete", run_ids: ["helmet"] },
    ]);
    expect(location.pathname).toBe("/wattbill");
  });

  it("is offered only once the Run is final", async () => {
    const backend = deleting().subscription(SUBSCRIBE, () => [
      { runs: [...recorded.snapshot.runs, started.run] },
    ]);
    const panel = await mountPanel(backend, { path: "/run/print-live" });

    expect(query(panel, "ha-button.delete-run").hasAttribute("disabled")).toBe(true);
  });

  it("is in German when Home Assistant is", async () => {
    const german = recordedBackend({ language: "de" }).reply(
      "wattbill/runs/delete_preview",
      () => recorded.deletePreview,
    );
    const panel = await mountPanel(german, { path: "/run/helmet" });

    await click(panel, query(panel, "ha-button.delete-run"));

    expect(text(query(panel, ".dialog"))).toContain(
      "Gesamtkosten 0,30 € Energie in Läufen 1,08 kWh Materialverbrauch 0 g Läufe 1",
    );
  });
});

describe("Gallery tiles", () => {
  it("show the cost per part when a Run made several parts, and open Flags", async () => {
    const panel = await mountPanel(recordedBackend());
    const [, helmet, benchy] = queryAll(panel, ".tile");

    expect(text(benchy)).toContain("€0.22 per part × 4");
    expect(text(helmet)).not.toContain("per part");
    expect(text(query(helmet, ".tile-flags"))).toBe("⚑ 2");
    expect(queryAll(benchy, ".tile-flags")).toHaveLength(0);
  });
});

describe("Saving a correction", () => {
  it("confirms it for a moment where the page says every change is saved", async () => {
    const panel = await mountPanel(correcting(), { path: "/run/benchy" });
    expect(text(query(panel, ".saves"))).toBe("Every change saves at once.");

    await change(panel, query(panel, "input[name=name]"), "Benchy v2");

    expect(text(query(panel, ".saves"))).toBe("Saved.");
  });
});
