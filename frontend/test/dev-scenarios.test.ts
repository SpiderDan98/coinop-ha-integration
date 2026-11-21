import { afterEach, describe, expect, it, vi } from "vitest";
import { recordedBackend } from "./fake-hass";
import { click, iconButton, mountPanel, query, queryAll, text } from "./render";

const SCENARIOS = {
  groups: [
    {
      device_type: "3d_printer",
      pieces: [
        { name: "prusa", title: "Prusa MK4", description: "7 Runs.", section: "device" },
        { name: "bambu", title: "Bambu Lab X1C", description: "10 Runs.", section: "device" },
        {
          name: "anycubic_cloud.3d_printer",
          title: "Kobra S1 · Anycubic Cloud & LAN",
          description: "A printer with its plug sensor as meter.",
          section: "quick_start",
        },
      ],
    },
    {
      device_type: "washing_machine",
      pieces: [
        { name: "washer", title: "Washing machine", description: "10 loads.", section: "device" },
        {
          name: "ha_washdata.washing_machine",
          title: "Washing machine · WashData",
          description: "A washing machine WashData follows.",
          section: "quick_start",
        },
      ],
    },
    {
      device_type: "other",
      pieces: [
        {
          name: "irrigation",
          title: "Garden valve",
          description: "6 waterings.",
          section: "device",
        },
      ],
    },
  ],
  presets: [
    {
      name: "empty",
      title: "Empty",
      description: "The hub without any Device.",
      selection: { pieces: [] },
    },
    {
      name: "few-runs",
      title: "3D printer, a few Runs",
      description: "The Prusa with its 7 Runs.",
      selection: { pieces: ["prusa"] },
    },
    {
      name: "quick-start",
      title: "Quick Start",
      description: "Every Quick Start Piece.",
      selection: { pieces: ["anycubic_cloud.3d_printer", "ha_washdata.washing_machine"] },
    },
  ],
  preset: "few-runs",
  selection: { pieces: ["prusa"] },
};

const devBackend = (scenarios: object = SCENARIOS) => {
  const backend = recordedBackend().reply("coinop_dev/scenarios", () => scenarios);
  backend.hass.config.components.push("coinop_dev");
  return backend;
};

const open = async (panel: HTMLElement) => {
  await click(panel, iconButton(panel, "Test data"));
  return query(panel, "coinop-dev-scenarios-dialog");
};

const groups = (dialog: HTMLElement) => queryAll(dialog, "details.group") as HTMLDetailsElement[];

const group = (dialog: HTMLElement, name: string) => {
  const found = groups(dialog).find((candidate) =>
    text(query(candidate, "summary")).includes(name),
  );
  if (!found) throw new Error(`no group "${name}"`);
  return found;
};

const groupBox = (dialog: HTMLElement, name: string) =>
  query(query(group(dialog, name), "summary"), "input") as HTMLInputElement;

const pieces = (root: HTMLElement) =>
  queryAll(root, ".piece").map((piece) => ({
    title: text(query(piece, "strong")),
    box: query(piece, "input") as HTMLInputElement,
  }));

const selected = (dialog: HTMLElement) =>
  pieces(dialog)
    .filter(({ box }) => box.checked)
    .map(({ title }) => title);

afterEach(() => vi.restoreAllMocks());

describe("Test data", () => {
  it("is offered only in the dev container", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(queryAll(panel, "ha-icon-button.dev")).toHaveLength(0);
  });

  it("lists the groups and their Pieces with the stored selection checked", async () => {
    const panel = await mountPanel(devBackend());

    const dialog = await open(panel);

    expect(groups(dialog).map((found) => text(query(found, "summary")))).toEqual([
      "3D printers 1 of 3",
      "Washing machines 0 of 2",
      "Other 0 of 1",
    ]);
    expect(text(group(dialog, "3D printers"))).toContain(
      "Devices with history Prusa MK4 7 Runs. Bambu Lab X1C 10 Runs. " +
        "Quick Start Kobra S1 · Anycubic Cloud & LAN A printer with its plug sensor as meter.",
    );
    expect(selected(dialog)).toEqual(["Prusa MK4"]);
  });

  it("shows on each group's checkbox whether all, some or none of its Pieces are picked", async () => {
    const panel = await mountPanel(
      devBackend({ ...SCENARIOS, selection: { pieces: ["prusa", "washer", "irrigation"] } }),
    );

    const dialog = await open(panel);

    expect(groupBox(dialog, "3D printers")).toMatchObject({ checked: false, indeterminate: true });
    expect(groupBox(dialog, "Washing machines")).toMatchObject({
      checked: false,
      indeterminate: true,
    });
    expect(groupBox(dialog, "Other")).toMatchObject({ checked: true, indeterminate: false });

    await click(panel, groupBox(dialog, "Washing machines"));
    await click(panel, groupBox(dialog, "Other"));

    expect(groupBox(dialog, "Washing machines")).toMatchObject({
      checked: true,
      indeterminate: false,
    });
    expect(groupBox(dialog, "Other")).toMatchObject({ checked: false, indeterminate: false });
    expect(text(query(group(dialog, "Washing machines"), "summary"))).toContain("2 of 2");
    expect(selected(dialog)).toEqual([
      "Prusa MK4",
      "Washing machine",
      "Washing machine · WashData",
    ]);
  });

  it("selects a whole group, and clears it once it is complete", async () => {
    const panel = await mountPanel(devBackend());
    const dialog = await open(panel);

    await click(panel, groupBox(dialog, "3D printers"));

    expect(selected(dialog)).toEqual([
      "Prusa MK4",
      "Bambu Lab X1C",
      "Kobra S1 · Anycubic Cloud & LAN",
    ]);

    await click(panel, groupBox(dialog, "3D printers"));

    expect(selected(dialog)).toEqual([]);
    expect(groupBox(dialog, "3D printers")).toMatchObject({ checked: false, indeterminate: false });
  });

  it("starts with the groups expanded that have a picked Piece", async () => {
    const panel = await mountPanel(devBackend());

    const dialog = await open(panel);

    expect(groups(dialog).map(({ open }) => open)).toEqual([true, false, false]);
  });
});
