import { describe, expect, it } from "vitest";
import { FakeBackend, WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, settle, text } from "./render";

const RUNS = { path: "/runs" };
const CREATE = "coinop/runs/create";
const SUBSCRIBE = "coinop/runs/subscribe";

const creating = (options?: ConstructorParameters<typeof FakeBackend>[0]) => {
  const backend = recordedBackend(options);
  const created = recorded.manualRun;
  return backend
    .reply(CREATE, () => {
      backend.push(SUBSCRIBE, { change: "created", run: created });
      return { run: created };
    })
    .reply("coinop/runs/get", (msg) => {
      const run = [...recorded.runs, created].find((candidate) => candidate.id === msg.run_id);
      if (!run) throw new WsError("not_found");
      return { run };
    });
};

const open = async (panel: HTMLElement) => {
  await click(panel, query(panel, "ha-button.manual-run"));
  return query(panel, ".manual-dialog");
};

const field = (dialog: HTMLElement, name: string) =>
  query(dialog, `[name=${name}]`) as HTMLInputElement;

const enter = async (panel: HTMLElement, dialog: HTMLElement) => {
  await fill(panel, field(dialog, "name"), "Bracket");
  await fill(panel, field(dialog, "started"), "2026-01-15T04:00");
  await fill(panel, field(dialog, "ended"), "2026-01-15T06:00");
};

describe("A manual Run", () => {
  it("asks for name, start, end and Outcome with the Device's Tags pre-filled", async () => {
    const panel = await mountPanel(creating(), RUNS);

    const dialog = await open(panel);

    expect(text(dialog)).toContain("Manual Run");
    // With one Device there is nothing to pick.
    expect(queryAll(dialog, "[name=device]")).toHaveLength(0);
    expect(field(dialog, "name").value).toBe("");
    expect(field(dialog, "started").type).toBe("datetime-local");
    expect(field(dialog, "ended").type).toBe("datetime-local");
    expect(field(dialog, "outcome").value).toBe("completed");
    expect(text(query(dialog, "coinop-tag-input"))).toContain("Batch 7");
  });

  it("asks for the Device when there is more than one", async () => {
    const [kobra] = recorded.devices;
    const mini = { ...kobra, id: "device-mini", name: "Mini" };
    const backend = creating().reply("coinop/devices/list", () => ({ devices: [kobra, mini] }));
    const panel = await mountPanel(backend, RUNS);

    const dialog = await open(panel);

    expect(field(dialog, "device").value).toBe("device-kobra");
    expect(queryAll(field(dialog, "device"), "option").map((option) => text(option))).toEqual([
      "Kobra",
      "Mini",
    ]);
  });

  it("is created with what was entered and opens on its Run page", async () => {
    const backend = creating({ timeZone: "Europe/Berlin" });
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    await enter(panel, dialog);
    await fill(panel, field(dialog, "outcome"), "failed");

    await click(panel, query(dialog, "ha-button.create"));

    expect(backend.calls.filter((call) => call.type === CREATE)).toEqual([
      {
        type: CREATE,
        device_id: "device-kobra",
        name: "Bracket",
        started: "2026-01-15T03:00:00.000Z",
        ended: "2026-01-15T05:00:00.000Z",
        outcome: "failed",
        tags: ["Batch 7"],
      },
    ]);
    expect(queryAll(panel, ".manual-dialog")).toEqual([]);
    expect(location.pathname).toBe("/coinop/run/manual");
    expect(text(query(panel, ".item"))).toContain("Estimated from average power");
  });

  it("needs an end after its start", async () => {
    const backend = creating();
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    const create = query(dialog, "ha-button.create") as HTMLButtonElement;
    expect(create.disabled).toBe(true);

    await enter(panel, dialog);
    expect(create.disabled).toBe(false);
    await fill(panel, field(dialog, "ended"), "2026-01-15T03:00");

    expect(create.disabled).toBe(true);
  });

  it("stays open with a message when it could not be created", async () => {
    const backend = creating().reply(CREATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    await enter(panel, dialog);

    await click(panel, query(dialog, "ha-button.create"));

    expect(text(query(panel, ".manual-dialog"))).toContain("could not be created");
    expect(location.pathname).toBe("/coinop/runs");
  });

  it("asks a washing machine for its Program and nothing printer-only", async () => {
    const backend = creating().reply("coinop/devices/list", () => ({
      devices: [recorded.washer],
    }));
    const panel = await mountPanel(backend, RUNS);

    const dialog = await open(panel);

    expect(
      queryAll(dialog, "input[name], select[name]").map((field) => field.getAttribute("name")),
    ).toEqual(["name", "program", "started", "ended", "outcome"]);
    expect(text(dialog)).toContain("Program");
    expect(text(dialog)).not.toMatch(/print|part/i);
    const known = query(dialog, `datalist#${field(dialog, "program").getAttribute("list")}`);
    expect(queryAll(known, "option").map((option) => option.getAttribute("value"))).toEqual([
      "Cotton 60°",
      "Wool",
      "Eco 40-60",
    ]);
  });

  it("offers a dishwasher's Programs", async () => {
    const backend = creating().reply("coinop/devices/list", () => ({
      devices: [recorded.dishwasher],
    }));
    const panel = await mountPanel(backend, RUNS);

    const dialog = await open(panel);

    const known = query(dialog, `datalist#${field(dialog, "program").getAttribute("list")}`);
    expect(queryAll(known, "option").map((option) => option.getAttribute("value"))).toEqual([
      "Eco 50°",
      "Intensive 70°",
    ]);
  });

  it.each([
    ["an EV charger", recorded.wallbox],
    ["a robotic mower", recorded.mower],
    ["an Other Device that has nothing", recorded.others[0]],
  ])("asks %s for no Program", async (_, device) => {
    const backend = creating().reply("coinop/devices/list", () => ({ devices: [device] }));
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    expect(
      queryAll(dialog, "input[name], select[name]").map((field) => field.getAttribute("name")),
    ).toEqual(["name", "started", "ended", "outcome"]);
    await enter(panel, dialog);

    await click(panel, query(dialog, "ha-button.create"));

    const created = backend.calls.find((call) => call.type === CREATE);
    expect(created).toMatchObject({ device_id: device.id, name: "Bracket" });
    expect(created).not.toHaveProperty("program");
  });

  it("sends a washing machine's Program, known or typed, which names an unnamed Run", async () => {
    const backend = creating().reply("coinop/devices/list", () => ({
      devices: [recorded.washer],
    }));
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    await fill(panel, field(dialog, "started"), "2026-01-15T04:00");
    await fill(panel, field(dialog, "ended"), "2026-01-15T06:00");

    await fill(panel, field(dialog, "program"), " Mix 30° ");

    expect(field(dialog, "name").placeholder).toBe("Mix 30°");
    await click(panel, query(dialog, "ha-button.create"));
    expect(backend.calls.find((call) => call.type === CREATE)).toMatchObject({
      device_id: "device-washer",
      name: null,
      program: "Mix 30°",
    });
  });

  it("sends no Program for a printer", async () => {
    const backend = creating();
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);
    expect(queryAll(dialog, "[name=program]")).toEqual([]);
    await enter(panel, dialog);

    await click(panel, query(dialog, "ha-button.create"));

    expect(backend.calls.find((call) => call.type === CREATE)).not.toHaveProperty("program");
  });

  it("is dropped on cancel", async () => {
    const backend = creating();
    const panel = await mountPanel(backend, RUNS);
    const dialog = await open(panel);

    await click(panel, query(dialog, "ha-button.cancel"));

    expect(queryAll(panel, ".manual-dialog")).toEqual([]);
    expect(backend.calls.some((call) => call.type === CREATE)).toBe(false);
  });
});

describe("The Manual Run dialog", () => {
  it("pre-fills the end with now and points out an end before the start", async () => {
    const panel = await mountPanel(creating(), RUNS);
    const dialog = await open(panel);
    expect(field(dialog, "ended").value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(field(dialog, "ended").max).toBe(field(dialog, "ended").value);

    await fill(panel, field(dialog, "started"), "2026-01-15T04:00");
    await fill(panel, field(dialog, "ended"), "2026-01-15T03:00");

    expect(text(query(dialog, ".times-problem"))).toBe("The end must come after the start.");
    expect((query(dialog, "ha-button.create") as HTMLButtonElement).disabled).toBe(true);
  });

  it("refuses times in the future", async () => {
    const panel = await mountPanel(creating(), RUNS);
    const dialog = await open(panel);

    await fill(panel, field(dialog, "started"), "2099-01-15T04:00");
    await fill(panel, field(dialog, "ended"), "2099-01-15T06:00");

    expect(text(query(dialog, ".times-problem"))).toBe("A Run can't start or end in the future.");
    expect((query(dialog, "ha-button.create") as HTMLButtonElement).disabled).toBe(true);
  });

  it("is cancelled with Escape or a click on the backdrop", async () => {
    const panel = await mountPanel(creating(), RUNS);
    await open(panel);

    query(panel, "coinop-dialog dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
    await settle(panel);
    expect(queryAll(panel, ".manual-dialog")).toEqual([]);

    await open(panel);
    await click(panel, query(panel, "coinop-dialog dialog"));
    expect(queryAll(panel, ".manual-dialog")).toEqual([]);
  });

  it("is closed with its close button", async () => {
    const panel = await mountPanel(creating(), RUNS);
    await open(panel);

    await click(panel, iconButton(panel, "Close"));

    expect(queryAll(panel, ".manual-dialog")).toEqual([]);
  });

  it("is offered on the Runs overview only", async () => {
    const panel = await mountPanel(creating(), { path: "/materials" });

    expect(queryAll(panel, "ha-button.manual-run")).toEqual([]);
  });

  it("opens as a modal dialog with the name focused", async () => {
    const panel = await mountPanel(creating(), RUNS);
    const dialog = await open(panel);

    expect((query(panel, "coinop-dialog dialog") as HTMLDialogElement).open).toBe(true);
    expect(dialog.getRootNode()).toHaveProperty("activeElement", field(dialog, "name"));
  });

  it("explains how to add a Device when there is none", async () => {
    const backend = creating().reply("coinop/devices/list", () => ({ devices: [] }));
    const panel = await mountPanel(backend, RUNS);

    const dialog = await open(panel);

    expect(text(dialog)).toContain("No Devices yet.");
    expect(query(dialog, "a").getAttribute("href")).toBe("/config/integrations/integration/coinop");
    expect(queryAll(dialog, "ha-button.create")).toEqual([]);
  });

  it("opens from the floating button on a narrow screen too", async () => {
    const panel = await mountPanel(creating(), { ...RUNS, narrow: true });

    await click(panel, query(panel, "ha-button.manual-run.fab"));

    expect(queryAll(panel, ".manual-dialog")).toHaveLength(1);
  });
});
