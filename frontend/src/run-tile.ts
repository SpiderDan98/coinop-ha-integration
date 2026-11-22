// A Run's gallery tile, on the Overview and the Runs tab; only the Runs tab picks Runs.
import { css, html, nothing } from "lit";
import type { Device, RunSummary } from "./api";
import type { Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import type { Localize } from "./localize";
import "./run-image";
import { deviceName, flagLabel, outcomeChip, runName } from "./run-parts";
import { tagChip } from "./tag-input";

const SHOWN_TAGS = 2;

export function runTile(
  run: RunSummary,
  {
    hass,
    devices,
    basePath,
    t,
    format,
  }: { hass: HomeAssistant; devices?: Device[]; basePath: string; t: Localize; format: Format },
  pick?: { selected: boolean; toggle: (on: boolean) => void },
) {
  return html`<div class="pick-tile ${pick?.selected ? "selected" : ""}">
    <a class="tile" href="${basePath}/run/${run.id}" @click=${followLink}>
      <div class="image">
        <coinop-run-image .hass=${hass} .src=${run.cover?.tile_url}></coinop-run-image>
        ${
          run.flags.length
            ? html`<span
                class="tile-flags"
                title=${run.flags.map((flag) => flagLabel(flag, t)).join("\n")}
                >⚑ ${run.flags.length}</span
              >`
            : nothing
        }
      </div>
      <div class="body">
        <div class="strong ellipsis">${runName(run, t)}</div>
        <div class="muted small">
          ${deviceName(run, devices, t)} · ${format.date(run.started)} ·
          ${format.duration(run.running_seconds)}
        </div>
        ${
          run.part_count !== null && run.cost_per_part !== null && run.part_count > 1
            ? html`<div class="muted small">
                ${t("run.per_part", { amount: format.money(run.cost_per_part), count: run.part_count })}
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
        <div class="row between foot">${outcomeChip(run, t)}<b>${format.money(run.total)}</b></div>
      </div>
    </a>
    ${
      pick
        ? html`<input
            type="checkbox"
            class="pick"
            aria-label=${t("runs.select", { name: runName(run, t) })}
            .checked=${pick.selected}
            @change=${(event: Event) => pick.toggle((event.target as HTMLInputElement).checked)}
          />`
        : nothing
    }
  </div>`;
}

/** The tiles' grid (`.gallery`) and the tiles. */
export const tileStyles = css`
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;
  }
  :host([narrow]) .gallery {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .pick-tile {
    position: relative;
    border-radius: 12px;
  }
  .pick-tile.selected {
    outline: 3px solid var(--primary-color);
  }
  .pick-tile .pick {
    position: absolute;
    top: 8px;
    left: 8px;
    width: 20px;
    height: 20px;
    margin: 0;
    cursor: pointer;
    accent-color: var(--primary-color);
  }
  .tile {
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    height: 100%;
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
    flex: 1;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .foot {
    margin-top: auto;
  }
  .tags {
    display: flex;
    gap: 4px;
    align-items: center;
    min-width: 0;
    overflow: hidden;
  }
`;
