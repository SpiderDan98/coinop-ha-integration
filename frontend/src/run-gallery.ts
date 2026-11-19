import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import type { Device, RunSummary } from "./api";
import { formatter } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import "./run-image";
import { deviceName, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";

@customElement("wattbill-run-gallery")
export class RunGallery extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runs: RunSummary[] = [];
  /** Current Devices; Runs of any other Device are shown as removed. */
  @property({ attribute: false }) devices?: Device[];
  /** Where Run pages live, e.g. "/wattbill". */
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private deviceId = "";

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const all = this.runs.toSorted((a, b) => b.started.localeCompare(a.started));
    const runs = this.deviceId ? all.filter((run) => run.device_id === this.deviceId) : all;
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
              ${repeat(
                runs,
                (run) => run.id,
                (run) => html`
                  <a class="tile" href="${this.basePath}/run/${run.id}" @click=${followLink}>
                    <div class="image">
                      <wattbill-run-image
                        .hass=${this.hass}
                        .src=${run.cover?.tile_url}
                      ></wattbill-run-image>
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
    </div>`;
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
      select {
        font: inherit;
        color: inherit;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 6px 8px;
        max-width: 100%;
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
