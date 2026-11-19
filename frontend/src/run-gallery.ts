import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { Device, RunSummary } from "./api";
import { formatter } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { deviceName, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";
import { sortTags, tagChip } from "./tag-input";

const SHOWN_TAGS = 2;

@customElement("wattbill-run-gallery")
export class RunGallery extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runs: RunSummary[] = [];
  /** Current Devices; Runs of any other Device are shown as removed. */
  @property({ attribute: false }) devices?: Device[];
  /** Every Tag there is, offered in the Tag filter. */
  @property({ attribute: false }) tags: string[] = [];
  /** Where Run pages live, e.g. "/wattbill". */
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private deviceId = "";
  /** Runs with any of these Tags pass the Tag filter, and untagged ones if `untagged`. */
  @state() private tagFilter: string[] = [];
  @state() private untagged = false;

  private matchesTags(run: RunSummary) {
    if (!this.tagFilter.length && !this.untagged) return true;
    return (
      (this.untagged && !run.tags.length) || run.tags.some((tag) => this.tagFilter.includes(tag))
    );
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const all = this.runs.toSorted((a, b) => b.started.localeCompare(a.started));
    const runs = all.filter(
      (run) => (!this.deviceId || run.device_id === this.deviceId) && this.matchesTags(run),
    );
    const total = runs.reduce((sum, run) => sum + run.total, 0);
    return html`
      <div class="head">
        <h2>${t("runs.title")}</h2>
        <span class="muted">${runs.length} · ${format.money(total)}</span>
      </div>
      ${all.length ? this.renderFilters(all, t) : ""}
      ${
        runs.length
          ? html`<div class="gallery">
              ${runs.map(
                (run) => html`
                  <a class="tile" href="${this.basePath}/run/${run.id}" @click=${followLink}>
                    <div class="image">
                      <div class="no-image">${t("run.no_image")}</div>
                      ${
                        run.flags.length
                          ? html`<span class="tile-flags">⚑ ${run.flags.length}</span>`
                          : nothing
                      }
                    </div>
                    <div class="body">
                      <div class="strong ellipsis">${runName(run, t)}</div>
                      <div class="muted small">
                        ${deviceName(run, this.devices, t)} · ${format.date(run.started)} ·
                        ${format.duration(run.running_seconds)}
                      </div>
                      <div class="row between">
                        ${outcomeChip(run, t)}<b>${format.money(run.total)}</b>
                      </div>
                      ${
                        run.part_count > 1
                          ? html`<div class="muted small">
                              ${t("run.per_part", {
                                amount: format.money(run.cost_per_part),
                                count: run.part_count,
                              })}
                            </div>`
                          : nothing
                      }
                      ${
                        run.tags.length
                          ? html`<div class="tags">
                              ${run.tags.slice(0, SHOWN_TAGS).map(tagChip)}
                              ${
                                run.tags.length > SHOWN_TAGS
                                  ? html`<span class="more-tags muted small"
                                      >${`+${run.tags.length - SHOWN_TAGS}`}</span
                                    >`
                                  : nothing
                              }
                            </div>`
                          : nothing
                      }
                    </div>
                  </a>
                `,
              )}
            </div>`
          : html`<p class="muted empty">${t("runs.empty")}</p>`
      }
    `;
  }

  private renderFilters(runs: RunSummary[], t: Localize) {
    const devices = new Map(this.devices?.map((device) => [device.id, device.name]));
    for (const run of runs) {
      if (!devices.has(run.device_id)) devices.set(run.device_id, deviceName(run, this.devices, t));
    }
    return html`<div class="filters row">
      <select
        class="device-filter"
        aria-label=${t("runs.filter_device")}
        @change=${(event: Event) => (this.deviceId = (event.target as HTMLSelectElement).value)}
      >
        <option value="">${t("runs.all_devices")}</option>
        ${[...devices].map(
          ([id, name]) =>
            html`<option value=${id} ?selected=${id === this.deviceId}>${name}</option>`,
        )}
      </select>
      ${this.renderTagFilter(runs, t)}
    </div>`;
  }

  private renderTagFilter(runs: RunSummary[], t: Localize) {
    const tags = sortTags([...new Set([...this.tags, ...runs.flatMap((run) => run.tags)])]);
    const chosen = [
      ...(this.untagged ? [t("runs.no_tag")] : []),
      ...tags.filter((tag) => this.tagFilter.includes(tag)),
    ];
    const toggle = (event: Event) => {
      const box = event.target as HTMLInputElement;
      if (box.classList.contains("no-tag")) this.untagged = box.checked;
      else
        this.tagFilter = box.checked
          ? [...this.tagFilter, box.value]
          : this.tagFilter.filter((tag) => tag !== box.value);
    };
    return html`<details class="tag-filter" aria-label=${t("runs.filter_tags")}>
      <summary>${chosen.length ? chosen.join(", ") : t("runs.all_tags")}</summary>
      <div class="options" @change=${toggle}>
        <label
          ><input type="checkbox" class="no-tag" .checked=${this.untagged} />${t(
            "runs.no_tag",
          )}</label
        >
        ${tags.map(
          (tag) =>
            html`<label
              ><input
                type="checkbox"
                .value=${tag}
                .checked=${this.tagFilter.includes(tag)}
              />${tag}</label
            >`,
        )}
      </div>
    </details>`;
  }

  static override styles = [
    shared,
    css`
      .head {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin: 8px 0 12px;
      }
      .filters {
        margin-bottom: 12px;
      }
      select,
      .tag-filter summary {
        font: inherit;
        color: inherit;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 6px 8px;
        max-width: 100%;
      }
      .tag-filter {
        position: relative;
      }
      .tag-filter summary {
        display: block;
        cursor: pointer;
        max-width: 260px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .tag-filter .options {
        position: absolute;
        z-index: 3;
        display: flex;
        flex-direction: column;
        gap: 4px;
        min-width: 180px;
        max-height: 320px;
        overflow-y: auto;
        margin-top: 4px;
        padding: 8px 10px;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
      }
      .tag-filter label {
        display: flex;
        gap: 6px;
        align-items: center;
        white-space: nowrap;
      }
      .tags {
        display: flex;
        gap: 4px;
        align-items: center;
        min-width: 0;
        overflow: hidden;
      }
      .gallery {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 14px;
      }
      :host([narrow]) .gallery {
        grid-template-columns: 1fr;
      }
      .tile {
        display: block;
        color: inherit;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 12px;
        overflow: hidden;
      }
      .tile:hover,
      .tile:focus-visible {
        border-color: var(--primary-color);
      }
      .image {
        position: relative;
      }
      .tile-flags {
        position: absolute;
        top: 8px;
        right: 8px;
        padding: 1px 7px;
        border-radius: 10px;
        font-size: 11px;
        background: var(--warning-color, #ffa600);
        color: #000;
      }
      .body {
        padding: 10px 12px;
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-gallery": RunGallery;
  }
}
