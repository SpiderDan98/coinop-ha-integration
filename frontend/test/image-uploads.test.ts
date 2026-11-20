import { describe, expect, it } from "vitest";
import type { RunDetail } from "../src/api";
import { recorded, recordedBackend } from "./fake-hass";
import { click, mountPanel, query, queryAll, settle, text } from "./render";

const UPLOADS = "/api/coinop/runs/benchy/images";
const SET_COVER = "coinop/images/set_cover";
const DELETE = "coinop/images/delete";
const benchy = () => recorded.run("benchy");
const [upload] = recorded.upload.images;
const withUpload: RunDetail = { ...benchy(), images: [...benchy().images, upload] };

const photo = (name: string) => new File([name], name, { type: "image/jpeg" });
const captions = (panel: Element) => queryAll(panel, ".strip figcaption").map(text);
const figure = (panel: Element, kind: string) => {
  const found = queryAll(panel, ".strip figure").find((f) => text(f).startsWith(kind));
  if (!found) throw new Error(`no ${kind} figure`);
  return found;
};

/** What the user does in the file picker: choose these files. */
async function choose(panel: Element, files: File[]) {
  const input = query(panel, "input[type=file]") as HTMLInputElement;
  Object.defineProperty(input, "files", { value: files, configurable: true });
  input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  await settle(panel);
}

describe("Run images on the Run page", () => {
  it("upload the chosen photos at once and show them", async () => {
    let stored = benchy();
    const backend = recordedBackend()
      .post(UPLOADS, () => {
        stored = withUpload;
        return [200, recorded.upload];
      })
      .reply("coinop/runs/get", () => ({ run: stored }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const files = [photo("front.jpg"), photo("back.jpg")];

    await choose(panel, files);

    expect(backend.uploads).toEqual([{ path: UPLOADS, files }]);
    expect(captions(panel)).toEqual(["Thumbnail", "Snapshot", "Upload"]);
    expect(backend.fetches).toContain(upload.tile_url);
  });

  it("accept JPEG, PNG and WebP without a permanent line of limits", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/benchy" });

    const input = query(panel, "input[type=file]") as HTMLInputElement;
    expect(input.multiple).toBe(true);
    expect(input.accept).toBe("image/jpeg,image/png,image/webp");
    expect(text(query(panel, ".facts"))).not.toContain("Up to 10 photos");
  });

  it("say why an upload was refused", async () => {
    const answers: [number, unknown][] = [
      [409, recorded.uploadTooMany],
      [413, { code: "too_large" }],
      [415, { code: "invalid_format" }],
      [500, {}],
    ];
    const backend = recordedBackend().post(UPLOADS, () => answers.shift() ?? [500, {}]);
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const errors = [];

    for (let n = 0; n < 4; n++) {
      await choose(panel, [photo("plate.jpg")]);
      errors.push(text(query(panel, ".images-error")));
    }

    const limits = "Up to 10 photos per Run: JPEG, PNG or WebP, up to 20 MB each.";
    expect(errors).toEqual([
      `A Run keeps up to 10 uploaded photos. ${limits}`,
      `A photo may have up to 20 MB. ${limits}`,
      `Only JPEG, PNG and WebP photos can be uploaded. ${limits}`,
      `The images could not be changed. ${limits}`,
    ]);
    expect(captions(panel)).toEqual(["Thumbnail", "Snapshot"]);
  });

  it("take no more photos once the Run has 10 uploads, and say so", async () => {
    const full = {
      ...benchy(),
      images: Array.from({ length: 10 }, (_, n) => ({ ...upload, id: `upload-${n}` })),
    };
    const panel = await mountPanel(
      recordedBackend().reply("coinop/runs/get", () => ({ run: full })),
      { path: "/run/benchy" },
    );

    expect((query(panel, "input[type=file]") as HTMLInputElement).disabled).toBe(true);
    expect(text(query(panel, ".images-full"))).toBe("A Run keeps up to 10 uploaded photos.");
  });

  it("mark the Cover Image and pick another with “Set as cover”", async () => {
    const backend = recordedBackend()
      .reply("coinop/runs/get", () => ({ run: withUpload }))
      .reply(SET_COVER, () => ({ run: recorded.setCover }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    expect(text(figure(panel, "Thumbnail"))).toContain("Cover Image");
    expect(text(figure(panel, "Upload"))).not.toContain("Cover Image");

    await click(panel, query(figure(panel, "Upload"), ".set-cover"));

    expect(backend.calls.filter((call) => call.type === SET_COVER)).toEqual([
      { type: SET_COVER, run_id: "benchy", image_id: upload.id },
    ]);
    expect(recorded.setCover.cover?.id).toBe(upload.id);
    expect(text(figure(panel, "Upload"))).toContain("Cover Image");
    expect(queryAll(figure(panel, "Thumbnail"), ".set-cover")).toHaveLength(1);
    expect(backend.fetches.at(-1)).toBe(upload.url);
  });

  it("delete an image only after confirmation", async () => {
    const backend = recordedBackend()
      .reply("coinop/runs/get", () => ({ run: withUpload }))
      .reply(DELETE, () => ({ run: recorded.deleteImage }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    await click(panel, query(figure(panel, "Upload"), ".delete-image"));
    expect(text(query(panel, ".image-dialog"))).toMatch(/^Delete this image\?/);
    await click(panel, query(panel, ".image-dialog .cancel"));
    expect(queryAll(panel, ".image-dialog")).toEqual([]);
    expect(backend.calls.filter((call) => call.type === DELETE)).toEqual([]);

    await click(panel, query(figure(panel, "Upload"), ".delete-image"));
    await click(panel, query(panel, ".image-dialog .confirm"));

    expect(backend.calls.filter((call) => call.type === DELETE)).toEqual([
      { type: DELETE, run_id: "benchy", image_id: upload.id },
    ]);
    expect(queryAll(panel, ".image-dialog")).toEqual([]);
    expect(captions(panel)).toEqual(["Thumbnail", "Snapshot"]);
  });

  it("are offered in German when Home Assistant is", async () => {
    const backend = recordedBackend({ language: "de" }).reply("coinop/runs/get", () => ({
      run: withUpload,
    }));
    const panel = await mountPanel(backend, { path: "/run/benchy" });

    expect(text(figure(panel, "Vorschaubild"))).toContain("Titelbild");
    expect(text(query(figure(panel, "Hochgeladen"), ".set-cover"))).toBe("Als Titelbild");
    expect(text(query(panel, ".upload"))).toContain("Fotos hochladen");
  });
});
