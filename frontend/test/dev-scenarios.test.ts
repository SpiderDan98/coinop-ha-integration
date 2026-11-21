import { afterEach, describe, expect, it, vi } from "vitest";
import { WsError, recordedBackend } from "./fake-hass";
import { click, iconButton, mountPanel, query, queryAll, text } from "./render";

const SCENARIOS = {
  groups: [
    {
      device_type: "3d_printer",
      pieces: [{ name: "prusa", title: "Prusa MK4", description: "7 Runs.", section: "device" }],
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
  ],
  preset: "few-runs",
  selection: { pieces: ["prusa"] },
};

const devBackend = () => {
  const backend = recordedBackend().reply("coinop_dev/scenarios", () => SCENARIOS);
  backend.hass.config.components.push("coinop_dev");
  return backend;
};

const open = async (panel: HTMLElement) => {
  await click(panel, iconButton(panel, "Test data"));
  return query(panel, "coinop-dev-scenarios-dialog");
};

afterEach(() => vi.restoreAllMocks());

describe("Test data", () => {
  it("is offered only in the dev container", async () => {
    const panel = await mountPanel(recordedBackend());

    expect(queryAll(panel, "ha-icon-button.dev")).toHaveLength(0);
  });

  it("lists the Presets with the loaded one marked", async () => {
    const panel = await mountPanel(devBackend());

    const dialog = await open(panel);

    const rows = queryAll(dialog, "li").map(text);
    expect(rows[0]).toContain("Empty");
    expect(rows[0]).not.toContain("loaded");
    expect(rows[1]).toContain("3D printer, a few Runs · loaded");
  });

  it("loads a Preset and opens the panel afresh", async () => {
    const backend = devBackend().reply("call_service", () => ({}));
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});
    const panel = await mountPanel(backend);

    const dialog = await open(panel);
    await click(panel, query(dialog, "li ha-button"));

    expect(backend.calls.at(-1)).toMatchObject({
      type: "call_service",
      domain: "coinop_dev",
      service: "load",
      service_data: { preset: "empty" },
    });
    expect(assign).toHaveBeenCalledWith("/coinop");
  });

  it("says so when loading fails", async () => {
    const backend = devBackend().reply("call_service", () => {
      throw new WsError("home_assistant_error");
    });
    const panel = await mountPanel(backend);

    const dialog = await open(panel);
    await click(panel, query(dialog, "li ha-button"));

    expect(text(dialog)).toContain("The Scenario could not be loaded");
  });
});
