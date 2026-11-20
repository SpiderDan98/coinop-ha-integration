// The Runs tab's list: filters and the Runs as gallery or table, as this browser last
// chose. Filter and selection belong to the Runs tab, which keeps the filter in the URL.
import { mdiMagnify, mdiTableLarge, mdiViewGridOutline } from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";
import type { Device, RunSummary } from "./api";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import {
  DEFAULT_SORT,
  NO_FILTER,
  OUTCOME_FILTERS,
  matches,
  programmed,
  selectable,
  sorted,
  type Filter,
} from "./runs-query";
import "./run-image";
import { deviceName, flagLabel, outcomeChip, runCount, runName } from "./run-parts";
import { runTile, tileStyles } from "./run-tile";
import { RunsTotal } from "./runs-total";
import { shared } from "./styles";
import { table, tableStyles } from "./table";
import { sortTags, tagChip } from "./tag-input";

const VIEWS = ["gallery", "table"] as const;
const VIEW_KEY = "coinop-runs-view";
// Programs are trimmed, so a blank value can't be one.
const NO_PROGRAM = " ";

/** The view this browser last chose; the gallery without one. */
function storedView() {
  try {
    return VIEWS.find((view) => view === localStorage.getItem(VIEW_KEY)) ?? "gallery";
  } catch {
    return "gallery";
  }
}

@customElement("coinop-run-list")
export class RunList extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runs: RunSummary[] = [];
  /** Current Devices; Runs of any other Device are shown as removed. */
  @property({ attribute: false }) devices?: Device[];
  /** Every Tag there is, offered in the Tag filter. */
  @property({ attribute: false }) tags: string[] = [];
  /** Where Run pages live, e.g. "/coinop". */
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;
  @property({ attribute: false }) filter = NO_FILTER;
  @property({ attribute: false }) sort = DEFAULT_SORT;
  @property({ attribute: false }) selected: ReadonlySet<string> = new Set();

  @state() private view = storedView();
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
    const inputs = ["runs", "filter", "sort", "devices", "hass"] as const;
    if (!inputs.some((name) => changed.has(name))) return;
    const t = localize(this.hass);
    const format = formatter(this.hass);
    this.all = sorted(this.runs, this.sort, t, this.devices);
    this.shown = this.all.filter((run) => matches(run, this.filter, t, format, this.devices));
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

  private show(view: (typeof VIEWS)[number]) {
    this.view = view;
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch {
      // Private mode or storage switched off: the choice lasts until the page is left.
    }
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
      ".program-filter": this.filter.noProgram ? NO_PROGRAM : this.filter.program,
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
      <div class="head row between">
        <span class="muted"
          >${runCount(runs.length, t)}${total === undefined ? nothing : ` · ${format.money(total)}`}</span
        >
        ${this.renderToggle(t)}
      </div>
      ${all.length ? this.renderFilters(all, runs, t, format) : ""}
      ${
        !runs.length
          ? html`<p class="muted empty">${t(all.length ? "runs.no_match" : "runs.empty")}</p>`
          : this.view === "table"
            ? this.renderTable(runs, t, format)
            : html`<div class="gallery">
                ${repeat(
                  runs,
                  (run) => run.id,
                  (run) =>
                    runTile(
                      run,
                      {
                        hass: this.hass,
                        devices: this.devices,
                        basePath: this.basePath,
                        t,
                        format,
                      },
                      selectable(run)
                        ? {
                            selected: this.selected.has(run.id),
                            toggle: (on) => this.toggle(run, on),
                          }
                        : undefined,
                    ),
                )}
              </div>`
      }
    `;
  }

  private renderToggle(t: Localize) {
    const icons = { gallery: mdiViewGridOutline, table: mdiTableLarge };
    return html`<div class="view-toggle" role="group" aria-label=${t("runs.view")}>
      ${VIEWS.map(
        (view) =>
          html`<button
            class="show-${view}"
            aria-pressed=${this.view === view ? "true" : "false"}
            aria-label=${t(`runs.view_${view}`)}
            title=${t(`runs.view_${view}`)}
            @click=${() => this.show(view)}
          >
            <ha-svg-icon .path=${icons[view]}></ha-svg-icon>
          </button>`,
      )}
    </div>`;
  }

  private renderTable(runs: RunSummary[], t: Localize, format: Format) {
    return table({
      name: "runs",
      columns: this.narrow
        ? [
            {},
            { label: t("run.name"), sort: "name" },
            { label: t("run.total"), num: true, sort: "total" },
          ]
        : [
            {},
            {},
            { label: t("run.name"), sort: "name" },
            { label: t("run.device"), sort: "device" },
            { label: t("runs.start"), sort: "start" },
            { label: t("runs.duration"), num: true, sort: "duration" },
            { label: t("run.outcome") },
            { label: t("run.tags") },
            { label: t("runs.flags") },
            { label: t("run.total"), num: true, sort: "total" },
            { label: t("runs.per_part"), num: true, sort: "per_part" },
          ],
      sort: this.sort,
      onSort: (sort) => this.dispatchEvent(new CustomEvent("sort-changed", { detail: sort })),
      rows: repeat(
        runs,
        (run) => run.id,
        (run) => this.renderRow(run, t, format),
      ),
    });
  }

  private renderRow(run: RunSummary, t: Localize, format: Format) {
    const path = `${this.basePath}/run/${run.id}`;
    const selected = this.selected.has(run.id);
    const pick = html`<td class="pick-cell">
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
    </td>`;
    const name = html`<a href=${path} @click=${followLink}>${runName(run, t)}</a>`;
    // The whole row opens the Run; its link and checkbox cell act on their own.
    const open = (event: MouseEvent) => {
      const own = event
        .composedPath()
        .some(
          (target) =>
            target instanceof HTMLAnchorElement ||
            (target instanceof HTMLElement && target.classList.contains("pick-cell")),
        );
      if (!own) navigate(path);
    };
    if (this.narrow)
      return html`<tr class="run ${selected ? "selected" : ""}" @click=${open}>
        ${pick}
        <td class="name">
          <div class="strong">${name}</div>
          <div class="muted small">
            ${deviceName(run, this.devices, t)} · ${format.date(run.started)}
          </div>
        </td>
        <td class="num">${format.money(run.total)}</td>
      </tr>`;
    return html`<tr class="run ${selected ? "selected" : ""}" @click=${open}>
      ${pick}
      <td class="cover">
        <coinop-run-image .hass=${this.hass} .src=${run.cover?.tile_url}></coinop-run-image>
      </td>
      <td class="name strong">${name}</td>
      <td>${deviceName(run, this.devices, t)}</td>
      <td class="nowrap">${format.dateTime(run.started)}</td>
      <td class="num">${format.duration(run.running_seconds)}</td>
      <td>${outcomeChip(run, t)}</td>
      <td><div class="tags">${run.tags.map(tagChip)}</div></td>
      <td class="nowrap">
        ${
          run.flags.length
            ? html`<span title=${run.flags.map((flag) => flagLabel(flag, t)).join("\n")}
                >⚑ ${run.flags.length}</span
              >`
            : nothing
        }
      </td>
      <td class="num">${format.money(run.total)}</td>
      <td class="num">
        ${run.part_count !== null && run.cost_per_part !== null && run.part_count > 1 ? format.money(run.cost_per_part) : nothing}
      </td>
    </tr>`;
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
      ${this.renderProgramFilter(runs, t)} ${this.renderTagFilter(runs, t)}
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

  private renderProgramFilter(runs: RunSummary[], t: Localize) {
    const { program, noProgram } = this.filter;
    if (!program && !noProgram && !runs.some((run) => programmed(run, this.devices)))
      return nothing;
    const programs = [...new Set([program, ...runs.map((run) => run.program ?? "")])]
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b));
    return html`<select
      class="program-filter"
      aria-label=${t("runs.filter_program")}
      @change=${(event: Event) => {
        const value = (event.target as HTMLSelectElement).value;
        this.setFilter(
          value === NO_PROGRAM
            ? { program: "", noProgram: true }
            : { program: value, noProgram: false },
        );
      }}
    >
      <option value="">${t("runs.all_programs")}</option>
      ${programs.map((name) => html`<option .value=${name}>${name}</option>`)}
      <option .value=${NO_PROGRAM}>${t("runs.no_program")}</option>
    </select>`;
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
    tileStyles,
    tableStyles,
    css`
      .head {
        margin: 0 0 12px;
      }
      .view-toggle {
        display: flex;
        border: 1px solid var(--outline-color, var(--divider-color, rgba(0, 0, 0, 0.12)));
        border-radius: 10px;
        overflow: hidden;
      }
      .view-toggle button {
        display: grid;
        place-items: center;
        width: 40px;
        height: 32px;
        padding: 0;
        border: 0;
        cursor: pointer;
        color: var(--secondary-text-color);
        background: var(--card-background-color, #fff);
        --mdc-icon-size: 20px;
      }
      .view-toggle button[aria-pressed="true"] {
        color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent);
      }
      .view-toggle button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }
      tr.run {
        cursor: pointer;
      }
      tr.run:hover td {
        background: var(--secondary-background-color, #ededed);
      }
      tr.run.selected td {
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 10%, transparent);
      }
      tr.run a {
        color: inherit;
      }
      .pick-cell {
        width: 20px;
      }
      .pick-cell .pick {
        width: 18px;
        height: 18px;
        margin: 0;
        cursor: pointer;
      }
      .cover coinop-run-image {
        width: 56px;
        border-radius: 6px;
        overflow: hidden;
      }
      .nowrap {
        white-space: nowrap;
      }
      .runs .tags {
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-run-list": RunList;
  }
}
