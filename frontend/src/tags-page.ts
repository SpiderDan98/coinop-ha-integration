// The Tags tab: each Tag with its Run count and total cost. A Tag is created and renamed
// (or merged into another by its name) in a dialog, and deleted once confirmed. The
// catalogue follows by subscription.
import { mdiDelete, mdiPencil, mdiPlus } from "@mdi/js";
import { LitElement, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { createTag, deleteTag, getAggregates, renameTag, type RunSummary } from "./api";
import { confirmDialog, formDialog } from "./dialog";
import { field, input } from "./fields";
import { formatter } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { Pagination, pagerStyles } from "./pagination";
import { shared } from "./styles";
import { table, tableStyles } from "./table";

@customElement("coinop-tags-page")
export class TagsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) tags?: string[];
  @property({ attribute: false }) runs: RunSummary[] = [];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** The dialog's draft: the Tag being renamed, none for a new one, and the name typed so far. */
  @state() private editing?: { tag?: string; name: string };
  /** Set while its delete confirmation is open. */
  @state() private deleting?: string;
  @state() private saving = false;
  /** What could not be done: "save" shows in the dialog, "delete" on the page. */
  @state() private failed?: "save" | "delete";
  /** Each Tag's total cost as the backend sums it; undefined until read. */
  @state() private costs?: Map<string | null | undefined, number>;
  private request = 0;
  private readonly pages = new Pagination(this);

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runs")) void this.load();
  }

  private async load() {
    const request = ++this.request;
    const groups = await getAggregates(this.hass, ["tag"]).catch(() => undefined);
    if (request !== this.request) return;
    this.costs = groups && new Map(groups.map((group) => [group.tag, group.cost]));
  }

  override render() {
    const t = localize(this.hass);
    if (!this.tags) return html`<p class="muted">${t("tags.loading")}</p>`;
    return html`
      <ha-button class="new-tag fab" @click=${() => this.edit()}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("tags.new")}
      </ha-button>
      ${
        this.tags.length
          ? table({
              name: "tags",
              columns: [
                { label: t("tags.tag") },
                { label: t("runs.title"), num: true },
                { label: t("sensor.total_cost"), num: true },
                {},
              ],
              rows: this.pages.of(this.tags).map((tag) => this.renderTag(tag, t)),
              pager: this.pages.controls(this.tags.length, t),
            })
          : html`<p class="muted">${t("tags.empty")}</p>`
      }
      ${this.failed === "delete" ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
      ${this.editing ? this.renderDialog(this.editing.tag, this.editing.name, t) : nothing}
      ${this.deleting === undefined ? nothing : this.renderDeleteDialog(this.deleting, t)}
    `;
  }

  private runsOf(tag: string) {
    return this.runs.filter((run) => run.tags.includes(tag)).length;
  }

  private renderTag(tag: string, t: Localize) {
    const total = this.costs && (this.costs.get(tag) ?? 0);
    return html`<tr class="tag">
      <td><span class="tag-name">${tag}</span></td>
      <td class="num">${this.runsOf(tag)}</td>
      <td class="num">${total === undefined ? nothing : formatter(this.hass).money(total)}</td>
      <td class="actions">
        <ha-icon-button
          class="rename"
          .label=${t("tags.rename")}
          .path=${mdiPencil}
          @click=${() => this.edit(tag)}
        ></ha-icon-button>
        <ha-icon-button
          class="delete"
          .label=${t("tags.delete")}
          .path=${mdiDelete}
          @click=${() => (this.deleting = tag)}
        ></ha-icon-button>
      </td>
    </tr>`;
  }

  /** `tag` is the Tag being renamed, undefined for a new one. */
  private renderDialog(tag: string | undefined, name: string, t: Localize) {
    const typed = name.trim().toLocaleLowerCase();
    const other = this.tags?.find(
      (existing) => existing !== tag && existing.toLocaleLowerCase() === typed,
    );
    const creating = tag === undefined;
    return formDialog({
      t,
      title: creating ? t("tags.new") : t("tags.rename_title", { tag }),
      name: "tag-dialog",
      submit: creating ? t("tags.new_create") : undefined,
      busy: this.saving,
      disabled: !typed || (creating && !!other),
      error: this.failed === "save" && t("run.save_failed"),
      onCancel: () => (this.editing = undefined),
      onSubmit: () => this.save(tag, name.trim()),
      content: field(
        t("tags.tag"),
        input({
          name: "name",
          maxlength: 40,
          autofocus: true,
          value: name,
          onInput: (entered) => (this.editing = { tag, name: entered }),
        }),
        { hint: other && t(creating ? "tags.exists" : "tags.merge_hint", { tag: other }) },
      ),
    });
  }

  private renderDeleteDialog(tag: string, t: Localize) {
    return confirmDialog({
      t,
      title: t("delete.title", { name: tag }),
      name: "delete-tag-dialog",
      content: html`<p>${t("tags.delete_hint", { tag, count: this.runsOf(tag) })}</p>`,
      confirm: t("tags.delete_confirm"),
      onCancel: () => (this.deleting = undefined),
      onConfirm: () => this.delete(tag),
    });
  }

  private edit(tag?: string) {
    this.failed = undefined;
    this.editing = { tag, name: tag ?? "" };
  }

  private async save(tag: string | undefined, name: string) {
    if (name === tag) return void (this.editing = undefined);
    this.saving = true;
    this.failed = undefined;
    try {
      await (tag === undefined ? createTag(this.hass, name) : renameTag(this.hass, tag, name));
      this.editing = undefined;
    } catch {
      this.failed = "save";
    } finally {
      this.saving = false;
    }
  }

  private async delete(tag: string) {
    this.deleting = undefined;
    this.failed = undefined;
    try {
      await deleteTag(this.hass, tag);
    } catch {
      this.failed = "delete";
    }
  }

  static override styles = [shared, tableStyles, pagerStyles];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-tags-page": TagsPage;
  }
}
