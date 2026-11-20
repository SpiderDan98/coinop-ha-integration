// The panel's editing rule (ADR 0008): pages show stored data read-only, and everything
// is edited in a dialog whose fields come from `src/fields.ts`.
import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, iconButton, mountPanel, query, queryAll } from "./render";

const CONTROLS = "input, select, textarea";
/** Controls that change what a page shows, not what is stored. */
const VIEW_CONTROLS = "[type=file], .filters *, .pager *, .pick";

const statementBackend = () =>
  recordedBackend().subscription("coinop/runs/subscribe", () => [
    { runs: recorded.snapshot.runs.map((run) => ({ ...run, finalised: true })) },
  ]);

/** Every dialog that edits, with the page it is on and what opens it. */
const DIALOGS: [name: string, path: string, open: (panel: Element) => HTMLElement][] = [
  ["Manual Run", "/runs", (panel) => query(panel, "ha-button.manual-run")],
  ["a Run's fields", "/run/benchy", (panel) => query(panel, ".facts ha-icon-button.edit")],
  ["a Line Item", "/run/benchy", (panel) => query(panel, ".item ha-icon-button.edit")],
  ["a new Material Line Item", "/run/benchy", (panel) => query(panel, "ha-button.add-material")],
  ["a new Other Line Item", "/run/benchy", (panel) => query(panel, "ha-button.add-other")],
  ["a Line Item from a template", "/run/benchy", (panel) => query(panel, ".add-template")],
  ["a Device's settings", "/devices", (panel) => iconButton(panel, "Edit settings of Kobra")],
  ["a new Material", "/materials", (panel) => query(panel, "ha-button.new-material")],
  ["a Material", "/materials", (panel) => query(panel, ".material ha-icon-button.edit")],
  ["a new Tag", "/tags", (panel) => query(panel, "ha-button.new-tag")],
  ["a Tag's name", "/tags", (panel) => query(panel, ".tag ha-icon-button.rename")],
  ["a new Line Item Template", "/templates", (panel) => query(panel, "ha-button.new-template")],
  ["a Line Item Template", "/templates", (panel) => query(panel, ".template .edit")],
];

/** The Tag input keeps its own control in its shadow root; it is the field's control. */
const owner = (control: HTMLElement) => {
  const root = control.getRootNode();
  return root instanceof ShadowRoot && root.host.localName === "coinop-tag-input"
    ? root.host
    : control;
};

describe("Editing", () => {
  it.each([
    "",
    "/runs",
    "/run/benchy",
    "/devices",
    "/materials",
    "/tags",
    "/templates",
    "/analysis",
  ])("happens in no page itself: %s shows what is stored read-only", async (path) => {
    const panel = await mountPanel(recordedBackend(), { path });

    expect(queryAll(panel, "coinop-dialog")).toEqual([]);
    expect(queryAll(panel, CONTROLS).filter((control) => !control.matches(VIEW_CONTROLS))).toEqual(
      [],
    );
  });

  it.each(DIALOGS)("of %s is in a dialog of full-width fields", async (_, path, open) => {
    const panel = await mountPanel(recordedBackend(), { path });

    await click(panel, open(panel));

    const dialog = query(panel, "coinop-dialog");
    const controls = queryAll(dialog, CONTROLS);
    expect(controls.length).toBeGreaterThan(0);
    // A table's cells share its width instead: the Program Defaults.
    expect(controls.filter((control) => !owner(control).closest(".field, .check, td"))).toEqual([]);
  });

  it.each(DIALOGS)("of %s saves nothing before its saving button", async (_, path, open) => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path });
    await click(panel, open(panel));
    const sent = backend.calls.filter(({ type }) => !/\/(get|list|types|suggestions)$/.test(type));

    expect(queryAll(panel, "coinop-dialog [slot=footer] ha-button")).toHaveLength(2);
    await click(panel, query(panel, "coinop-dialog ha-button.cancel"));

    expect(queryAll(panel, "coinop-dialog")).toEqual([]);
    expect(
      backend.calls.filter(({ type }) => !/\/(get|list|types|suggestions)$/.test(type)),
    ).toEqual(sent);
  });

  it("keeps the page behind its dialog from scrolling", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/tags" });
    const page = document.documentElement;

    await click(panel, query(panel, "ha-button.new-tag"));
    expect(page.style.overflow).toBe("hidden");

    await click(panel, query(panel, "coinop-dialog ha-button.cancel"));
    expect(page.style.overflow).toBe("");
  });

  it("of a Cost Statement's options is in a dialog of full-width fields", async () => {
    const panel = await mountPanel(statementBackend(), { path: "/runs" });
    await click(panel, query(panel, "input.pick"));

    await click(panel, query(panel, ".basket .statement"));

    const controls = queryAll(query(panel, ".statement-dialog"), CONTROLS);
    expect(controls.length).toBeGreaterThan(0);
    expect(controls.filter((control) => !control.closest(".field, .check"))).toEqual([]);
  });
});
