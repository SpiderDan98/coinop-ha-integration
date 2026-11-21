import { afterEach, describe, expect, it, vi } from "vitest";
import { WsError, recordedBackend } from "./fake-hass";
import { change, click, iconButton, mountPanel, query, queryAll, text } from "./render";

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
  options: { history: ["none", "short", "long"] },
  presets: [
    {
      name: "empty",
      title: "Empty",
      description: "The hub without any Device.",
      selection: { pieces: [], history: "short", open_run: false },
    },
    {
      name: "few-runs",
      title: "3D printer, a few Runs",
      description: "The Prusa with its 7 Runs.",
      selection: { pieces: ["prusa"], history: "short", open_run: false },
    },
    {
      name: "printing-now",
      title: "3D printer, printing now",
      description: "Like a few Runs, with an open Run.",
      selection: { pieces: ["prusa"], history: "short", open_run: true },
    },
    {
      name: "long-history",
      title: "Long history",
      description: "Two years of Runs on two printers.",
      selection: { pieces: ["prusa", "bambu"], history: "long", open_run: false },
    },
    {
      name: "quick-start",
      title: "Quick Start",
      description: "Every Quick Start Piece.",
      selection: {
        pieces: ["anycubic_cloud.3d_printer", "ha_washdata.washing_machine"],
        history: "short",
        open_run: false,
      },
    },
  ],
  preset: "few-runs",
  selection: { pieces: ["prusa"], history: "short", open_run: false },
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

const piece = (dialog: HTMLElement, title: string) => {
  const found = pieces(dialog).find((candidate) => candidate.title === title);
  if (!found) throw new Error(`no Piece "${title}"`);
  return found.box;
};

const presetButton = (dialog: HTMLElement, title: string) => {
  const found = queryAll(dialog, "ha-button.preset").find((button) => text(button) === title);
  if (!found) throw new Error(`no Preset "${title}"`);
  return found;
};

const pickedPreset = (dialog: HTMLElement) => {
  const picked = queryAll(dialog, "ha-button.preset[appearance=filled]").map(text);
  expect(picked.length).toBeLessThan(2);
  return picked[0];
};

const loadButton = (dialog: HTMLElement) => query(dialog, "ha-button.load");

const historySelect = (dialog: HTMLElement) =>
  query(dialog, 'select[name="history"]') as HTMLSelectElement;

const openRunBox = (dialog: HTMLElement) =>
  query(dialog, 'input[name="open_run"]') as HTMLInputElement;

const options = (dialog: HTMLElement) => ({
  history: historySelect(dialog).value,
  openRun: openRunBox(dialog).checked,
});

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

  it("shows the Options above the groups, as the stored selection has them", async () => {
    const backend = devBackend({
      ...SCENARIOS,
      preset: null,
      // happy-dom shows the wrong option when the third or a later one is rendered picked.
      selection: { pieces: ["prusa"], history: "none", open_run: true },
    }).reply("call_service", () => ({}));
    vi.spyOn(window.location, "assign").mockImplementation(() => {});
    const panel = await mountPanel(backend);

    const dialog = await open(panel);

    expect(options(dialog)).toEqual({ history: "none", openRun: true });
    expect([...historySelect(dialog).options].map(text)).toEqual([
      "None",
      "A few weeks",
      "Two years",
    ]);
    expect(text(query(dialog, ".options"))).toContain("An open Run on each Device with history");
    expect(
      historySelect(dialog).compareDocumentPosition(groups(dialog)[0]) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    await click(panel, loadButton(dialog));

    expect(backend.sent("call_service")).toMatchObject([
      { service_data: { pieces: ["prusa"], history: "none", open_run: true } },
    ]);
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

  it("fills in a Preset's Pieces without loading them", async () => {
    const backend = devBackend();
    const panel = await mountPanel(backend);
    const dialog = await open(panel);

    expect(pickedPreset(dialog)).toBe("3D printer, a few Runs");
    expect(text(dialog)).toContain("The Prusa with its 7 Runs.");

    await click(panel, presetButton(dialog, "Quick Start"));

    expect(selected(dialog)).toEqual([
      "Kobra S1 · Anycubic Cloud & LAN",
      "Washing machine · WashData",
    ]);
    expect(pickedPreset(dialog)).toBe("Quick Start");
    expect(text(dialog)).toContain("Every Quick Start Piece.");
    expect(backend.sent("call_service")).toEqual([]);

    await click(panel, piece(dialog, "Garden valve"));

    expect(pickedPreset(dialog)).toBeUndefined();
    expect(text(dialog)).not.toContain("Every Quick Start Piece.");
  });

  it("fills in a Preset's Options, and an Option changed makes the selection one's own", async () => {
    const panel = await mountPanel(devBackend());
    const dialog = await open(panel);

    await click(panel, presetButton(dialog, "Long history"));

    expect(options(dialog)).toEqual({ history: "long", openRun: false });
    expect(selected(dialog)).toEqual(["Prusa MK4", "Bambu Lab X1C"]);

    await click(panel, presetButton(dialog, "3D printer, printing now"));

    expect(options(dialog)).toEqual({ history: "short", openRun: true });

    await click(panel, openRunBox(dialog));

    expect(pickedPreset(dialog)).toBeUndefined();

    await click(panel, presetButton(dialog, "3D printer, a few Runs"));
    await change(panel, historySelect(dialog), "none");

    expect(options(dialog)).toEqual({ history: "none", openRun: false });
    expect(pickedPreset(dialog)).toBeUndefined();
    expect(selected(dialog)).toEqual(["Prusa MK4"]);
  });

  it("picks every Piece or none", async () => {
    const panel = await mountPanel(devBackend());
    const dialog = await open(panel);

    await click(panel, query(dialog, "ha-button.all"));

    expect(selected(dialog)).toHaveLength(6);

    await click(panel, query(dialog, "ha-button.none"));

    expect(selected(dialog)).toEqual([]);
  });

  it("loads the Pieces picked and opens the panel afresh", async () => {
    let answer = () => {};
    const backend = devBackend().reply(
      "call_service",
      () => new Promise<void>((resolve) => (answer = resolve)),
    );
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    await click(panel, piece(dialog, "Washing machine"));
    await click(panel, piece(dialog, "Bambu Lab X1C"));
    await change(panel, historySelect(dialog), "long");
    await click(panel, openRunBox(dialog));

    await click(panel, loadButton(dialog));

    expect(backend.calls.at(-1)).toEqual({
      type: "call_service",
      domain: "coinop_dev",
      service: "load",
      service_data: { pieces: ["prusa", "bambu", "washer"], history: "long", open_run: true },
    });
    expect(loadButton(dialog)).toMatchObject({ loading: true });
    expect(text(loadButton(dialog))).toBe("Loading…");
    expect(assign).not.toHaveBeenCalled();

    answer();
    await click(panel, dialog);

    expect(assign).toHaveBeenCalledWith("/coinop");
  });

  it("loads a Preset picked by its name, so that it is stored as loaded", async () => {
    const backend = devBackend().reply("call_service", () => ({}));
    vi.spyOn(window.location, "assign").mockImplementation(() => {});
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    await click(panel, presetButton(dialog, "Quick Start"));

    await click(panel, loadButton(dialog));

    expect(backend.sent("call_service")).toMatchObject([
      { service: "load", service_data: { preset: "quick-start" } },
    ]);
  });

  it("keeps the Pieces picked and says so when loading fails", async () => {
    const backend = devBackend().reply("call_service", () => {
      throw new WsError("home_assistant_error");
    });
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    await click(panel, piece(dialog, "Garden valve"));

    await click(panel, loadButton(dialog));

    expect(text(dialog)).toContain("The Scenario could not be loaded");
    expect(selected(dialog)).toEqual(["Prusa MK4", "Garden valve"]);
    expect(loadButton(dialog)).toMatchObject({ loading: false, disabled: false });
  });

  it("starts with the groups expanded that have a picked Piece", async () => {
    const panel = await mountPanel(devBackend());

    const dialog = await open(panel);

    expect(groups(dialog).map(({ open }) => open)).toEqual([true, false, false]);
  });
});
