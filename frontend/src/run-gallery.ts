// Filter and selection belong to the Overview, which sets them from its tiles and charts too.
import { mdiMagnify } from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import { OUTCOMES, type Device, type RunSummary } from "./api";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import "./run-image";
import { RunsTotal } from "./runs-total";
import { deviceName, flagLabel, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";
import { sortTags, tagChip } from "./tag-input";

const SHOWN_TAGS = 2;

const OUTCOME_FILTERS = ["open", ...OUTCOMES, "failed_cancelled"] as const;

/** Tags match any of `tags`, or no Tag at all with `untagged`. */
export const NO_FILTER = {
  name: "",
  deviceId: "",
  month: "",
  outcome: "" as "" | (typeof OUTCOME_FILTERS)[number],
  flagged: false,
  tags: [] as string[],
  untagged: false,
};

export type Filter = typeof NO_FILTER;

/** Only final Runs go into a Cost Statement or can be deleted. */
export const selectable = (run: RunSummary) => run.finalised;

export function matches(run: RunSummary, filter: Filter, t: Localize, format: Format) {
  const outcome = run.ended === null ? "open" : (run.outcome ?? "unknown");
  const name = filter.name.trim().toLocaleLowerCase();
  return (
    (!name || runName(run, t).toLocaleLowerCase().includes(name)) &&
    (!filter.deviceId || run.device_id === filter.deviceId) &&
    (!filter.month || format.month(run.started) === filter.month) &&
    (!filter.outcome ||
      (filter.outcome === "failed_cancelled"
        ? outcome === "failed" || outcome === "cancelled"
        : outcome === filter.outcome)) &&
    (!filter.flagged || run.flags.length > 0) &&
    ((!filter.tags.length && !filter.untagged) ||
      (filter.untagged && !run.tags.length) ||
      run.tags.some((tag) => filter.tags.includes(tag)))
  );
}

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
  @property({ attribute: false }) filter = NO_FILTER;
  @property({ attribute: false }) selected: ReadonlySet<string> = new Set();

  private readonly total = new RunsTotal(this);
  private all: RunSummary[] = [];
  private shown: RunSummary[] = [];

  override connectedCallback() {
    super.connectedCallback();
    document.addEventListener("click", this.closeTagFilter);
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    document.removeEventListener("click", this.closeTagFilter);
  }

  private closeTagFilter = (event: Event) => {
    const details = this.renderRoot.querySelector<HTMLDetailsElement>("details.tag-filter");
    if (details?.open && !event.composedPath().includes(details)) details.open = false;
  };

  protected override willUpdate(changed: PropertyValues<this>) {
    if (!changed.has("runs") && !changed.has("filter") && !changed.has("hass")) return;
    const t = localize(this.hass);
    const format = formatter(this.hass);
    this.all = this.runs.toSorted((a, b) => b.started.localeCompare(a.started));
    this.shown = this.all.filter((run) => matches(run, this.filter, t, format));
    this.total.load(this.hass, this.shown);
  }

  private setFilter(changes: Partial<Filter>) {
    this.dispatchEvent(
      new CustomEvent("filter-changed", { detail: { ...this.filter, ...changes } }),
    );
  }

  private select(selected: Set<string>) {
    this.dispatchEvent(new CustomEvent("selection-changed", { detail: selected }));
  }

  private toggle(run: RunSummary, on: boolean) {
    const selected = new Set(this.selected);
    if (on) selected.add(run.id);
    else selected.delete(run.id);
    this.select(selected);
  }

  /** Selects every final Run the filter shows, or clears them if all are selected. */
  private selectAll(runs: RunSummary[]) {
    const ids = runs.filter(selectable).map((run) => run.id);
    const selected = new Set(this.selected);
    const all = ids.every((id) => selected.has(id));
    for (const id of ids) {
      if (all) selected.delete(id);
      else selected.add(id);
    }
    this.select(selected);
  }

  // Options are rendered after their select, so an option added in this render (a month
  // picked in the chart) can only be chosen once it exists.
  protected override updated() {
    const values = {
      ".device-filter": this.filter.deviceId,
      ".month-filter": this.filter.month,
      ".outcome-filter": this.filter.outcome,
    };
    for (const [selector, value] of Object.entries(values)) {
      const select = this.renderRoot.querySelector<HTMLSelectElement>(selector);
      if (select) select.value = value;
    }
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const { all, shown: runs } = this;
    const total = this.total.cost;
    return html`
      <div class="head">
        <h2>${t("runs.title")}</h2>
        <span class="muted"
          >${runs.length}${total === undefined ? nothing : ` · ${format.money(total)}`}</span
        >
      </div>
      ${all.length ? this.renderFilters(all, runs, t, format) : ""}
      ${
        runs.length
          ? html`<div class="gallery">
              ${repeat(
                runs,
                (run) => run.id,
                (run) => this.renderTile(run, t, format),
              )}
            </div>`
          : html`<p class="muted empty">${t(all.length ? "runs.no_match" : "runs.empty")}</p>`
      }
    `;
  }

  private renderTile(run: RunSummary, t: Localize, format: Format) {
    const selected = this.selected.has(run.id);
    return html`<div class="pick-tile ${selected ? "selected" : ""}">
      <a class="tile" href="${this.basePath}/run/${run.id}" @click=${followLink}>
        <div class="image">
          <wattbill-run-image .hass=${this.hass} .src=${run.cover?.tile_url}></wattbill-run-image>
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
            ${deviceName(run, this.devices, t)} · ${format.date(run.started)} ·
            ${format.duration(run.running_seconds)}
          </div>
          <div class="row between">${outcomeChip(run, t)}<b>${format.money(run.total)}</b></div>
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
      ${
        selectable(run)
          ? html`<input
              type="checkbox"
              class="pick"
              aria-label=${t("runs.select", { name: runName(run, t) })}
              .checked=${selected}
              @change=${(event: Event) =>
                this.toggle(run, (event.target as HTMLInputElement).checked)}
            />`
          : nothing
      }
    </div>`;
  }

  private renderFilters(runs: RunSummary[], shown: RunSummary[], t: Localize, format: Format) {
    const devices = new Map(this.devices?.map((device) => [device.id, device.name]));
    for (const run of runs) {
      if (!devices.has(run.device_id)) devices.set(run.device_id, deviceName(run, this.devices, t));
    }
    const months = [
      ...new Set([this.filter.month, ...runs.map((run) => format.month(run.started))]),
    ]
      .filter(Boolean)
      .sort()
      .reverse();
    const value = (event: Event) => (event.target as HTMLInputElement | HTMLSelectElement).value;
    return html`<div class="filters row">
      <div class="search">
        <ha-svg-icon .path=${mdiMagnify}></ha-svg-icon>
        <input
          type="search"
          class="name-filter"
          placeholder=${t("runs.search")}
          aria-label=${t("runs.search")}
          .value=${this.filter.name}
          @input=${(event: Event) => this.setFilter({ name: value(event) })}
        />
      </div>
      ${
        devices.size > 1 || this.filter.deviceId
          ? html`<select
              class="device-filter"
              aria-label=${t("runs.filter_device")}
              @change=${(event: Event) => this.setFilter({ deviceId: value(event) })}
            >
              <option value="">${t("runs.all_devices")}</option>
              ${[...devices].map(([id, name]) => html`<option value=${id}>${name}</option>`)}
            </select>`
          : nothing
      }
      ${
        months.length > 1 || this.filter.month
          ? html`<select
              class="month-filter"
              aria-label=${t("runs.filter_month")}
              @change=${(event: Event) => this.setFilter({ month: value(event) })}
            >
              <option value="">${t("runs.all_months")}</option>
              ${months.map(
                (month) => html`<option value=${month}>${format.monthName(month)}</option>`,
              )}
            </select>`
          : nothing
      }
      <select
        class="outcome-filter"
        aria-label=${t("runs.filter_outcome")}
        @change=${(event: Event) => this.setFilter({ outcome: value(event) as Filter["outcome"] })}
      >
        <option value="">${t("runs.any_outcome")}</option>
        ${OUTCOME_FILTERS.map(
          (outcome) =>
            html`<option value=${outcome}>
              ${t(outcome === "failed_cancelled" ? "runs.failed_cancelled" : `outcome.${outcome}`)}
            </option>`,
        )}
      </select>
      ${this.renderTagFilter(runs, t)}
      <label class="flagged-filter">
        <input
          type="checkbox"
          .checked=${this.filter.flagged}
          @change=${(event: Event) =>
            this.setFilter({ flagged: (event.target as HTMLInputElement).checked })}
        />⚑ ${t("runs.flagged_only")}
      </label>
      ${
        shown.some(selectable)
          ? html`<ha-button
              class="small select-all"
              appearance="plain"
              @click=${() => this.selectAll(shown)}
            >
              ${t("runs.select_all")}
            </ha-button>`
          : nothing
      }
    </div>`;
  }

  private renderTagFilter(runs: RunSummary[], t: Localize) {
    const tags = sortTags([...new Set([...this.tags, ...runs.flatMap((run) => run.tags)])]);
    if (!tags.length && !this.filter.untagged) return nothing;
    const chosen = [
      ...(this.filter.untagged ? [t("runs.no_tag")] : []),
      ...tags.filter((tag) => this.filter.tags.includes(tag)),
    ];
    const toggle = (event: Event) => {
      const box = event.target as HTMLInputElement;
      if (box.classList.contains("no-tag")) this.setFilter({ untagged: box.checked });
      else
        this.setFilter({
          tags: box.checked
            ? [...this.filter.tags, box.value]
            : this.filter.tags.filter((tag) => tag !== box.value),
        });
    };
    return html`<details
      class="tag-filter"
      aria-label=${t("runs.filter_tags")}
      @keydown=${(event: KeyboardEvent) => {
        if (event.key === "Escape") (event.currentTarget as HTMLDetailsElement).open = false;
      }}
    >
      <summary>${chosen.length ? chosen.join(", ") : t("runs.all_tags")}</summary>
      <div class="options" @change=${toggle}>
        <label
          ><input type="checkbox" class="no-tag" .checked=${this.filter.untagged} />${t(
            "runs.no_tag",
          )}</label
        >
        ${tags.map(
          (tag) =>
            html`<label
              ><input
                type="checkbox"
                .value=${tag}
                .checked=${this.filter.tags.includes(tag)}
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
      .select-all {
        margin-left: auto;
      }
      .filters {
        margin-bottom: 12px;
      }
      /* Outlined like the search and filter controls above HA's data tables. */
      .filters input[type="search"],
      .filters select,
      .tag-filter summary,
      .flagged-filter {
        height: 40px;
        min-height: 0;
        font: inherit;
        color: inherit;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--outline-color, var(--divider-color, rgba(0, 0, 0, 0.12)));
        border-radius: 10px;
        padding: 0 12px;
        max-width: 100%;
        box-sizing: border-box;
        box-shadow: none;
      }
      .filters input[type="search"]:focus-visible,
      .filters select:focus-visible,
      .tag-filter summary:focus-visible {
        outline: none;
        border-color: var(--primary-color);
      }
      .search {
        position: relative;
        flex: 1 1 240px;
        max-width: 480px;
      }
      .search ha-svg-icon {
        position: absolute;
        inset-inline-start: 10px;
        top: 50%;
        translate: 0 -50%;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
        pointer-events: none;
      }
      .filters input[type="search"] {
        width: 100%;
        padding-inline-start: 38px;
      }
      .flagged-filter {
        display: flex;
        align-items: center;
        gap: 6px;
        cursor: pointer;
      }
      :host([narrow]) .search {
        flex-basis: 100%;
        max-width: none;
      }
      .tag-filter {
        position: relative;
      }
      .tag-filter summary {
        display: block;
        line-height: 38px;
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
      .pick {
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
