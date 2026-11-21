import { describe, expect, it } from "vitest";
import { recorded, recordedBackend } from "./fake-hass";
import { click, iconButton, mountPanel, query, queryAll, text } from "./render";

const LIST = "coinop/devices/list";
const GET = "coinop/runs/get";
const cards = (panel: Element) => queryAll(panel, ".device").map(text);
const facts = (panel: Element) => text(query(panel, ".facts dl"));
const kiln = recorded.studioKiln;
const mugs = recorded.mugs;

describe("An Other Device with images and a Part Count and no job", () => {
  it("shows its image inputs and none of a job", async () => {
    const backend = recordedBackend().reply(LIST, () => ({ devices: [kiln] }));

    const panel = await mountPanel(backend, { path: "/devices" });

    expect(queryAll(panel, ".device-type h2").map(text)).toEqual(["Kiln"]);
    expect(cards(panel)).toEqual([
      "Studio kiln " +
        "Status sensor.kiln_status " +
        "Thumbnail image.kiln_preview " +
        "Camera camera.kiln · Snapshot when a Run ends " +
        "Consumption source Estimate from average power 2,000 W running " +
        "Electricity price €0.30 per kWh " +
        "Reconfigure in Home Assistant " +
        "Tags for new Runs None " +
        "Automatic templates None",
    ]);
    await click(panel, iconButton(panel, "Edit settings of Studio kiln"));
    expect(queryAll(panel, ".settings-dialog .field .label").map(text)).toEqual([
      "Tags for new Runs",
      "Automatic templates",
    ]);
  });

  it("names only the image inputs as not used when it uses neither", async () => {
    const images = { thumbnail: null, camera: null, snapshot: false };
    const backend = recordedBackend().reply(LIST, () => ({
      devices: [{ ...kiln, ha_settings: { ...kiln.ha_settings, images } }],
    }));

    const panel = await mountPanel(backend, { path: "/devices" });

    const [card] = cards(panel);
    expect(card).toContain("Status sensor.kiln_status Not used Thumbnail, Camera Consumption");
    expect(card).not.toMatch(/Job name|Material used|Slots/);
  });

  it("shows its Run's Part Count, cost per part and images", async () => {
    const backend = recordedBackend()
      .reply(LIST, () => ({ devices: [kiln] }))
      .reply(GET, () => ({ run: mugs }));
    for (const image of mugs.images) backend.file(image.url).file(image.tile_url);

    const panel = await mountPanel(backend, { path: "/run/mugs" });

    expect(facts(panel)).toBe(
      "Device Studio kiln Started Jan 15, 2026, 10:00 AM Ended Jan 15, 2026, 11:30 AM " +
        "Running time 1 h 30 min Part Count 9 Tags None",
    );
    expect(text(query(panel, ".totals"))).toBe("Total €0.90 Cost per part (9) €0.10");
    expect(queryAll(panel, ".strip figcaption").map(text)).toEqual(["Thumbnail", "Snapshot"]);
    expect(backend.fetches).toContain(mugs.cover?.url);
    await click(panel, query(panel, ".facts ha-icon-button.edit"));
    expect(queryAll(panel, ".run-dialog [name=part_count]")).toHaveLength(1);
    expect(queryAll(panel, ".run-dialog [name=program]")).toEqual([]);
  });
});
