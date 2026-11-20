import { describe, expect, it } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { back, click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "coinop/runs/subscribe";
const RUNS = { path: "/runs" };
const [started] = recorded.changes;

const names = (panel: Element) => queryAll(panel, ".tile .strong").map(text);
const pick = (panel: Element, name: string) =>
  query(
    queryAll(panel, ".pick-tile").find((tile) => text(query(tile, ".strong")) === name) ?? panel,
    "input.pick",
  );
const basket = (panel: Element) => text(query(panel, ".basket"));
const url = () => location.pathname + location.search;

describe("Runs tab", () => {
  it("opens from the toolbar with every Run, its filters and no tiles or charts", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href="/coinop/runs"]`));

    expect(url()).toBe("/coinop/runs");
    expect(query(panel, "a.tab.on").title).toBe("Runs");
    expect(text(query(panel, ".page-title"))).toBe("Runs");
    expect(text(query(panel, "coinop-run-list .head"))).toBe("3 Runs · €1.23");
    expect(names(panel)).toEqual(["Untitled Run", "Helmet", "Benchy"]);
    expect(queryAll(panel, ".name-filter, ha-button.manual-run")).toHaveLength(2);
    expect(queryAll(panel, ".stat, .charts")).toEqual([]);
  });

  it("is a tab of its own on a phone", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { narrow: true });

    await click(panel, query(panel, `a.tab[href="/coinop/runs"]`));

    expect(text(query(panel, "a.tab.on"))).toBe("Läufe");
    expect(names(panel)).toHaveLength(3);
  });

  it("reads its filter from the URL", async () => {
    const panel = await mountPanel(recordedBackend(), {
      path: "/runs?outcome=failed_cancelled&tag=Gift&tag=Cosplay+helmet&untagged=1",
    });

    expect(names(panel)).toEqual(["Untitled Run", "Helmet"]);
    expect((query(panel, ".outcome-filter") as HTMLSelectElement).value).toBe("failed_cancelled");
    expect(text(query(panel, ".tag-filter summary"))).toBe("No tag, Cosplay helmet, Gift");
  });

  it("writes each filter change to the URL, and back and forward step through them", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);

    await fill(panel, query(panel, ".outcome-filter"), "failed");
    expect(url()).toBe("/coinop/runs?outcome=failed");
    await fill(panel, query(panel, ".flagged-filter input"), "on");
    expect(url()).toBe("/coinop/runs?outcome=failed&flagged=1");
    expect(names(panel)).toEqual(["Helmet"]);

    await back(panel);
    expect(url()).toBe("/coinop/runs?outcome=failed");
    expect(names(panel)).toEqual(["Helmet"]);
    expect((query(panel, ".flagged-filter input") as HTMLInputElement).checked).toBe(false);
    await back(panel);
    expect(url()).toBe("/coinop/runs");
    expect(names(panel)).toHaveLength(3);
  });

  it("keeps a name being typed as one step back", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);
    const length = history.length;

    await fill(panel, query(panel, ".name-filter"), "h");
    await fill(panel, query(panel, ".name-filter"), "he");
    await fill(panel, query(panel, ".name-filter"), "hel");

    expect(url()).toBe("/coinop/runs?q=hel");
    expect(history.length).toBe(length + 1);
  });
});

describe("Runs tab filters", () => {
  it("find Runs by name, Device, month, Outcome and Flags, all at once", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);

    await fill(panel, query(panel, ".name-filter"), "hel");
    expect(names(panel)).toEqual(["Helmet"]);
    await fill(panel, query(panel, ".name-filter"), "");

    await fill(panel, query(panel, ".outcome-filter"), "completed");
    expect(names(panel)).toEqual(["Benchy"]);
    await fill(panel, query(panel, ".device-filter"), "device-mini");
    expect(text(panel)).toContain("No Runs match the filters.");
    await fill(panel, query(panel, ".outcome-filter"), "");
    expect(names(panel)).toEqual(["Untitled Run"]);
    await fill(panel, query(panel, ".device-filter"), "");

    await fill(panel, query(panel, ".flagged-filter input"), "on");
    expect(names(panel)).toEqual(["Helmet"]);
    await fill(panel, query(panel, ".flagged-filter input"), "off");

    // Every Run is from January: a month filter would choose nothing.
    expect(queryAll(panel, ".month-filter")).toHaveLength(0);
  });

  it("offers the Runs in progress as an Outcome", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, RUNS);
    backend.push(SUBSCRIBE, started);
    await settle(panel);

    await fill(panel, query(panel, ".outcome-filter"), "open");

    expect(names(panel)).toEqual(["Untitled Run"]);
  });
});

describe("Selection basket", () => {
  it("collects selected final Runs with their names and total", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, RUNS);
    backend.push(SUBSCRIBE, started);
    await settle(panel);
    expect(queryAll(panel, ".basket")).toHaveLength(0);

    await fill(panel, pick(panel, "Helmet"), "on");
    await fill(panel, pick(panel, "Benchy"), "on");

    expect(basket(panel)).toBe("2 Runs €1.16 Benchy, Helmet Cost Statement… Clear Delete");
    expect(queryAll(panel, ".pick-tile.selected")).toHaveLength(2);
    // The open Run can't be selected.
    expect(queryAll(panel, "input.pick")).toHaveLength(3);

    await click(panel, query(panel, ".basket .clear"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
  });

  it("selects all ended Runs the filter shows, and clears them again", async () => {
    const panel = await mountPanel(recordedBackend(), {
      path: "/runs?outcome=failed_cancelled",
    });

    await click(panel, query(panel, ".select-all"));
    expect(basket(panel)).toMatch(/^2 Runs €0.37 Helmet, Untitled Run/);

    await fill(panel, query(panel, ".outcome-filter"), "");
    await click(panel, query(panel, ".select-all"));
    expect(basket(panel)).toMatch(/^3 Runs €1.23 Benchy, Helmet, Untitled Run/);

    await click(panel, query(panel, ".select-all"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
  });

  it("keeps filter and selection while a Run page is open", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);
    await fill(panel, query(panel, ".name-filter"), "e");
    await fill(panel, pick(panel, "Helmet"), "on");

    await click(panel, query(panel, ".tile[href='/coinop/run/benchy']"));
    expect(queryAll(panel, ".basket")).toHaveLength(0);
    expect(query(panel, "a.tab.on").title).toBe("Runs");
    expect(text(query(panel, ".title"))).toBe("Coin-op › Runs › Benchy");
    await click(panel, query(panel, ".title a.runs-link"));

    expect(location.pathname + location.search).toBe("/coinop/runs?q=e");
    expect((query(panel, ".name-filter") as HTMLInputElement).value).toBe("e");
    expect(basket(panel)).toMatch(/^1 Run €0.30 Helmet/);
  });

  it("deletes the selection after confirming what the sensor totals lose", async () => {
    const backend = recordedBackend()
      .reply("coinop/runs/delete_preview", () => recorded.deletePreview)
      .reply("coinop/runs/delete", () => recorded.deletePreview);
    const panel = await mountPanel(backend, RUNS);
    await fill(panel, pick(panel, "Helmet"), "on");
    await fill(panel, pick(panel, "Benchy"), "on");

    await click(panel, query(panel, ".basket .delete"));
    expect(backend.sent("coinop/runs/delete_preview")).toEqual([
      { type: "coinop/runs/delete_preview", run_ids: ["benchy", "helmet"] },
    ]);
    expect(text(query(panel, ".dialog"))).toBe(
      "Delete 2 Runs? The sensor totals drop at once by: Total cost €0.30 Energy in Runs 1.08 kWh " +
        "Material used 0 g Runs 1 Flagged Runs 1 Sensor history is not rewritten. " +
        "This cannot be undone. Cancel Delete",
    );
    await click(panel, query(panel, ".dialog .cancel"));
    expect(backend.sent("coinop/runs/delete")).toEqual([]);

    await click(panel, query(panel, ".basket .delete"));
    await click(panel, query(panel, ".dialog .confirm"));

    expect(backend.sent("coinop/runs/delete")).toEqual([
      { type: "coinop/runs/delete", run_ids: ["benchy", "helmet"] },
    ]);
    expect(queryAll(panel, ".dialog, .basket")).toHaveLength(0);
  });

  it("says when the selection can't be deleted", async () => {
    const backend = recordedBackend().reply("coinop/runs/delete_preview", () => {
      throw new WsError("not_allowed");
    });
    const panel = await mountPanel(backend, RUNS);
    await fill(panel, pick(panel, "Helmet"), "on");

    await click(panel, query(panel, ".basket .delete"));

    expect(basket(panel)).toContain("The selected Runs could not be deleted.");
  });
});
