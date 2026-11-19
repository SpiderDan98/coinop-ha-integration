// One Run as its own page: its facts on the left, Line Items by kind on the right.
// Refetches the Run whenever its summary changes, so it follows live updates.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { KINDS, getRun, type LineItem, type RunDetail, type RunSummary } from "./api";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import "./run-image";
import { outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";

const evidence = (item: LineItem, t: Localize) =>
  [
    item.method && t(`method.${item.method}`),
    item.segments.length > 1 && t("evidence.segments", { count: item.segments.length }),
  ]
    .filter(Boolean)
    .join(" · ");

@customElement("wattbill-run-page")
export class RunPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runId = "";
  /** The Run's entry in the live list; a new object means the Run changed. */
  @property({ attribute: false }) summary?: RunSummary;
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private run?: RunDetail;
  @state() private missing = false;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runId")) {
      this.run = undefined;
      this.missing = false;
    }
    if (changed.has("runId") || changed.has("summary")) void this.load();
  }

  private async load() {
    const request = ++this.request;
    try {
      const run = await getRun(this.hass, this.runId);
      if (request === this.request) [this.run, this.missing] = [run, false];
    } catch {
      if (request === this.request) [this.run, this.missing] = [undefined, true];
    }
  }

  override render() {
    const t = localize(this.hass);
    if (this.missing) {
      return html`<p>${t("run.not_found")}</p>
        <a href=${this.basePath} @click=${followLink}>${t("run.back")}</a>`;
    }
    if (!this.run) return html`<p class="muted">${t("run.loading")}</p>`;
    const run = this.run;
    const format = formatter(this.hass);
    return html`
      <div class="runbar row">
        ${outcomeChip(run, t)}
        <span class="muted">${run.device_name} · ${format.dateTime(run.started)}</span>
      </div>
      <div class="grid">
        <div class="card facts">
          <wattbill-run-image
            class="cover"
            .hass=${this.hass}
            .src=${run.cover?.url}
          ></wattbill-run-image>
          ${
            run.images.length
              ? html`<div class="strip">
                  ${run.images.map(
                    (image) =>
                      html`<figure>
                        <wattbill-run-image
                          .hass=${this.hass}
                          .src=${image.tile_url}
                        ></wattbill-run-image>
                        <figcaption>${t(`image.${image.kind}`)}</figcaption>
                      </figure>`,
                  )}
                </div>`
              : nothing
          }
          <h1>${runName(run, t)}</h1>
          <dl>
            <dt>${t("run.device")}</dt>
            <dd>${run.device_name}</dd>
            <dt>${t("run.started")}</dt>
            <dd>${format.dateTime(run.started)}</dd>
            <dt>${t("run.ended")}</dt>
            <dd>${run.ended ? format.dateTime(run.ended) : "—"}</dd>
            <dt>${t("run.running_time")}</dt>
            <dd>${format.duration(run.running_seconds)}</dd>
          </dl>
        </div>
        <div class="items">
          ${KINDS.map((kind) => {
            const items = run.line_items.filter((item) => item.kind === kind);
            return html`
              <div class="card kind" style="--kind-color: var(--wattbill-${kind})">
                <div class="row between">
                  <h3>${t(`kind.${kind}`)}</h3>
                  <b class="num">${format.money(run.subtotals[kind])}</b>
                </div>
                <table>
                  ${
                    items.length
                      ? items.map((item) => this.renderItem(item, t, format))
                      : html`<tr>
                          <td class="muted small">${t("run.none")}</td>
                        </tr>`
                  }
                </table>
              </div>
            `;
          })}
          <div class="card totals">
            <span>${t("run.total")}</span><span class="num">${format.money(run.total)}</span>
          </div>
        </div>
      </div>
    `;
  }

  private renderItem(item: LineItem, t: Localize, format: Format) {
    const why = evidence(item, t);
    return html`<tr>
      <td>
        <div>${item.label ?? t(`kind.${item.kind}`)}</div>
        ${why ? html`<div class="evidence">${why}</div>` : nothing}
      </td>
      <td class="num small muted">
        ${
          item.quantity === null
            ? nothing
            : `${format.quantity(item.quantity, item.unit)} × ${format.unitPrice(item.unit_price)}`
        }
      </td>
      <td class="num amount">${format.money(item.amount)}</td>
    </tr>`;
  }

  static override styles = [
    shared,
    css`
      .runbar {
        margin-bottom: 14px;
      }
      .grid {
        display: grid;
        grid-template-columns: 340px 1fr;
        gap: 18px;
        align-items: start;
      }
      :host([narrow]) .grid {
        grid-template-columns: 1fr;
      }
      .cover {
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 12px;
      }
      .strip {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
      }
      figure {
        margin: 0;
        width: 96px;
        text-align: center;
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      figure wattbill-run-image {
        border-radius: 6px;
        overflow: hidden;
        margin-bottom: 2px;
      }
      dl {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 6px 12px;
        margin: 0;
      }
      dt {
        color: var(--secondary-text-color);
      }
      dd {
        margin: 0;
      }
      .items {
        display: flex;
        flex-direction: column;
        gap: 12px;
        min-width: 0;
      }
      .kind h3::before {
        content: "";
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 3px;
        margin-right: 8px;
        background: var(--kind-color);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
      }
      td {
        padding: 6px 4px;
        border-bottom: 1px dotted var(--divider-color, rgba(0, 0, 0, 0.12));
        vertical-align: top;
      }
      tr:last-child td {
        border-bottom: 0;
      }
      .amount {
        width: 90px;
      }
      .evidence {
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      .totals {
        display: flex;
        justify-content: space-between;
        font-size: 22px;
        font-weight: 600;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-page": RunPage;
  }
}
