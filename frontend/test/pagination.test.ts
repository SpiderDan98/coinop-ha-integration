import { beforeEach, describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const RUNS = { path: "/runs" };
const names = (panel: Element) => queryAll(panel, ".tile .strong").map(text);
const range = (panel: Element) => text(query(panel, ".pager .range"));
const disabled = (button: HTMLElement) => button.hasAttribute("disabled");

/** "Run 01" to "Run 60", each started a minute after the one before. */
const sixtyRuns = () => {
  const [run] = recorded.snapshot.runs;
  if (!run) throw new Error("no recorded Run");
  const runs = Array.from({ length: 60 }, (_, index) => ({
    ...run,
    id: `run-${index + 1}`,
    name: `Run ${String(index + 1).padStart(2, "0")}`,
    started: new Date(Date.UTC(2026, 0, 1, 8, index)).toISOString(),
  }));
  return recordedBackend()
    .subscription("coinop/runs/subscribe", () => [{ runs }])
    .reply("coinop/aggregates/get", () => ({ groups: [] }));
};

beforeEach(() => localStorage.clear());

describe("Pagination", () => {
  it("shows a list a page at a time", async () => {
    const panel = await mountPanel(sixtyRuns(), RUNS);

    expect(names(panel)).toHaveLength(25);
    expect(names(panel)[0]).toBe("Run 60");
    expect(range(panel)).toBe("1–25 of 60");
    expect(disabled(iconButton(panel, "Previous page"))).toBe(true);

    await click(panel, iconButton(panel, "Next page"));
    expect(names(panel)[0]).toBe("Run 35");
    expect(range(panel)).toBe("26–50 of 60");

    await click(panel, iconButton(panel, "Last page"));
    expect(names(panel)).toHaveLength(10);
    expect(range(panel)).toBe("51–60 of 60");
    expect(disabled(iconButton(panel, "Next page"))).toBe(true);

    await click(panel, iconButton(panel, "First page"));
    expect(range(panel)).toBe("1–25 of 60");
  });

  it("pages the table like the gallery", async () => {
    const panel = await mountPanel(sixtyRuns(), RUNS);

    await click(panel, query(panel, ".show-table"));
    await click(panel, iconButton(panel, "Next page"));

    expect(queryAll(panel, "tr.run")).toHaveLength(25);
    expect(text(query(panel, ".table .pager .range"))).toBe("26–50 of 60");
  });

  it("starts at the first page again when the filter changes", async () => {
    const panel = await mountPanel(sixtyRuns(), RUNS);
    await click(panel, iconButton(panel, "Last page"));

    await fill(panel, query(panel, ".name-filter"), "Run 3");

    expect(names(panel)[0]).toBe("Run 39");
    expect(queryAll(panel, ".pager")).toHaveLength(0);
  });

  it("remembers the page size and keeps the first Run shown on the page", async () => {
    const backend = sixtyRuns();
    const panel = await mountPanel(backend, RUNS);
    await click(panel, iconButton(panel, "Next page"));

    await fill(panel, query(panel, ".pager select"), "50");

    expect(names(panel)).toHaveLength(50);
    expect(range(panel)).toBe("1–50 of 60");
    panel.remove();
    expect(range(await mountPanel(backend, RUNS))).toBe("1–50 of 60");
  });

  it("has no controls for a list that fits one page", async () => {
    const panel = await mountPanel(recordedBackend(), RUNS);

    expect(queryAll(panel, ".pager")).toHaveLength(0);
  });

  it("pages the catalogue tables", async () => {
    const tags = Array.from({ length: 30 }, (_, index) => `Tag ${index + 1}`);
    const backend = recordedBackend()
      .subscription("coinop/catalog/subscribe", () => [{ ...recorded.catalog.filled, tags }])
      .reply("coinop/aggregates/get", () => ({ groups: [] }));
    const panel = await mountPanel(backend, { path: "/tags" });

    expect(queryAll(panel, "tr.tag")).toHaveLength(25);
    await click(panel, iconButton(panel, "Next page"));
    expect(queryAll(panel, "tr.tag")).toHaveLength(5);
    expect(range(panel)).toBe("26–30 of 30");
  });
});
