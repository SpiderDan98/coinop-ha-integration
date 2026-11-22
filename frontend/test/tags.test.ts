import { describe, expect, it } from "vitest";
import type { Message } from "../src/hass";
import { WsError, recorded, recordedBackend } from "./fake-hass";
import { click, fill, iconButton, mountPanel, query, queryAll, settle, text } from "./render";

const chips = (root: Element) => queryAll(root, ".tag-chip .tag-name").map(text);
const button = (root: Element, label: string) => {
  const found = queryAll(root, "ha-button, ha-icon-button, button").find(
    (candidate) => text(candidate) === label || (candidate as { label?: string }).label === label,
  );
  if (!found) throw new Error(`no button "${label}"`);
  return found;
};
const press = async (panel: Element, input: HTMLElement, key: string) => {
  input.dispatchEvent(
    new KeyboardEvent("keydown", { key, bubbles: true, composed: true, cancelable: true }),
  );
  await settle(panel);
};

const editRun = async (panel: Element) => {
  await click(panel, query(panel, ".facts ha-icon-button.edit"));
  return query(panel, ".run-dialog");
};

/** A backend whose `coinop/runs/update` returns the Run with the Tags it was sent. */
function taggingBackend() {
  return recordedBackend().reply("coinop/runs/update", (msg: Message) => ({
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
  const CREATE = "coinop/tags/create";
  const RENAME = "coinop/tags/rename";
  const DELETE = "coinop/tags/delete";
  const tagsBackend = () =>
    recordedBackend()
      .reply(CREATE, (msg) => ({ tag: msg.name }))
      .reply(RENAME, (msg) => ({ tag: msg.name }))
      .reply(DELETE, () => ({}));
  const failingBackend = () => {
    const refuse = () => {
      throw new WsError("invalid_format");
    };
    return recordedBackend().reply(CREATE, refuse).reply(RENAME, refuse).reply(DELETE, refuse);
  };
  const dialogs = (panel: Element) => queryAll(panel, ".tag-dialog");
  const name = (panel: Element) => query(panel, ".tag-dialog [name=name]") as HTMLInputElement;
  const save = (panel: Element) => query(panel, ".tag-dialog ha-button.save");
  const hints = (panel: Element) => queryAll(panel, ".tag-dialog .hint").map(text);
  const openNew = (panel: Element) => click(panel, query(panel, "ha-button.new-tag.fab"));
  const openRename = (panel: Element, tag: string) =>
    click(panel, button(row(panel, tag), "Rename"));
  const escape = async (panel: Element) => {
    query(panel, "coinop-dialog dialog").dispatchEvent(new Event("cancel", { cancelable: true }));
    await settle(panel);
  };

  it("opens from the toolbar between Line Item Templates and Devices", async () => {
    const panel = await mountPanel(recordedBackend());

    await click(panel, query(panel, `a.tab[href$="/tags"]`));

    expect(location.pathname).toBe("/coinop/tags");
    expect(queryAll(panel, "a.tab").map((tab) => tab.title)).toEqual([
      "Overview",
      "Runs",
      "Analysis",
      "Materials",
      "Line Item Templates",
      "Tags",
      "Devices",
    ]);
    expect(query(panel, "a.tab.on").title).toBe("Tags");
    expect(text(query(panel, ".page-title"))).toBe("Tags");
  });

  it("lists each Tag with its Run count and total cost, read-only", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/tags" });

    expect(rows(panel)).toEqual(["Cosplay helmet 1 €0.30", "Gift 2 €1.16", "Spare parts 0 €0.00"]);
    expect(queryAll(panel, ".tags input")).toEqual([]);
  });

  it("renames a Tag in a dialog, saying when the new name merges it into another", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    await openRename(panel, "Gift");
    expect(text(query(panel, ".tag-dialog"))).toContain("Rename “Gift”");
    expect(name(panel).value).toBe("Gift");
    expect(name(panel).getAttribute("maxlength")).toBe("40");
    expect(queryAll(panel, ".tags input")).toEqual([]);

    await fill(panel, name(panel), "cosplay HELMET");
    expect(hints(panel)).toEqual([
      "Merges into “Cosplay helmet”: every Run and Device keeps it once.",
    ]);
    await fill(panel, name(panel), " Present ");
    expect(hints(panel)).toEqual([]);
    expect(backend.sent(RENAME)).toEqual([]);
    await click(panel, save(panel));

    expect(backend.sent(RENAME)).toEqual([{ type: RENAME, tag: "Gift", name: "Present" }]);
    expect(dialogs(panel)).toEqual([]);
  });

  it("merges a Tag into the one whose name it is renamed to", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await openRename(panel, "Gift");

    await fill(panel, name(panel), "Spare parts");
    await click(panel, save(panel));

    expect(backend.sent(RENAME)).toEqual([{ type: RENAME, tag: "Gift", name: "Spare parts" }]);
  });

  it("does not rename a Tag to a blank name", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await openRename(panel, "Gift");

    await fill(panel, name(panel), "  ");
    expect(save(panel).hasAttribute("disabled")).toBe(true);
    await click(panel, save(panel));
    await press(panel, name(panel), "Enter");

    expect(backend.sent(RENAME)).toEqual([]);
    expect(dialogs(panel)).toHaveLength(1);
  });

  it("creates a Tag from the floating button, but not one that already exists", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    await openNew(panel);
    expect(text(query(panel, ".tag-dialog"))).toContain("New Tag");
    expect(name(panel).value).toBe("");
    expect(text(save(panel))).toBe("Create");
    expect(save(panel).hasAttribute("disabled")).toBe(true);

    await fill(panel, name(panel), "gift");
    expect(hints(panel)).toEqual(["“Gift” already exists."]);
    expect(save(panel).hasAttribute("disabled")).toBe(true);
    await press(panel, name(panel), "Enter");
    expect(backend.sent(CREATE)).toEqual([]);

    await fill(panel, name(panel), " Batch 8 ");
    expect(hints(panel)).toEqual([]);
    expect(backend.sent(CREATE)).toEqual([]);
    await click(panel, save(panel));

    expect(backend.sent(CREATE)).toEqual([{ type: CREATE, name: "Batch 8" }]);
    expect(dialogs(panel)).toEqual([]);
    expect(queryAll(panel, "ha-button.new-tag.fab")).toHaveLength(1);
  });

  it("creates a Tag on Enter in the name", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await openNew(panel);

    await fill(panel, name(panel), "Batch 8");
    await press(panel, name(panel), "Enter");

    expect(backend.sent(CREATE)).toEqual([{ type: CREATE, name: "Batch 8" }]);
    expect(dialogs(panel)).toEqual([]);
  });

  it("discards what was typed on Cancel or Escape without sending anything", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    await openNew(panel);
    await fill(panel, name(panel), "Batch 8");
    await escape(panel);
    expect(dialogs(panel)).toEqual([]);

    await openRename(panel, "Gift");
    await fill(panel, name(panel), "Present");
    await click(panel, query(panel, ".tag-dialog ha-button.cancel"));
    expect(dialogs(panel)).toEqual([]);

    expect(backend.calls.filter(({ type }) => type.startsWith("coinop/tags/"))).toEqual([]);
    expect(rows(panel)).toEqual(["Cosplay helmet 1 €0.30", "Gift 2 €1.16", "Spare parts 0 €0.00"]);
    await openRename(panel, "Gift");
    expect(name(panel).value).toBe("Gift");
    await escape(panel);
    await openNew(panel);
    expect(name(panel).value).toBe("");
  });

  it("keeps the dialog open and says so when a Tag could not be created", async () => {
    const backend = failingBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await openNew(panel);
    await fill(panel, name(panel), "Batch 8");

    await click(panel, save(panel));

    expect(backend.sent(CREATE)).toHaveLength(1);
    expect(text(query(panel, ".tag-dialog .error"))).toBe("This change could not be saved.");
    expect(name(panel).value).toBe("Batch 8");
    expect(save(panel).hasAttribute("disabled")).toBe(false);
  });

  it("keeps the dialog open and says so when a Tag could not be renamed", async () => {
    const backend = failingBackend();
    const panel = await mountPanel(backend, { path: "/tags" });
    await openRename(panel, "Gift");
    await fill(panel, name(panel), "Present");

    await click(panel, save(panel));

    expect(backend.sent(RENAME)).toHaveLength(1);
    expect(text(query(panel, ".tag-dialog .error"))).toBe("This change could not be saved.");
    expect(name(panel).value).toBe("Present");

    await escape(panel);
    await openRename(panel, "Gift");
    expect(queryAll(panel, ".error")).toEqual([]);
  });

  it("deletes a Tag only once confirmed in a dialog", async () => {
    const backend = tagsBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    await click(panel, button(row(panel, "Gift"), "Delete"));
    const dialog = query(panel, ".delete-tag-dialog");
    expect(text(dialog)).toContain("Delete “Gift”?");
    expect(text(query(dialog, "p"))).toBe(
      "Removes “Gift” from 2 Runs and from every Device's Tags for new Runs.",
    );
    await click(panel, query(dialog, "ha-button.cancel"));
    expect(queryAll(panel, ".delete-tag-dialog")).toEqual([]);
    expect(backend.sent(DELETE)).toEqual([]);

    await click(panel, button(row(panel, "Gift"), "Delete"));
    expect(text(query(panel, ".delete-tag-dialog ha-button.confirm"))).toBe("Delete for good");
    await click(panel, query(panel, ".delete-tag-dialog ha-button.confirm"));

    expect(backend.sent(DELETE)).toEqual([{ type: DELETE, tag: "Gift" }]);
    expect(queryAll(panel, ".delete-tag-dialog")).toEqual([]);
    expect(queryAll(panel, ".error")).toEqual([]);
  });

  it("says when a Tag could not be deleted", async () => {
    const panel = await mountPanel(failingBackend(), { path: "/tags" });
    await click(panel, button(row(panel, "Gift"), "Delete"));

    await click(panel, query(panel, ".delete-tag-dialog ha-button.confirm"));

    expect(queryAll(panel, ".delete-tag-dialog")).toEqual([]);
    expect(text(query(panel, ".error"))).toBe("This change could not be saved.");
  });

  it("follows the catalogue as it changes", async () => {
    const backend = recordedBackend();
    const panel = await mountPanel(backend, { path: "/tags" });

    backend.push("coinop/catalog/subscribe", { tags: ["Cosplay helmet", "Present"] });
    await settle(panel);

    expect(queryAll(panel, "tr.tag .tag-name").map(text)).toEqual(["Cosplay helmet", "Present"]);
  });

  it("says when there are no Tags yet", async () => {
    const backend = recordedBackend().subscription("coinop/catalog/subscribe", () => [
      recorded.catalog.empty,
    ]);

    const panel = await mountPanel(backend, { path: "/tags" });

    expect(text(panel)).toContain("No Tags yet. Create one here or type a name in a Run's Tags.");
  });

  it("is in German when Home Assistant is", async () => {
    const panel = await mountPanel(recordedBackend({ language: "de" }), { path: "/tags" });

    expect(rows(panel)[1]).toBe("Gift 2 1,16 €");
    await click(panel, button(row(panel, "Gift"), "Umbenennen"));
    expect(text(query(panel, ".tag-dialog"))).toContain("„Gift“ umbenennen");
    expect(text(save(panel))).toBe("Speichern");
  });
});

describe("Tags in the gallery", () => {
  const tagged = (tags: Record<string, string[]>) =>
    recordedBackend().subscription("coinop/runs/subscribe", () => [
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
    const panel = await mountPanel(recordedBackend(), { path: "/runs" });
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
    const panel = await mountPanel(recordedBackend(), { path: "/runs" });
    await tick(panel, "input.no-tag");
    await tick(panel, `input[value="Cosplay helmet"]`);

    await fill(panel, query(panel, "select.device-filter"), "device-kobra");

    expect(shown(panel)).toEqual(["Helmet"]);
    expect(text(query(panel, "coinop-run-list .head .muted"))).toBe("1 Run · €0.30");
  });
});

describe("Tags for new Runs", () => {
  const UPDATE = "coinop/devices/update_settings";

  it("are set per Device in its settings dialog and saved with it", async () => {
    const backend = recordedBackend().reply(UPDATE, (msg) => ({
      settings: { ...recorded.devices[0]?.settings, ...(msg.settings as object) },
    }));
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Kobra"));
    const dialog = query(panel, ".settings-dialog");
    expect(text(query(dialog, ".new-run-tags"))).toBe(
      "Tags for new Runs Batch 7 Copied onto every Run that starts on this Device.",
    );

    await fill(panel, query(dialog, ".tag-input input"), "gif");
    await click(panel, button(dialog, "Gift"));
    expect(backend.sent(UPDATE)).toEqual([]);
    await click(panel, query(panel, ".settings-dialog ha-button.save"));

    expect(backend.sent(UPDATE)).toEqual([
      {
        type: UPDATE,
        device_id: "device-kobra",
        settings: { tags_for_new_runs: ["Batch 7", "Gift"] },
      },
    ]);
    expect(queryAll(panel, ".settings-dialog")).toEqual([]);
    expect(chips(query(panel, ".device .new-run-tags"))).toEqual(["Batch 7", "Gift"]);
  });

  it("say when they could not be saved and keep what was saved", async () => {
    const backend = recordedBackend().reply(UPDATE, () => {
      throw new WsError("invalid_format");
    });
    const panel = await mountPanel(backend, { path: "/devices" });
    await click(panel, iconButton(panel, "Edit settings of Kobra"));

    await click(panel, iconButton(panel, "Remove Batch 7"));
    await click(panel, query(panel, ".settings-dialog ha-button.save"));

    expect(text(query(panel, ".settings-dialog .error"))).toBe("This change could not be saved.");
    expect(chips(query(panel, ".device .new-run-tags"))).toEqual(["Batch 7"]);
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
    const dialog = await editRun(panel);
    const input = query(dialog, ".tag-input input");

    await fill(panel, input, "s");

    expect(queryAll(dialog, ".suggestion").map(text)).toEqual([
      "Cosplay helmet",
      "Spare parts",
      "Create “s”",
    ]);
    await click(panel, button(dialog, "Spare parts"));
    expect(chips(dialog)).toEqual(["Gift", "Spare parts"]);
    expect((input as HTMLInputElement).value).toBe("");
    expect(backend.sent("coinop/runs/update")).toEqual([]);
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent("coinop/runs/update")).toEqual([
      { type: "coinop/runs/update", run_id: "benchy", tags: ["Gift", "Spare parts"] },
    ]);
    expect(chips(query(panel, ".facts"))).toEqual(["Gift", "Spare parts"]);
  });

  it("creates a Tag by typing its name, reusing an existing one that differs in case", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await editRun(panel);
    const input = query(dialog, ".tag-input input");

    await fill(panel, input, "  Batch 7 ");
    await press(panel, input, "Enter");
    await fill(panel, input, "spare PARTS");
    await press(panel, input, "Enter");
    await fill(panel, input, "gift");
    await press(panel, input, "Enter");
    expect(backend.sent("coinop/runs/update")).toEqual([]);
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent("coinop/runs/update").map((call) => call.tags)).toEqual([
      ["Batch 7", "Gift", "Spare parts"],
    ]);
    expect(input.getAttribute("maxlength")).toBe("40");
  });

  it("removes a Tag from the Run", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/helmet" });
    const dialog = await editRun(panel);

    await click(panel, iconButton(dialog, "Remove Gift"));
    await click(panel, query(dialog, "ha-button.save"));

    expect(backend.sent("coinop/runs/update").at(-1)?.tags).toEqual(["Cosplay helmet"]);
    expect(chips(panel)).toEqual(["Cosplay helmet"]);
  });
});

describe("The Tag field", () => {
  it("picks a suggestion with the arrow keys and Enter, which doesn't save the dialog", async () => {
    const backend = taggingBackend();
    const panel = await mountPanel(backend, { path: "/run/benchy" });
    const dialog = await editRun(panel);
    const input = query(dialog, ".tag-input input");

    await fill(panel, input, "s");
    await press(panel, input, "ArrowDown");
    await press(panel, input, "ArrowDown");
    expect(text(query(dialog, ".suggestion.active"))).toBe("Spare parts");
    await press(panel, input, "Enter");

    expect(chips(dialog)).toEqual(["Gift", "Spare parts"]);
    expect(backend.sent("coinop/runs/update")).toEqual([]);
  });

  it("closes its suggestions when focus leaves it", async () => {
    const panel = await mountPanel(taggingBackend(), { path: "/run/benchy" });
    const dialog = await editRun(panel);
    const input = query(dialog, ".tag-input input");
    await fill(panel, input, "s");

    input.dispatchEvent(new FocusEvent("focusout", { bubbles: true, composed: true }));
    await settle(panel);

    expect(queryAll(dialog, ".suggestion")).toEqual([]);
  });
});

describe("The Tag filter", () => {
  it("closes on a click outside it", async () => {
    const panel = await mountPanel(recordedBackend(), { path: "/runs" });
    const details = query(panel, "details.tag-filter") as HTMLDetailsElement;
    details.open = true;

    await click(panel, query(panel, ".name-filter"));

    expect(details.open).toBe(false);
  });
});
