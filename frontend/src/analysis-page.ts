// The Analysis tab: tables of totals across all Devices from the backend's aggregates,
// read afresh whenever a Run changes.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { KINDS, OUTCOMES, getGroupings, type Device, type Group, type RunSummary } from "./api";
import { formatter, type Format } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { deviceName } from "./run-parts";
import { shared } from "./styles";

type Aggregates = Awaited<ReturnType<typeof loadAggregates>>;

async function loadAggregates(hass: HomeAssistant) {
  const { total, material, ...groups } = await getGroupings(hass, {
    total: [],
    kind: ["kind"],
    device: ["device"],
    month: ["month"],
    material: ["kind", "material"],
    outcome: ["outcome"],
    tag: ["tag"],
  });
  return {
    ...groups,
    cost: total[0]?.cost ?? 0,
    // Electricity and Other Line Items have no Material either.
    material: material.filter((group) => group.kind === "material"),
  };
}

/** A card with a table whose columns after the first hold numbers. */
function table(
  name: string,
  title: string,
  {
    head,
    rows,
    foot,
    hint,
    empty,
  }: { head: string[]; rows: (string | number)[][]; foot?: string[]; hint?: string; empty: string },
) {
  const cells = (row: (string | number)[], tag: "th" | "td") =>
    row.map((value, index) =>
      tag === "th"
        ? html`<th class=${index ? "num" : ""}>${value}</th>`
        : html`<td class=${index ? "num" : ""}>${value}</td>`,
    );
  return html`<section class="card ${name}">
    <header>
      <h3>${title}</h3>
      ${hint ? html`<p class="small hint">${hint}</p>` : nothing}
    </header>
    <table>
      <thead>
        <tr>
          ${cells(head, "th")}
        </tr>
      </thead>
      <tbody>
        ${
          rows.length
            ? rows.map(
                (row) =>
                  html`<tr>
                    ${cells(row, "td")}
                  </tr>`,
              )
            : html`<tr class="empty">
                <td colspan=${head.length} class="muted">${empty}</td>
              </tr>`
        }
      </tbody>
      ${
        foot
          ? html`<tfoot>
              <tr>
                ${cells(foot, "td")}
              </tr>
            </tfoot>`
          : nothing
      }
    </table>
  </section>`;
}

@customElement("wattbill-analysis-page")
export class AnalysisPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Replaced, not changed, whenever a Run changes. */
  @property({ attribute: false }) runs: ReadonlyMap<string, RunSummary> = new Map();
  @property({ attribute: false }) devices?: Device[];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** Undefined until loaded, null if loading failed. */
  @state() private aggregates?: Aggregates | null;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runs")) void this.load();
  }

  private async load() {
    const request = ++this.request;
    const aggregates = await loadAggregates(this.hass).catch(() => null);
    if (request === this.request) this.aggregates = aggregates;
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const aggregates = this.aggregates;
    return html`
      <p class="muted small intro">${t("analysis.intro")}</p>
      ${
        aggregates === null
          ? html`<p class="muted">${t("overview.error")}</p>`
          : !aggregates
            ? html`<p class="muted">${t("analysis.loading")}</p>`
            : !this.runs.size
              ? html`<p class="muted">${t("runs.empty")}</p>`
              : html`<div class="tables">
                  ${this.renderKinds(aggregates, t, format)}
                  ${this.renderDevices(aggregates, t, format)}
                  ${this.renderMonths(aggregates, t, format)}
                  ${this.renderMaterials(aggregates, t, format)}
                  ${this.renderOutcomes(aggregates, t, format)}
                  ${this.renderTags(aggregates, t, format)}
                </div>`
      }
    `;
  }

  private renderKinds({ cost, kind }: Aggregates, t: Localize, format: Format) {
    return table("by-kind", t("analysis.by_kind"), {
      head: [t("analysis.kind"), t("analysis.cost"), t("analysis.share")],
      rows: KINDS.map((key) => {
        const amount = kind.find((group) => group.kind === key)?.cost ?? 0;
        return [t(`kind.${key}`), format.money(amount), share(amount, cost, format)];
      }),
      foot: [t("run.total"), format.money(cost), ""],
      empty: "",
    });
  }

  private renderDevices({ device }: Aggregates, t: Localize, format: Format) {
    return table("by-device", t("analysis.by_device"), {
      head: [
        t("run.device"),
        t("runs.title"),
        t("run.running_time"),
        t("analysis.energy"),
        t("analysis.cost"),
      ],
      rows: device.map((group) => [
        deviceName(group, this.devices, t),
        group.runs,
        format.duration(group.running_hours * 3600),
        format.quantity(group.energy_kwh, "kWh"),
        format.money(group.cost),
      ]),
      empty: t("analysis.empty"),
    });
  }

  private renderMonths({ month }: Aggregates, t: Localize, format: Format) {
    return table("by-month", t("analysis.by_month"), {
      head: [
        t("analysis.month"),
        t("runs.title"),
        ...KINDS.map((kind) => t(`kind.${kind}`)),
        t("run.total"),
      ],
      rows: month
        .toSorted((a, b) => (b.month ?? "").localeCompare(a.month ?? ""))
        .map((group) => [
          format.monthName(group.month ?? ""),
          group.runs,
          ...KINDS.map((kind) => format.money(group[`${kind}_cost`])),
          format.money(group.cost),
        ]),
      empty: t("analysis.empty"),
    });
  }

  private renderMaterials({ material }: Aggregates, t: Localize, format: Format) {
    return table("by-material", t("analysis.by_material"), {
      head: [t("item.material"), t("analysis.used"), t("analysis.cost"), t("analysis.per_kg")],
      rows: material
        .toSorted((a, b) => Number(!a.material_id) - Number(!b.material_id) || b.cost - a.cost)
        .map((group) => [
          group.material_name ?? t("item.no_material"),
          format.quantity(group.material_grams, "g"),
          format.money(group.cost),
          group.material_grams > 0 ? format.money((group.cost / group.material_grams) * 1000) : "–",
        ]),
      empty: t("overview.no_material_cost"),
    });
  }

  private renderOutcomes({ cost, outcome }: Aggregates, t: Localize, format: Format) {
    const rank = (group: Group) =>
      group.outcome ? OUTCOMES.indexOf(group.outcome) : OUTCOMES.length;
    return table("by-outcome", t("analysis.by_outcome"), {
      head: [t("run.outcome"), t("runs.title"), t("analysis.cost"), t("analysis.share")],
      rows: outcome
        .toSorted((a, b) => rank(a) - rank(b))
        .map((group) => [
          t(`outcome.${group.outcome ?? "open"}`),
          group.runs,
          format.money(group.cost),
          share(group.cost, cost, format),
        ]),
      empty: t("analysis.empty"),
    });
  }

  private renderTags({ tag }: Aggregates, t: Localize, format: Format) {
    return table("by-tag overlapping", t("analysis.by_tag"), {
      head: [t("tags.tag"), t("runs.title"), t("analysis.cost")],
      rows: tag.map((group) => [
        group.tag ?? t("runs.no_tag"),
        group.runs,
        format.money(group.cost),
      ]),
      hint: t("analysis.tag_overlap"),
      empty: t("tags.empty"),
    });
  }

  static override styles = [
    shared,
    css`
      .intro {
        margin: 0 0 12px;
      }
      .tables {
        container-type: inline-size;
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
        grid-auto-flow: dense;
        gap: 16px;
        align-items: start;
      }
      .by-month {
        grid-column: 1 / -1;
      }
      /* Five columns of figures don't fit one 400px column; spans two once there are two. */
      @container (min-width: 816px) {
        .by-device {
          grid-column: span 2;
        }
      }
      :host([narrow]) .tables {
        grid-template-columns: minmax(0, 1fr);
      }
      td:first-child {
        min-width: 7em;
      }
      .card {
        padding: 0;
        overflow-x: auto;
      }
      header {
        padding: 12px 14px 8px;
      }
      .hint {
        margin: 4px 0 0;
        color: var(--secondary-text-color);
      }
      .overlapping {
        border-style: dashed;
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      th,
      td {
        padding: 7px 14px;
        text-align: left;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      th {
        font-weight: 500;
        font-size: 12px;
        color: var(--secondary-text-color);
        white-space: nowrap;
      }
      th.num,
      td.num {
        text-align: right;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }
      tr.empty td {
        text-align: left;
      }
      tbody tr:last-child td {
        border-bottom: 0;
      }
      tfoot td {
        font-weight: 500;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-bottom: 0;
      }
      :host([narrow]) th,
      :host([narrow]) td {
        padding: 6px 10px;
      }
    `,
  ];
}

const share = (amount: number, total: number, format: Format) =>
  total ? format.percent(amount / total) : "–";

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-analysis-page": AnalysisPage;
  }
}
