// The Tags tab: each Tag with its Run count and total cost, renamed (or merged into
// another by its name) and deleted here. The catalogue follows by subscription.
import { mdiDelete, mdiPencil } from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { deleteTag, getAggregates, renameTag, type RunSummary } from "./api";
import { formatter } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";

@customElement("wattbill-tags-page")
export class TagsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) tags?: string[];
  @property({ attribute: false }) runs: RunSummary[] = [];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** The Tag being renamed and the name typed so far. */
  @state() private renaming?: { tag: string; name: string };
  @state() private confirming?: string;
  @state() private failed = false;
  /** Each Tag's total cost as the backend sums it; undefined until read. */
  @state() private costs?: Map<string | null | undefined, number>;
  private request = 0;
  private focusRename = false;

  protected override updated() {
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
        this.tags.length
          ? html`<table>
              <thead>
                <tr>
                  <th>${t("tags.tag")}</th>
                  <th class="num">${t("runs.title")}</th>
                  <th class="num">${t("sensor.total_cost")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${this.tags.map((tag) => this.renderTag(tag, t))}
              </tbody>
            </table>`
          : html`<p class="muted">${t("tags.empty")}</p>`
      }
      ${this.failed ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
    `;
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
    css`
      table {
        width: 100%;
        max-width: 900px;
        border-collapse: collapse;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 12px;
      }
      th,
      td {
        padding: 8px 12px;
        text-align: left;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        vertical-align: middle;
      }
      th {
        font-weight: 500;
        color: var(--secondary-text-color);
      }
      th.num,
      td.num {
        text-align: right;
      }
      tr:last-child td {
        border-bottom: 0;
      }
      .actions {
        text-align: right;
        white-space: nowrap;
      }
      .actions ha-icon-button {
        --ha-icon-button-size: 36px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .delete-hint {
        white-space: normal;
        margin-bottom: 6px;
      }
      input {
        width: 100%;
      }
      .error {
        color: var(--error-color, #db4437);
      }
      :host([narrow]) th,
      :host([narrow]) td {
        padding: 6px 8px;
      }
      :host([narrow]) .actions {
        white-space: normal;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-tags-page": TagsPage;
  }
}
