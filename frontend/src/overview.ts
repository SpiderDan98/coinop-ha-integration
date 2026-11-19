// The panel's start page: cost tiles and charts from the backend's aggregates, the Runs
// running now, the gallery, and a basket of selected final Runs. Tiles and charts set
// the gallery's filter; the aggregates are read afresh whenever a Run changes.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  KINDS,
  deleteRuns,
  getAggregates,
  getGroupings,
  previewDelete,
  type Device,
  type RunSummary,
  type Totals,
} from "./api";
import { barRows, chartStyles, legend, stackedColumns } from "./charts";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import "./run-gallery";
import "./statement-dialog";
import { NO_FILTER, selectable, type Filter } from "./run-gallery";
import { deleteDialog, deviceName, runName } from "./run-parts";
import { RunsTotal } from "./runs-total";
import { shared } from "./styles";

const MONTHS_SHOWN = 12;
const MATERIALS_SHOWN = 6;

type Aggregates = Awaited<ReturnType<typeof loadAggregates>>;

async function loadAggregates(hass: HomeAssistant) {
  const { total, month, monthKind, material } = await getGroupings(hass, {
    total: [],
    month: ["month"],
    monthKind: ["month", "kind"],
    material: ["kind", "material"],
  });
  const materials = material
    .filter((group) => group.kind === "material" && (group.cost !== 0 || group.material_grams > 0))
    .sort((a, b) => b.cost - a.cost);
  const shown = materials.length > MATERIALS_SHOWN ? MATERIALS_SHOWN - 1 : MATERIALS_SHOWN;
  const rest = materials.slice(shown).map((group) => group.material_id ?? null);
  const others = rest.length
    ? (await getAggregates(hass, ["kind"], { material_ids: rest })).find(
        (group) => group.kind === "material",
      )
    : undefined;
  return { total: total[0], month, monthKind, materials: materials.slice(0, shown), others };
}

const runCount = (count: number, t: Localize) =>
  count === 1 ? t("overview.run_one") : t("overview.runs", { count });

const failedOrCancelled = (run: RunSummary) =>
  run.outcome === "failed" || run.outcome === "cancelled";

/** Every "YYYY-MM" from `first` to `last`. */
function monthsBetween(first: string, last: string) {
  const months = [];
  let [year, month] = first.split("-").map(Number);
  for (let key = first; key <= last;) {
    months.push(key);
    [year, month] = month === 12 ? [year + 1, 1] : [year, month + 1];
    key = `${year}-${String(month).padStart(2, "0")}`;
  }
  return months;
}

@customElement("wattbill-overview")
export class Overview extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Replaced, not changed, whenever a Run changes. */
  @property({ attribute: false }) runs: ReadonlyMap<string, RunSummary> = new Map();
  @property({ attribute: false }) devices?: Device[];
  @property({ attribute: false }) tags: string[] = [];
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private filter = NO_FILTER;
  @state() private selected: ReadonlySet<string> = new Set();
  /** Undefined until loaded, null if loading failed. */
  @state() private aggregates?: Aggregates | null;
  /** Set while the delete confirmation is open. */
  @state() private drop?: Totals;
  @state() private deleteFailed = false;
  @state() private exporting = false;
  private request = 0;
  private readonly failedTotal = new RunsTotal(this);
  private readonly basketTotal = new RunsTotal(this);

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runs")) void this.load();
    // Each reads again only when its Runs or their costs changed.
    this.failedTotal.load(this.hass, [...this.runs.values()].filter(failedOrCancelled));
    this.basketTotal.load(this.hass, this.selectedRuns());
  }

  private async load() {
    const request = ++this.request;
    const aggregates = await loadAggregates(this.hass).catch(() => null);
    if (request === this.request) this.aggregates = aggregates;
  }

  /** The selected Runs that are still there and final, by start. */
  selectedRuns() {
    return [...this.runs.values()]
      .filter((run) => this.selected.has(run.id) && selectable(run))
      .sort((a, b) => a.started.localeCompare(b.started));
  }

  private setFilter(changes: Partial<Filter>) {
    this.filter = { ...this.filter, ...changes };
  }

  private async confirmDelete() {
    this.deleteFailed = false;
    try {
      this.drop = await previewDelete(
        this.hass,
        this.selectedRuns().map((run) => run.id),
      );
    } catch {
      this.deleteFailed = true;
    }
  }

  private async delete() {
    try {
      await deleteRuns(
        this.hass,
        this.selectedRuns().map((run) => run.id),
      );
      this.selected = new Set();
    } catch {
      this.deleteFailed = true;
    }
    this.drop = undefined;
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const selected = this.selectedRuns();
    return html`
      ${this.renderStats(t, format)}
      <wattbill-run-gallery
        class=${selected.length ? "with-basket" : ""}
        .hass=${this.hass}
        .runs=${[...this.runs.values()]}
        .devices=${this.devices}
        .tags=${this.tags}
        .basePath=${this.basePath}
        .filter=${this.filter}
        .selected=${new Set(selected.map((run) => run.id))}
        ?narrow=${this.narrow}
        @filter-changed=${(event: CustomEvent<Filter>) => (this.filter = event.detail)}
        @selection-changed=${(event: CustomEvent<Set<string>>) => (this.selected = event.detail)}
      ></wattbill-run-gallery>
      ${selected.length ? this.renderBasket(selected, t, format) : nothing}
      ${
        this.exporting && selected.length
          ? html`<wattbill-statement-dialog
              .hass=${this.hass}
              .runIds=${selected.map((run) => run.id)}
              .tag=${this.filter.tags.length === 1 && !this.filter.untagged ? this.filter.tags[0] : undefined}
              @close=${() => (this.exporting = false)}
            ></wattbill-statement-dialog>`
          : nothing
      }
      ${
        this.drop
          ? deleteDialog(t("delete.title_many", { count: selected.length }), this.drop, t, format, {
              cancel: () => (this.drop = undefined),
              confirm: () => void this.delete(),
            })
          : nothing
      }
    `;
  }

  private renderStats(t: Localize, format: Format) {
    if (this.aggregates === null) return html`<p class="muted">${t("overview.error")}</p>`;
    if (!this.aggregates) return nothing;
    const { total, month } = this.aggregates;
    const now = format.month(new Date().toISOString());
    const thisMonth = month.find((group) => group.month === now);
    const failed = [...this.runs.values()].filter(failedOrCancelled).length;
    const failedCost = this.failedTotal.cost;
    const flagged = total?.flagged_runs ?? 0;
    const failedOn = this.filter.outcome === "failed_cancelled";
    return html`
      <div class="stats">
        <div class="stat card this-month">
          <div class="muted small">${format.monthName(now)}</div>
          <div class="value">${format.money(thisMonth?.cost ?? 0)}</div>
          <div class="muted small">${runCount(thisMonth?.runs ?? 0, t)}</div>
        </div>
        <div class="stat card all-time">
          <div class="muted small">${t("overview.all_time")}</div>
          <div class="value">${format.money(total?.cost ?? 0)}</div>
          <div class="muted small">${runCount(total?.runs ?? 0, t)}</div>
        </div>
        <button
          class="stat card failed ${failedOn ? "on" : ""}"
          aria-pressed=${failedOn ? "true" : "false"}
          @click=${() => this.setFilter({ outcome: failedOn ? "" : "failed_cancelled" })}
        >
          <div class="muted small">${t("overview.failed_cancelled")}</div>
          <div class="value">${failedCost === undefined ? "–" : format.money(failedCost)}</div>
          <div class="muted small">
            ${
              total && total.cost > 0 && failedCost !== undefined
                ? t("overview.failed_share", {
                    runs: runCount(failed, t),
                    share: format.percent(failedCost / total.cost),
                  })
                : runCount(failed, t)
            }
          </div>
        </button>
        <button
          class="stat card flagged ${this.filter.flagged ? "on" : ""} ${flagged ? "warn" : ""}"
          aria-pressed=${this.filter.flagged ? "true" : "false"}
          @click=${() => this.setFilter({ flagged: !this.filter.flagged })}
        >
          <div class="muted small">${t("sensor.flagged_runs")}</div>
          <div class="value">⚑ ${flagged}</div>
          <div class="muted small">
            ${t(this.filter.flagged ? "overview.filtering" : "overview.click_to_filter")}
          </div>
        </button>
      </div>
      <div class="charts">
        ${this.renderMonths(this.aggregates, now, t, format)}
        ${this.renderMaterials(this.aggregates, t, format)} ${this.renderRunning(t, format)}
      </div>
    `;
  }

  private renderMonths({ month, monthKind }: Aggregates, now: string, t: Localize, format: Format) {
    const first = month[0]?.month ?? now;
    const last = month.reduce(
      (latest, group) => (group.month && group.month > latest ? group.month : latest),
      now,
    );
    const columns = monthsBetween(first, last)
      .slice(-MONTHS_SHOWN)
      .map((key) => ({
        key,
        label: format.monthShort(key),
        title: format.monthName(key),
        value: format.money(month.find((group) => group.month === key)?.cost ?? 0),
        on: this.filter.month === key,
        segments: KINDS.map((kind) => {
          const amount =
            monthKind.find((group) => group.month === key && group.kind === kind)?.cost ?? 0;
          return {
            amount,
            colour: `var(--wattbill-${kind})`,
            title: `${t(`kind.${kind}`)}: ${format.money(amount)}`,
          };
        }),
      }));
    return html`<div class="card per-month">
      <div class="row between">
        <h3>${t("overview.per_month")}</h3>
        <span class="muted small">${t("overview.per_month_hint")}</span>
      </div>
      ${stackedColumns(columns, (key) =>
        this.setFilter({ month: this.filter.month === key ? "" : key }),
      )}
      ${legend(KINDS.map((kind) => ({ label: t(`kind.${kind}`), colour: `var(--wattbill-${kind})` })))}
    </div>`;
  }

  private renderMaterials({ materials, others }: Aggregates, t: Localize, format: Format) {
    const rows = materials.map((group) => ({
      label: group.material_name ?? t("item.no_material"),
      cost: group.cost,
    }));
    if (others) rows.push({ label: t("overview.other_materials"), cost: others.cost });
    return html`<div class="card by-material">
      <h3>${t("overview.by_material")}</h3>
      ${
        rows.length
          ? barRows(
              rows.map((row) => ({
                label: row.label,
                value: format.money(row.cost),
                amount: row.cost,
                colour: "var(--wattbill-material)",
              })),
            )
          : html`<p class="muted small">${t("overview.no_material_cost")}</p>`
      }
    </div>`;
  }

  private renderRunning(t: Localize, format: Format) {
    const running = [...this.runs.values()].filter((run) => run.ended === null);
    if (!running.length) return nothing;
    return html`<div class="card running">
      <h3>${t("overview.running_now")}</h3>
      ${running.map(
        (run) =>
          html`<a class="live" href="${this.basePath}/run/${run.id}" @click=${followLink}>
            <div class="strong ellipsis">${runName(run, t)}</div>
            <div class="muted small">
              ${deviceName(run, this.devices, t)} · ${format.duration(run.running_seconds)}
            </div>
            <div class="live-cost">${format.money(run.total)}</div>
          </a>`,
      )}
      <div class="muted small">${t("overview.provisional")}</div>
    </div>`;
  }

  private renderBasket(runs: RunSummary[], t: Localize, format: Format) {
    return html`<aside class="basket card" aria-label=${t("basket.title")}>
      <div class="row between">
        <b>${runCount(runs.length, t)}</b>
        <b class="num"
          >${this.basketTotal.cost === undefined ? nothing : format.money(this.basketTotal.cost)}</b
        >
      </div>
      <div class="muted small names">${runs.map((run) => runName(run, t)).join(", ")}</div>
      <div class="row actions">
        <button class="btn small statement" @click=${() => (this.exporting = true)}>
          ${t("basket.statement")}
        </button>
        <button class="btn small danger delete" @click=${this.confirmDelete}>
          ${t("basket.delete")}
        </button>
        <button class="btn small clear" @click=${() => (this.selected = new Set())}>
          ${t("basket.clear")}
        </button>
      </div>
      ${this.deleteFailed ? html`<p class="error small">${t("basket.delete_failed")}</p>` : nothing}
    </aside>`;
  }

  static override styles = [
    shared,
    chartStyles,
    css`
      .stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
      }
      .stat {
        font: inherit;
        color: inherit;
        text-align: left;
        padding: 14px;
      }
      button.stat {
        cursor: pointer;
      }
      button.stat:hover,
      button.stat:focus-visible,
      .stat.on {
        border-color: var(--primary-color);
      }
      .stat.warn {
        border-color: var(--warning-color, #ffa600);
      }
      .stat .value {
        font-size: 24px;
        font-weight: 500;
        margin: 4px 0 2px;
        font-variant-numeric: tabular-nums;
      }
      :host {
        display: block;
      }
      .charts {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
        gap: 16px;
        margin-bottom: 20px;
        align-items: start;
      }
      :host([narrow]) .charts {
        grid-template-columns: minmax(0, 1fr);
      }
      .running {
        border-color: var(--primary-color);
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .live {
        display: block;
        color: inherit;
      }
      .live-cost {
        font-size: 26px;
        margin-top: 6px;
        font-variant-numeric: tabular-nums;
      }
      .with-basket {
        display: block;
        padding-bottom: 160px;
      }
      .basket {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 4;
        width: min(320px, calc(100vw - 32px));
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 8px;
        border: 2px solid var(--primary-color);
        box-shadow: 0 6px 22px rgba(0, 0, 0, 0.2);
      }
      :host([narrow]) .basket {
        right: 16px;
        bottom: 16px;
      }
      .names {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }
      .error {
        color: var(--error-color, #db4437);
        margin: 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-overview": Overview;
  }
}
