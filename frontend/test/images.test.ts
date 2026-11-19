import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeBackend, recorded, recordedBackend } from "./fake-hass";
import { mountPanel, query, queryAll, settle, text } from "./render";

const SUBSCRIBE = "wattbill/runs/subscribe";
const tiles = (panel: Element) => queryAll(panel, ".tile");
const shown = (root: Element) => queryAll(root, "img").map((img) => img.getAttribute("src"));
const cover = (id: string) => {
  const image = recorded.summary(id).cover;
  if (!image) throw new Error(`${id} has no Cover Image`);
  return image;
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Run images", () => {
  it("show each tile's Cover Image, fetched with authentication", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend);

    const [cancelled, helmet, benchy] = tiles(panel);
    expect(shown(benchy)).toEqual([expect.stringMatching(/^blob:/)]);
    expect(shown(helmet)).toEqual([expect.stringMatching(/^blob:/)]);
    expect(backend.fetches.toSorted()).toEqual(
      [cover("benchy").tile_url, cover("helmet").tile_url].toSorted(),
    );
    expect(cover("benchy").kind).toBe("thumbnail");
    expect(cover("helmet").kind).toBe("snapshot");
    expect(shown(cancelled)).toEqual([]);
    expect(text(cancelled)).toMatch(/^No image /);
  });

  it("show a neutral placeholder for an image that can't be loaded", async () => {
    const backend = new FakeBackend().subscription(SUBSCRIBE, () => [recorded.snapshot]);

    const panel = await mountPanel(backend);

    expect(tiles(panel).map(shown)).toEqual([[], [], []]);
    expect(tiles(panel).map((tile) => text(tile).slice(0, 8))).toEqual([
      "No image",
      "No image",
      "No image",
    ]);
  });

  it("follow a tile's new Cover Image", async () => {
    const backend = recordedBackend().file("/api/wattbill/runs/cancelled/images/new/tile");
    const panel = await mountPanel(backend);

    backend.push(SUBSCRIBE, {
      change: "updated",
      run: {
        ...recorded.summary("cancelled"),
        cover: { ...cover("helmet"), tile_url: "/api/wattbill/runs/cancelled/images/new/tile" },
      },
    });
    await settle(panel);

    expect(backend.fetches.at(-1)).toBe("/api/wattbill/runs/cancelled/images/new/tile");
    expect(shown(tiles(panel)[0])).toEqual([expect.stringMatching(/^blob:/)]);
  });

  it("show the Cover Image large on the Run page, and every image below it", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const benchy = recorded.run("benchy");

    expect(shown(query(panel, ".cover"))).toEqual([expect.stringMatching(/^blob:/)]);
    expect(backend.fetches).toContain(cover("benchy").url);
    expect(queryAll(panel, ".strip figcaption").map(text)).toEqual(["Thumbnail", "Snapshot"]);
    expect(backend.fetches).toEqual(
      expect.arrayContaining(benchy.images.map((image) => image.tile_url)),
    );
  });

  it("show only the placeholder for a Run without images", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/cancelled" });

    expect(shown(query(panel, ".facts"))).toEqual([]);
    expect(text(query(panel, ".facts"))).toMatch(/^No image \+ Upload photos /);
    expect(queryAll(panel, ".strip")).toEqual([]);
  });

  it("are let go when the panel goes away", async () => {
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    const panel = await mountPanel(recordedBackend());
    const urls = tiles(panel).flatMap(shown);

    panel.remove();
    await settle(panel);

    expect(urls).toHaveLength(2);
    expect(revoke.mock.calls.map(([url]) => url).toSorted()).toEqual(urls.toSorted());
  });

  it("are captioned in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), {
      path: "/run/benchy",
    });

    expect(queryAll(panel, ".strip figcaption").map(text)).toEqual(["Vorschaubild", "Kamerabild"]);
  });
});
