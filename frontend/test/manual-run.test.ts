import { describe, expect, it } from "vitest";
import { FakeBackend, WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, text } from "./render";

const CREATE = "wattbill/runs/create";
const SUBSCRIBE = "wattbill/runs/subscribe";

const creating = (options?: ConstructorParameters<typeof FakeBackend>[0]) => {
  const backend = recordedBackend(options);
  const created = recorded.manualRun;
  return backend
    .reply(CREATE, () => {
      backend.push(SUBSCRIBE, { change: "created", run: created });
      return { run: created };
    })
    .reply("wattbill/runs/get", (msg) => {
      const run = [...recorded.runs, created].find((candidate) => candidate.id === msg.run_id);
      if (!run) throw new WsError("not_found");
      return { run };
    });
};

const open = async (panel: HTMLElement) => {
  await click(panel, query(panel, "button.manual-run"));
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
  it("asks for Device, name, start, end and Outcome with the Device's Tags pre-filled", async () => {
    const panel = await mountPanel(creating());

    const dialog = await open(panel);

    expect(text(dialog)).toContain("Manual Run");
    expect(field(dialog, "device").value).toBe("device-kobra");
    expect(queryAll(field(dialog, "device"), "option").map((option) => text(option))).toEqual([
      "Kobra",
    ]);
    expect(field(dialog, "name").value).toBe("");
    expect(field(dialog, "started").type).toBe("datetime-local");
    expect(field(dialog, "ended").type).toBe("datetime-local");
    expect(field(dialog, "outcome").value).toBe("completed");
    expect(text(query(dialog, "wattbill-tag-input"))).toContain("Batch 7");
  });

  it("is created with what was entered and opens on its Run page", async () => {
    const backend = creating({ timeZone: "Europe/Berlin" });
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    await enter(panel, dialog);
    await fill(panel, field(dialog, "outcome"), "failed");

    await click(panel, query(dialog, "button.create"));

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
    expect(location.pathname).toBe("/wattbill/run/manual");
    expect(text(query(panel, ".item"))).toContain("Estimated from average power");
  });

  it("needs an end after its start", async () => {
    const backend = creating();
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    const create = query(dialog, "button.create") as HTMLButtonElement;
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
    const panel = await mountPanel(backend);
    const dialog = await open(panel);
    await enter(panel, dialog);

    await click(panel, query(dialog, "button.create"));

    expect(text(query(panel, ".manual-dialog"))).toContain("could not be created");
    expect(location.pathname).toBe("/wattbill");
  });

  it("is dropped on cancel", async () => {
    const backend = creating();
    const panel = await mountPanel(backend);
    const dialog = await open(panel);

    await click(panel, query(dialog, "button.cancel"));

    expect(queryAll(panel, ".manual-dialog")).toEqual([]);
    expect(backend.calls.some((call) => call.type === CREATE)).toBe(false);
  });
});
