import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, text } from "./render";

const { breadMaker, wheatLoaf, loaves } = recorded;
const UPDATE = "coinop/runs/update";

/** The bread maker next to Kobra, with its two loaves next to Kobra's Runs. */
const baking = () =>
  recordedBackend()
    .reply("coinop/devices/list", () => ({ devices: [...recorded.devices, breadMaker] }))
    .subscription("coinop/runs/subscribe", () => [
      { runs: [...recorded.snapshot.runs, ...loaves.runs] },
    ])
    .reply("coinop/runs/get", () => ({ run: wheatLoaf }))
    .reply(UPDATE, (msg) => ({ run: { ...wheatLoaf, program: msg.program } }));
const names = (panel: Element) => queryAll(panel, ".tile .strong").map(text);

describe("An Other Device with a Program and no Doses", () => {
  it("is listed under its Type Name with its Program rows and no Dose list", async () => {
    const backend = recordedBackend().reply("coinop/devices/list", () => ({
      devices: [breadMaker],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["Bread maker"]);
    expect(queryAll(panel, ".device").map(text)).toEqual([
      "Bread maker " +
        "Status sensor.bread_maker_status " +
        "Program sensor.bread_maker_program " +
        "Consumption source Per Program (kWh in the Program Defaults) " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Program rows Whole wheat " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
  });

  it("has Program Defaults that are just the kWh per Program", async () => {
    const backend = recordedBackend().reply("coinop/devices/list", () => ({
      devices: [breadMaker],
    }));
    const panel = await mountPanel(backend, { path: "/devices" });

    await click(panel, iconButton(panel, "Edit settings of Bread maker"));

    const dialog = query(panel, ".settings-dialog");
    expect(queryAll(dialog, ".program-defaults th").map(text)).toEqual([
      "Program",
      "Electricity (kWh)",
    ]);
    expect(queryAll(dialog, ".program-defaults tbody tr").map(text)).toEqual([
      "Default",
      "Basic Suggested",
      "Whole wheat",
    ]);
    expect(
      queryAll(dialog, ".program-defaults tbody input").map(
        (cell) => (cell as HTMLInputElement).value,
      ),
    ).toEqual(["0.4", "", "0.5"]);
    expect(queryAll(dialog, ".doses")).toEqual([]);
    expect(text(query(dialog, ".program-defaults .hint"))).not.toMatch(/Dose|dosed|litres/);
  });

  it("offers its Programs for a manual Run", async () => {
    const backend = recordedBackend().reply("coinop/devices/list", () => ({
      devices: [breadMaker],
    }));
    const panel = await mountPanel(backend, { path: "/runs" });

    await click(panel, query(panel, "ha-button.manual-run"));

    const dialog = query(panel, ".manual-dialog");
    expect(
      queryAll(dialog, "input[name], select[name]").map((field) => field.getAttribute("name")),
    ).toEqual(["name", "program", "started", "ended", "outcome"]);
    const known = query(dialog, `datalist#${query(dialog, "[name=program]").getAttribute("list")}`);
    expect(queryAll(known, "option").map((option) => option.getAttribute("value"))).toEqual([
      "Basic",
      "Whole wheat",
    ]);
  });

  it("shows a Run's Program and its kWh from the Program's row, and corrects the Program", async () => {
    const backend = baking();
    const panel = await mountPanel(backend, { path: "/run/wheat-loaf" });

    expect(text(query(panel, ".facts .program"))).toBe("Whole wheat");
    expect(text(query(panel, ".facts dl"))).not.toContain("Part Count");
    expect(queryAll(panel, ".kind .between").map(text)).toEqual([
      "Electricity €0.15",
      "Material €0.00",
      "Other €0.00",
    ]);
    expect(text(query(panel, ".kind .item .label"))).toContain("From the Program Defaults");
    await click(panel, query(panel, ".facts ha-icon-button.edit"));
    await fill(panel, query(panel, ".run-dialog [name=program]"), "Basic");
    await click(panel, query(panel, ".run-dialog ha-button.save"));

    expect(backend.sent(UPDATE)).toEqual([
      { type: UPDATE, run_id: "wheat-loaf", program: "Basic" },
    ]);
    expect(text(query(panel, ".facts .program"))).toBe("Basic");
  });

  it("has its Runs in the Program filter, those without a Program included", async () => {
    const panel = await mountPanel(baking(), { path: "/runs" });
    const program = query(panel, ".program-filter") as HTMLSelectElement;

    expect([...program.options].map(text)).toEqual(["All Programs", "Whole wheat", "No Program"]);
    await fill(panel, program, program.options[2].value);

    expect(location.pathname + location.search).toBe("/coinop/runs?no_program=1");
    expect(names(panel)).toEqual(["Untitled Run"]);
  });

  it("has its Runs in the Analysis by Program", async () => {
    const panel = await mountPanel(baking(), { path: "/analysis" });

    expect(queryAll(panel, ".by-program tbody tr, .by-program tfoot tr").map(text)).toEqual([
      "Whole wheat 1 €0.15 €0.15",
      "No Program 1 €0.12 €0.12",
    ]);
  });
});
