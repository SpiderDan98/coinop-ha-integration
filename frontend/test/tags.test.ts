import { describe, expect, it } from "vitest";
import type { Message } from "../src/hass";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, mountPanel, query, queryAll, settle, text } from "./render";

const sent = (backend: ReturnType<typeof recordedBackend>, type: string) =>
  backend.calls.filter((call) => call.type === type);
const chips = (root: Element) => queryAll(root, ".tag-chip .tag-name").map(text);
const button = (root: Element, label: string) => {
  const found = queryAll(root, "button").find((candidate) => text(candidate) === label);
  if (!found) throw new Error(`no button "${label}"`);
  return found;
};
const press = async (panel: Element, input: HTMLElement, key: string) => {
  input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, composed: true }));
  await settle(panel);
};

/** A backend whose `wattbill/runs/update` returns the Run with the Tags it was sent. */
function taggingBackend() {
  return recordedBackend().reply("wattbill/runs/update", (msg: Message) => ({
    run: { ...recorded.run(msg.run_id as string), tags: msg.tags },
  }));
}

describe("Tags tab", () => {
  const rows = (panel: Element) => queryAll(panel, "tr.tag").map(text);
  const row = (panel: Element, tag: string) => {
    const found = queryAll(panel, "tr.tag").find((candidate) =>
      text(query(candidate, ".tag-name")).startsWith(tag),
    );
    if (!found) throw new Error(`no row "${tag}"`);
    return found;
  };
  const tagsBackend = () =>
    recordedBackend()
      .reply("wattbill/tags/rename", (msg) => ({ tag: msg.name }))
      .reply("wattbill/tags/delete", () => ({}));

  it("opens from the toolbar between Materials and Devices", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/tags"]`));

    expect(location.pathname).toBe("/wattbill/tags");
    expect(queryAll(panel, "a.tab").map(text)).toEqual(["Materials", "Tags", "Devices"]);
    expect(text(query(panel, "h2"))).toBe("Tags");
  });

  it("lists each Tag with its Run count and total cost", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/tags" });

    expect(rows(panel)).toEqual([
      "Cosplay helmet 1 €0.30 Rename Delete",
      "Gift 2 €1.16 Rename Delete",
      "Spare parts 0 €0.00 Rename Delete",
    ]);
  });

  it("renames a Tag, saying when the new name merges it into another", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await click(panel, button(row(panel, "Gift"), "Rename"));
    const input = query(panel, "tr.tag input");

    await fill(panel, input, "cosplay HELMET");
    expect(text(query(panel, ".merge-hint"))).toBe(
      "Merges into “Cosplay helmet”: every Run and Device keeps it once.",
    );
    await fill(panel, input, " Present ");
    expect(queryAll(panel, ".merge-hint")).toHaveLength(0);
    await click(panel, button(panel, "Save"));

    expect(sent(backend, "wattbill/tags/rename")).toEqual([
      { type: "wattbill/tags/rename", tag: "Gift", name: "Present" },
    ]);
    expect(queryAll(panel, "tr.tag input")).toHaveLength(0);
  });

  it("deletes a Tag only once confirmed", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    await click(panel, button(row(panel, "Gift"), "Delete"));
    expect(text(query(panel, ".delete-hint"))).toBe(
      "Removes “Gift” from 2 Runs and from every Device's Tags for new Runs.",
    );
    await click(panel, button(panel, "Cancel"));
    expect(sent(backend, "wattbill/tags/delete")).toEqual([]);

    await click(panel, button(row(panel, "Gift"), "Delete"));
    await click(panel, button(panel, "Delete for good"));
    expect(sent(backend, "wattbill/tags/delete")).toEqual([
      { type: "wattbill/tags/delete", tag: "Gift" },
    ]);
  });

  it("follows the catalogue as it changes", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    backend.push("wattbill/catalog/subscribe", { tags: ["Cosplay helmet", "Present"] });
    await settle(panel);

    expect(queryAll(panel, "tr.tag .tag-name").map(text)).toEqual(["Cosplay helmet", "Present"]);
  });

  it("says when there are no Tags yet", async () => {
    const backend = recordedBackend().subscription("wattbill/catalog/subscribe", () => [
      recorded.catalog.empty,
    ]);

    const panel = await mountPanel(backend, { path: "/tags" });

    expect(text(panel)).toContain("No Tags yet. Type a name in a Run's Tags to create one.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/tags" });

    expect(rows(panel)[1]).toBe("Gift 2 1,16 € Umbenennen Löschen");
  });
});

describe("Tags in the gallery", () => {
  const tagged = (tags: Record<string, string[]>) =>
    recordedBackend().subscription("wattbill/runs/subscribe", () => [
      { runs: recorded.snapshot.runs.map((run) => ({ ...run, tags: tags[run.id] ?? run.tags })) },
    ]);
  const shown = (panel: Element) => queryAll(panel, ".tile .strong").map((name) => text(name));
  const tick = (panel: Element, selector: string, on = true) =>
    fill(panel, query(panel, `.tag-filter ${selector}`), on ? "on" : "off");

  it("shows up to two Tag chips per tile plus how many more", async () => {
    const backend = tagged({ benchy: ["Batch 7", "Cosplay helmet", "Gift", "Spare parts"] });
    const panel = await mountPanel(backend);

    expect(queryAll(panel, ".tile").map((tile) => chips(tile).join(", "))).toEqual([
      "",
      "Cosplay helmet, Gift",
      "Batch 7, Cosplay helmet",
    ]);
    expect(queryAll(panel, ".tile .more-tags").map(text)).toEqual(["+2"]);
  });

  it("filters by any of the chosen Tags, or Runs without one", async () => {
    const panel = await mountPanel(recordedBackend());
    expect(queryAll(panel, ".tag-filter label").map(text)).toEqual([
      "No tag",
      "Cosplay helmet",
      "Gift",
      "Spare parts",
    ]);

    await tick(panel, `input[value="Gift"]`);
    expect(shown(panel)).toEqual(["Helmet", "Benchy"]);
    expect(text(query(panel, ".tag-filter summary"))).toBe("Gift");

    await tick(panel, "input.no-tag");
    expect(shown(panel)).toEqual(["Untitled Run", "Helmet", "Benchy"]);

    await tick(panel, `input[value="Gift"]`, false);
    await tick(panel, `input[value="Cosplay helmet"]`);
    expect(shown(panel)).toEqual(["Untitled Run", "Helmet"]);
    expect(text(query(panel, ".tag-filter summary"))).toBe("No tag, Cosplay helmet");
  });

  it("combines the Tag filter with the Device filter", async () => {
    const panel = await mountPanel(recordedBackend());
    await tick(panel, "input.no-tag");
    await tick(panel, `input[value="Cosplay helmet"]`);

    await fill(panel, query(panel, "select.device-filter"), "device-kobra");

    expect(shown(panel)).toEqual(["Helmet"]);
    expect(text(query(panel, ".head"))).toBe("Runs 1 · €0.30");
  });
});

describe("Tags for new Runs", () => {
  const UPDATE = "wattbill/devices/update_settings";

  it("are set per Device and saved at once", async () => {
    const backend = recordedBackend().reply(UPDATE, (msg) => ({ settings: msg.settings }));
    const panel = await mountPanel(backend, { path: "/devices" });
    const card = query(panel, ".device");
    expect(text(query(card, ".new-run-tags"))).toBe(
      "Tags for new Runs Batch 7 × Copied onto every Run that starts on this Device.",
    );

    await fill(panel, query(card, ".tag-input input"), "gif");
    await click(panel, button(card, "Gift"));

    expect(sent(backend, UPDATE)).toEqual([
      {
        type: UPDATE,
        device_id: "device-kobra",
        settings: { tags_for_new_runs: ["Batch 7", "Gift"] },
      },
    ]);
    expect(chips(card)).toEqual(["Batch 7", "Gift"]);
  });

  it("say when they could not be saved and keep what was saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/devices" });

    await click(panel, query(panel, `.tag-chip button[aria-label="Remove Batch 7"]`));

    expect(chips(panel)).toEqual(["Batch 7"]);
    expect(text(query(panel, ".device .error"))).toBe("This change could not be saved.");
  });
});

describe("Tags on a Run", () => {
  it("shows the Run's Tags alphabetically", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/run/helmet" });

    expect(chips(panel)).toEqual(["Cosplay helmet", "Gift"]);
  });

  it("suggests existing Tags while typing and adds the one picked", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const input = query(panel, ".tag-input input");

    await fill(panel, input, "s");

    expect(queryAll(panel, ".suggestion").map(text)).toEqual([
      "Cosplay helmet",
      "Spare parts",
      "Create “s”",
    ]);
    await click(panel, button(panel, "Spare parts"));
    expect(sent(backend, "wattbill/runs/update").at(-1)).toEqual({
      type: "wattbill/runs/update",
      run_id: "benchy",
      tags: ["Gift", "Spare parts"],
    });
    expect(chips(panel)).toEqual(["Gift", "Spare parts"]);
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("creates a Tag by typing its name, reusing an existing one that differs in case", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const input = query(panel, ".tag-input input");

    await fill(panel, input, "  Batch 7 ");
    await press(panel, input, "Enter");
    await fill(panel, input, "spare PARTS");
    await press(panel, input, "Enter");
    await fill(panel, input, "gift");
    await press(panel, input, "Enter");

    expect(sent(backend, "wattbill/runs/update").map((call) => call.tags)).toEqual([
      ["Batch 7", "Gift"],
      ["Batch 7", "Gift", "Spare parts"],
    ]);
    expect(input.getAttribute("maxlength")).toBe("40");
  });

  it("removes a Tag from the Run", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/helmet" });

    await click(panel, query(panel, `.tag-chip button[aria-label="Remove Gift"]`));

    expect(sent(backend, "wattbill/runs/update").at(-1)?.tags).toEqual(["Cosplay helmet"]);
    expect(chips(panel)).toEqual(["Cosplay helmet"]);
  });
});
