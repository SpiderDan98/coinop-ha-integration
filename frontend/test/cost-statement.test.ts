import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Message } from "../src/hass";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const CREATE = "wattbill/cost_statement/create";

const sent = (backend: { calls: Message[] }, type: string) =>
  backend.calls.filter((call) => call.type === type);
const pick = (panel: Element, name: string) =>
  query(
    queryAll(panel, ".pick-tile").find((tile) => text(query(tile, ".strong")) === name) ?? panel,
    "input.pick",
  );
const field = (panel: Element, name: string) =>
  query(panel, `.statement-dialog [name=${name}]`) as HTMLInputElement;

/** The links the panel clicked to download, kept from navigating away. */
let downloads: { href: string; download: string }[] = [];
const keepDownload = (event: MouseEvent) => {
  const link = event.composedPath()[0];
  if (link instanceof HTMLAnchorElement) {
    event.preventDefault();
    downloads.push({ href: link.getAttribute("href") ?? "", download: link.download });
  }
};
beforeEach(() => {
  downloads = [];
  document.addEventListener("click", keepDownload);
});
afterEach(() => document.removeEventListener("click", keepDownload));

async function openDialog(backend = recordedBackend()) {
  const panel = await mountPanel(backend.reply(CREATE, () => recorded.statementCreate));
  await fill(panel, pick(panel, "Helmet"), "on");
  await fill(panel, pick(panel, "Benchy"), "on");
  await click(panel, query(panel, ".basket .statement"));
  return panel;
}

describe("Cost Statement export", () => {
  it("is the basket's first action", async () => {
    const panel = await openDialog();

    expect(text(query(panel, ".basket .actions"))).toBe("Cost Statement… Delete Clear");
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

    expect(sent(backend, CREATE)).toEqual([
      {
        type: CREATE,
        run_ids: ["benchy", "helmet"],
        title: null,
        note: null,
        detail: "detailed",
        language: "en",
        markup: 10,
      },
    ]);
    expect(downloads).toEqual([{ href: recorded.statementCreate.path, download: "" }]);
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

    expect(sent(backend, CREATE)).toEqual([
      {
        type: CREATE,
        run_ids: ["benchy", "helmet"],
        title: "Gifts 2026",
        note: "For the school fair.",
        detail: "compact",
        language: "de",
        markup: 7.5,
      },
    ]);
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
    expect(sent(backend, CREATE)).toEqual([]);
  });

  it("is in German and German by default when Home Assistant is", async () => {
    const panel = await openDialog(recordedBackend({ language: "de" }));
    await settle(panel);

    expect(text(query(panel, ".basket .statement"))).toBe("Kostenaufstellung…");
    expect(field(panel, "language").value).toBe("de");
    expect(field(panel, "title").placeholder).toBe("Kostenaufstellung");
  });
});
