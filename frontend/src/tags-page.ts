// The Tags tab: each Tag with its Run count and total cost, created, renamed (or merged
// into another by its name) and deleted here. The catalogue follows by subscription.
import { mdiDelete, mdiPencil, mdiPlus } from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { createTag, deleteTag, getAggregates, renameTag, type RunSummary } from "./api";
import { formatter } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";
import { table, tableStyles } from "./table";

@customElement("coinop-tags-page")
export class TagsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) tags?: string[];
  @property({ attribute: false }) runs: RunSummary[] = [];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** The new Tag's name typed so far while its form is open. */
  @state() private adding?: string;
  /** The Tag being renamed and the name typed so far. */
  @state() private renaming?: { tag: string; name: string };
  @state() private confirming?: string;
  @state() private failed = false;
  /** Each Tag's total cost as the backend sums it; undefined until read. */
  @state() private costs?: Map<string | null | undefined, number>;
  private request = 0;
  private focusRename = false;

  protected override updated(changed: PropertyValues) {
    // The form opens at the top, far from the floating button that opened it.
    if (changed.has("adding") && this.adding !== undefined && changed.get("adding") === undefined)
      this.renderRoot.querySelector<HTMLInputElement>("form.new input")?.focus();
    if (!this.focusRename) return;
    this.focusRename = false;
    const input = this.renderRoot.querySelector<HTMLInputElement>("input.rename");
    input?.focus();
    input?.select();
  }

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
      ${
        this.adding === undefined
          ? html`<ha-button class="new-tag fab" @click=${() => (this.adding = "")}>
              <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
              ${t("tags.new")}
            </ha-button>`
          : this.renderNew(this.adding, t)
      }
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
              rows: this.tags.map((tag) => this.renderTag(tag, t)),
            })
          : html`<p class="muted">${t("tags.empty")}</p>`
      }
      ${this.failed ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
    `;
  }

  private renderNew(name: string, t: Localize) {
    const typed = name.trim().toLocaleLowerCase();
    const existing = this.tags?.find((tag) => tag.toLocaleLowerCase() === typed);
    return html`<form
      class="card new"
      @submit=${(event: Event) => {
        event.preventDefault();
        void this.create();
      }}
    >
      <div class="row">
        <input
          maxlength="40"
          aria-label=${t("tags.tag")}
          .value=${name}
          @input=${(event: Event) => (this.adding = (event.target as HTMLInputElement).value)}
          @keydown=${(event: KeyboardEvent) => {
            if (event.key === "Escape") this.adding = undefined;
          }}
        />
        <ha-button type="submit" ?disabled=${!typed || !!existing}>
          ${t("tags.new_create")}
        </ha-button>
        <ha-button appearance="plain" @click=${() => (this.adding = undefined)}>
          ${t("tags.cancel")}
        </ha-button>
      </div>
      ${
        existing
          ? html`<div class="exists-hint muted small">${t("tags.exists", { tag: existing })}</div>`
          : nothing
      }
    </form>`;
  }

  private renderTag(tag: string, t: Localize) {
    const format = formatter(this.hass);
    const runs = this.runs.filter((run) => run.tags.includes(tag));
    const total = this.costs && (this.costs.get(tag) ?? 0);
    return html`<tr class="tag">
      <td>
        ${this.renaming?.tag === tag ? this.renderRename(tag, t) : html`<span class="tag-name">${tag}</span>`}
      </td>
      <td class="num">${runs.length}</td>
      <td class="num">${total === undefined ? nothing : format.money(total)}</td>
      <td class="actions">${this.renderActions(tag, runs.length, t)}</td>
    </tr>`;
  }

  private renderRename(tag: string, t: Localize) {
    const name = this.renaming?.name ?? tag;
    const typed = name.trim().toLocaleLowerCase();
    const target = this.tags?.find((other) => other !== tag && other.toLocaleLowerCase() === typed);
    return html`<input
        class="rename"
        maxlength="40"
        aria-label=${t("tags.rename")}
        .value=${name}
        @input=${(event: Event) =>
          (this.renaming = { tag, name: (event.target as HTMLInputElement).value })}
        @keydown=${(event: KeyboardEvent) => {
          if (event.key === "Enter") void this.rename();
          else if (event.key === "Escape") this.renaming = undefined;
        }}
      />${
        target
          ? html`<div class="merge-hint muted small">${t("tags.merge_hint", { tag: target })}</div>`
          : nothing
      }`;
  }

  private renderActions(tag: string, runs: number, t: Localize) {
    if (this.renaming?.tag === tag) {
      return html`<ha-button
          class="small"
          ?disabled=${!this.renaming.name.trim()}
          @click=${this.rename}
        >
          ${t("tags.save")}
        </ha-button>
        <ha-button class="small" appearance="plain" @click=${() => (this.renaming = undefined)}>
          ${t("tags.cancel")}
        </ha-button>`;
    }
    if (this.confirming === tag) {
      return html`<div class="delete-hint muted small">
          ${t("tags.delete_hint", { tag, count: runs })}
        </div>
        <ha-button class="small" variant="danger" @click=${() => this.delete(tag)}>
          ${t("tags.delete_confirm")}
        </ha-button>
        <ha-button class="small" appearance="plain" @click=${() => (this.confirming = undefined)}>
          ${t("tags.cancel")}
        </ha-button>`;
    }
    return html`<ha-icon-button
        class="rename"
        .label=${t("tags.rename")}
        .path=${mdiPencil}
        @click=${() => {
          this.renaming = { tag, name: tag };
          this.confirming = undefined;
          this.focusRename = true;
        }}
      ></ha-icon-button>
      <ha-icon-button
        class="delete"
        .label=${t("tags.delete")}
        .path=${mdiDelete}
        @click=${() => {
          this.confirming = tag;
          this.renaming = undefined;
        }}
      ></ha-icon-button>`;
  }

  private async create() {
    const name = this.adding?.trim();
    if (!name || this.tags?.some((tag) => tag.toLocaleLowerCase() === name.toLocaleLowerCase()))
      return;
    this.adding = undefined;
    await this.attempt(createTag(this.hass, name));
  }

  private async rename() {
    const renaming = this.renaming;
    const name = renaming?.name.trim();
    if (!renaming || !name) return;
    this.renaming = undefined;
    await this.attempt(renameTag(this.hass, renaming.tag, name));
  }

  private async delete(tag: string) {
    this.confirming = undefined;
    await this.attempt(deleteTag(this.hass, tag));
  }

  private async attempt(request: Promise<unknown>) {
    this.failed = false;
    try {
      await request;
    } catch {
      this.failed = true;
    }
  }

  static override styles = [
    shared,
    tableStyles,
    css`
      .tags {
        max-width: 900px;
      }
      .delete-hint {
        white-space: normal;
        margin-bottom: 6px;
      }
      input {
        width: 100%;
      }
      form.new {
        max-width: 900px;
        margin-bottom: 12px;
        box-sizing: border-box;
      }
      form.new input {
        flex: 1;
        width: auto;
        min-width: 160px;
      }
      .exists-hint {
        margin-top: 6px;
      }
      .error {
        color: var(--error-color, #db4437);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-tags-page": TagsPage;
  }
}
