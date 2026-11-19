import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const CREATE = "wattbill/cost_statement/create";

const pick = (panel: Element, name: string) =>
  query(
    queryAll(panel, ".pick-tile").find((tile) => text(query(tile, ".strong")) === name) ?? panel,
    "input.pick",
  );
const field = (panel: Element, name: string) =>
  query(panel, `.statement-dialog [name=${name}]`) as HTMLInputElement;

/** The links the panel clicked to download, kept from navigating away. */
let downloads: { href: string; download: string; target: string }[] = [];
const keepDownload = (event: MouseEvent) => {
  const link = event.composedPath()[0];
  if (link instanceof HTMLAnchorElement) {
    event.preventDefault();
    downloads.push({
      href: link.getAttribute("href") ?? "",
      download: link.download,
      target: link.target,
    });
  }
};
beforeEach(() => {
  downloads = [];
  localStorage.clear();
  document.addEventListener("click", keepDownload);
});
afterEach(() => {
  document.removeEventListener("click", keepDownload);
  vi.restoreAllMocks();
});

async function openDialog(backend = recordedBackend(), { tags = [] as string[] } = {}) {
  const panel = await mountPanel(backend.reply(CREATE, () => recorded.statementCreate));
  for (const tag of tags)
    await fill(panel, query(panel, `.tag-filter input[value="${tag}"]`), "on");
  await fill(panel, pick(panel, "Helmet"), "on");
  await fill(panel, pick(panel, "Benchy"), "on");
  await click(panel, query(panel, ".basket .statement"));
  return panel;
}

describe("Cost Statement export", () => {
  it("is the basket's first action", async () => {
    const panel = await openDialog();

    expect(text(query(panel, ".basket .actions"))).toBe("Cost Statement… Clear Delete");
  });

  it("downloads the selected Runs, by start, with the hub's default Markup", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend);

    expect(text(query(panel, ".statement-dialog h2"))).toBe("Cost Statement for 2 Runs");
    expect(field(panel, "title").placeholder).toBe("Cost Statement");
    expect(field(panel, "detail").value).toBe("detailed");
    expect(field(panel, "language").value).toBe("en");
    expect(field(panel, "markup").value).toBe(String(recorded.statementDefaults.markup));

    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        run_ids: ["benchy", "helmet"],
        title: null,
        note: null,
        detail: "detailed",
        images: true,
        language: "en",
        markup: 10,
      },
    ]);
    // HA's own file download: an absolute link opening in a new tab, which the
    // Companion apps hand to their download manager or the system browser.
    expect(downloads).toEqual([
      { href: location.origin + recorded.statementCreate.path, download: "", target: "_blank" },
    ]);
    expect(queryAll(panel, ".statement-dialog")).toHaveLength(0);
    expect(queryAll(panel, ".basket")).toHaveLength(1);
  });

  it("takes a title, a note, Compact, German and another Markup", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend);

    await fill(panel, field(panel, "title"), " Gifts 2026 ");
    await fill(panel, field(panel, "note"), "For the school fair.");
    await fill(panel, field(panel, "detail"), "compact");
    await fill(panel, field(panel, "language"), "de");
    await fill(panel, field(panel, "markup"), "7.5");
    expect(field(panel, "title").placeholder).toBe("Kostenaufstellung");
    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)).toEqual([
      {
        type: CREATE,
        run_ids: ["benchy", "helmet"],
        title: "Gifts 2026",
        note: "For the school fair.",
        detail: "compact",
        images: true,
        language: "de",
        markup: 7.5,
      },
    ]);
  });

  it("leaves Cover Images off when asked, which only a Detailed statement has", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend);
    expect(field(panel, "images").checked).toBe(true);

    await fill(panel, field(panel, "detail"), "compact");
    expect(field(panel, "images").disabled).toBe(true);
    await fill(panel, field(panel, "detail"), "detailed");
    await fill(panel, field(panel, "images"), "off");
    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)[0]).toMatchObject({ detail: "detailed", images: false });
  });

  it("refuses a negative or missing Markup", async () => {
    const panel = await openDialog();

    await fill(panel, field(panel, "markup"), "-1");
    expect((query(panel, ".statement-dialog .download") as HTMLButtonElement).disabled).toBe(true);
    await fill(panel, field(panel, "markup"), "");
    expect((query(panel, ".statement-dialog .download") as HTMLButtonElement).disabled).toBe(true);
    await fill(panel, field(panel, "markup"), "0");
    expect((query(panel, ".statement-dialog .download") as HTMLButtonElement).disabled).toBe(false);
  });

  it("says when the statement can't be made and stays open", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend);
    backend.reply(CREATE, () => {
      throw new WsError("not_allowed");
    });

    await click(panel, query(panel, ".statement-dialog .download"));

    expect(text(query(panel, ".statement-dialog"))).toContain(
      "The Cost Statement could not be made.",
    );
    expect(downloads).toEqual([]);
  });

  it("can be cancelled", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend);

    await click(panel, query(panel, ".statement-dialog .cancel"));

    expect(queryAll(panel, ".statement-dialog")).toHaveLength(0);
    expect(backend.sent(CREATE)).toEqual([]);
  });

  it("is in German and German by default when Home Assistant is", async () => {
    const panel = await openDialog(recordedBackend({ language: "de" }));
    await settle(panel);

    expect(text(query(panel, ".basket .statement"))).toBe("Kostenaufstellung…");
    expect(field(panel, "language").value).toBe("de");
    expect(field(panel, "title").placeholder).toBe("Kostenaufstellung");
  });
});

describe("Cost Statement title for one Tag", () => {
  it("defaults to the Tag when exactly one is filtered", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend, { tags: ["Gift"] });

    expect(field(panel, "title").placeholder).toBe("Cost Statement – Gift");
    await fill(panel, field(panel, "language"), "de");
    expect(field(panel, "title").placeholder).toBe("Kostenaufstellung – Gift");
    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)[0]).toMatchObject({ title: "Kostenaufstellung – Gift" });
  });

  it("gives way to a typed title", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend, { tags: ["Gift"] });

    await fill(panel, field(panel, "title"), "Fair 2026");
    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)[0]).toMatchObject({ title: "Fair 2026" });
  });

  it("stays the plain default with two Tags, or a Tag and No tag", async () => {
    const backend = recordedBackend();
    const panel = await openDialog(backend, { tags: ["Gift", "Cosplay helmet"] });
    expect(field(panel, "title").placeholder).toBe("Cost Statement");
    await click(panel, query(panel, ".statement-dialog .download"));

    const untagged = await openDialog(recordedBackend(), { tags: ["Gift"] });
    await click(untagged, query(untagged, ".statement-dialog .cancel"));
    await fill(untagged, query(untagged, ".tag-filter input.no-tag"), "on");
    await click(untagged, query(untagged, ".basket .statement"));

    expect(backend.sent(CREATE)[0]).toMatchObject({ title: null });
    expect(field(untagged, "title").placeholder).toBe("Cost Statement");
  });
});

describe("Remembered export options", () => {
  async function exportWith(changes: Record<string, string>) {
    const panel = await openDialog();
    for (const [name, value] of Object.entries(changes))
      await fill(panel, field(panel, name), value);
    await click(panel, query(panel, ".statement-dialog .download"));
  }

  it("come back the next time, but title and note don't", async () => {
    await exportWith({
      title: "Gifts",
      note: "For the fair.",
      images: "off",
      detail: "compact",
      language: "de",
      markup: "7.5",
    });

    const backend = recordedBackend();
    const panel = await openDialog(backend);

    expect(
      ["title", "note", "detail", "language", "markup"].map((name) => field(panel, name).value),
    ).toEqual(["", "", "compact", "de", "7.5"]);
    expect(field(panel, "images").checked).toBe(false);
    await click(panel, query(panel, ".statement-dialog .download"));
    expect(backend.sent(CREATE)[0]).toMatchObject({
      title: null,
      note: null,
      detail: "compact",
      images: false,
      language: "de",
      markup: 7.5,
    });
  });

  it("are only remembered once a statement was made", async () => {
    const panel = await openDialog();
    await fill(panel, field(panel, "markup"), "50");
    await click(panel, query(panel, ".statement-dialog .cancel"));

    const again = await openDialog();

    expect(field(again, "markup").value).toBe(String(recorded.statementDefaults.markup));
  });

  it("are left out where they no longer fit", async () => {
    localStorage.setItem(
      "wattbill-statement-options",
      JSON.stringify({ detail: "poster", language: "fr", markup: -3, images: "yes" }),
    );

    const panel = await openDialog();

    expect(["detail", "language", "markup"].map((name) => field(panel, name).value)).toEqual([
      "detailed",
      "en",
      String(recorded.statementDefaults.markup),
    ]);
    expect(field(panel, "images").checked).toBe(true);
  });

  it("are not needed when the browser keeps no storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const backend = recordedBackend();
    const panel = await openDialog(backend);

    expect(field(panel, "markup").value).toBe(String(recorded.statementDefaults.markup));
    await click(panel, query(panel, ".statement-dialog .download"));

    expect(backend.sent(CREATE)).toHaveLength(1);
    expect(downloads).toHaveLength(1);
  });
});
