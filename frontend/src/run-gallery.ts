import { LitElement, css, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { RunSummary } from "./api";
import { formatter } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize } from "./localize";
import { outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";

@customElement("wattbill-run-gallery")
export class RunGallery extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runs: RunSummary[] = [];
  /** Where Run pages live, e.g. "/wattbill". */
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const runs = this.runs.toSorted((a, b) => b.started.localeCompare(a.started));
    const total = runs.reduce((sum, run) => sum + run.total, 0);
    return html`
      <div class="head">
        <h2>${t("runs.title")}</h2>
        <span class="muted">${runs.length} · ${format.money(total)}</span>
      </div>
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
                        ${run.device_name} · ${format.date(run.started)} ·
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

  static override styles = [
    shared,
    css`
      .head {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin: 8px 0 12px;
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
