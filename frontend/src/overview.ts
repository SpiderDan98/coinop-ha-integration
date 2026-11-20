// The panel's start page: cost tiles and charts from the backend's aggregates, the Runs
// running now and the most recent Runs. Tiles and charts open the Runs tab filtered; the
// aggregates are read afresh whenever a Run changes.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { KINDS, getAggregates, getGroupings, type Device, type RunSummary } from "./api";
import { barRows, chartStyles, legend, stackedColumns } from "./charts";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { runsPath } from "./runs-query";
import { deviceName, runCount, runName } from "./run-parts";
import { runTile, tileStyles } from "./run-tile";
import { RunsTotal } from "./runs-total";
import { shared } from "./styles";

const MONTHS_SHOWN = 12;
const MATERIALS_SHOWN = 6;
const RECENT_SHOWN = 20;

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

@customElement("coinop-overview")
export class Overview extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Replaced, not changed, whenever a Run changes. */
  @property({ attribute: false }) runs: ReadonlyMap<string, RunSummary> = new Map();
  @property({ attribute: false }) devices?: Device[];
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** Undefined until loaded, null if loading failed. */
  @state() private aggregates?: Aggregates | null;
  private request = 0;
  private readonly failedTotal = new RunsTotal(this);

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runs")) void this.load();
    // Reads again only when its Runs or their costs changed.
    this.failedTotal.load(this.hass, [...this.runs.values()].filter(failedOrCancelled));
  }

  private async load() {
    const request = ++this.request;
    const aggregates = await loadAggregates(this.hass).catch(() => null);
    if (request === this.request) this.aggregates = aggregates;
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const recent = [...this.runs.values()]
      .sort((a, b) => b.started.localeCompare(a.started))
      .slice(0, RECENT_SHOWN);
    const context = { hass: this.hass, devices: this.devices, basePath: this.basePath, t, format };
    return html`
      ${this.renderStats(t, format)}
      <section class="recent">
        <div class="row between head">
          <h2>${t("overview.recent")}</h2>
          <a class="all-runs" href=${runsPath(this.basePath)} @click=${followLink}
            >${t("overview.all_runs")}</a
          >
        </div>
        ${
          recent.length
            ? html`<div class="gallery">${recent.map((run) => runTile(run, context))}</div>`
            : html`<p class="muted">${t("runs.empty")}</p>`
        }
      </section>
    `;
  }

  private renderStats(t: Localize, format: Format) {
    if (this.aggregates === null) return html`<p class="muted">${t("overview.error")}</p>`;
    // Until the totals arrive the tiles hold their place with dashes.
    const aggregates = this.aggregates;
    const { total, month } = aggregates ?? { total: undefined, month: [] };
    const money = (amount: number | undefined) =>
      aggregates && amount !== undefined ? format.money(amount) : "–";
    const runs = (count: number | undefined) => (aggregates ? runCount(count ?? 0, t) : "");
    const now = format.month(new Date().toISOString());
    const thisMonth = month.find((group) => group.month === now);
    const failed = [...this.runs.values()].filter(failedOrCancelled).length;
    const failedCost = this.failedTotal.cost;
    const flagged = total?.flagged_runs ?? 0;
    return html`
      <div class="stats">
        <div class="stat card this-month">
          <div class="muted small">${format.monthName(now)}</div>
          <div class="value">${money(thisMonth?.cost ?? 0)}</div>
          <div class="muted small">${runs(thisMonth?.runs)}</div>
        </div>
        <div class="stat card all-time">
          <div class="muted small">${t("overview.all_time")}</div>
          <div class="value">${money(total?.cost ?? 0)}</div>
          <div class="muted small">${runs(total?.runs)}</div>
        </div>
        <a
          class="stat card failed"
          href=${runsPath(this.basePath, { outcome: "failed_cancelled" })}
          @click=${followLink}
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
        </a>
        <a
          class="stat card flagged ${flagged ? "warn" : ""}"
          href=${runsPath(this.basePath, { flagged: true })}
          @click=${followLink}
        >
          <div class="muted small">${t("sensor.flagged_runs")}</div>
          <div class="value">⚑ ${aggregates ? flagged : "–"}</div>
          <div class="muted small">${t("overview.click_to_filter")}</div>
        </a>
      </div>
      ${
        aggregates
          ? html`<div class="charts">
              ${this.renderMonths(aggregates, now, t, format)}
              ${this.renderMaterials(aggregates, t, format)} ${this.renderRunning(t, format)}
            </div>`
          : nothing
      }
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
        label: format.monthShort(key),
        title: format.monthName(key),
        value: format.money(month.find((group) => group.month === key)?.cost ?? 0),
        href: runsPath(this.basePath, { month: key }),
        segments: KINDS.map((kind) => {
          const amount =
            monthKind.find((group) => group.month === key && group.kind === kind)?.cost ?? 0;
          return {
            amount,
            colour: `var(--coinop-${kind})`,
            title: `${t(`kind.${kind}`)}: ${format.money(amount)}`,
          };
        }),
      }));
    return html`<div class="card per-month">
      <div class="row between">
        <h3>${t("overview.per_month")}</h3>
        <span class="muted small">${t("overview.per_month_hint")}</span>
      </div>
      ${stackedColumns(columns)}
      ${legend(KINDS.map((kind) => ({ label: t(`kind.${kind}`), colour: `var(--coinop-${kind})` })))}
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
                colour: "var(--coinop-material)",
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

  static override styles = [
    shared,
    chartStyles,
    tileStyles,
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
      a.stat {
        display: block;
      }
      a.stat:hover,
      a.stat:focus-visible {
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
      .recent .head {
        margin-bottom: 12px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-overview": Overview;
  }
}
