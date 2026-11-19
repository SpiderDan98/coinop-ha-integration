// One Run as its own page: its fields on the left, Flags and Line Items by kind on the
// right. Every change saves at once. Refetches the Run whenever its summary changes,
// so it follows live updates.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  KINDS,
  OUTCOMES,
  clearFlag,
  deleteRuns,
  endRun,
  getRun,
  previewDelete,
  updateRun,
  type Drop,
  type LineItem,
  type Outcome,
  type RunDetail,
  type RunSummary,
} from "./api";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { isKey, localize, type Localize } from "./localize";
import { outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";

const evidence = (item: LineItem, t: Localize) =>
  [
    item.method && t(`method.${item.method}`),
    item.segments.length > 1 && t("evidence.segments", { count: item.segments.length }),
  ]
    .filter(Boolean)
    .join(" · ");

const flagLabel = (flag: string, t: Localize) => {
  const key = `flag.${flag}`;
  return isKey(key) ? t(key) : flag;
};

/** What each field shows, as its input's value. */
const fieldValues = (run: RunDetail, format: Format) => ({
  name: run.name ?? "",
  note: run.note ?? "",
  started: format.toInput(run.started),
  ended: run.ended ? format.toInput(run.ended) : "",
  outcome: run.outcome ?? "",
  part_count: String(run.part_count),
});

type Field = keyof ReturnType<typeof fieldValues>;

/** The correction a field's new value asks for; undefined if it is no valid value. */
const correction = (field: Field, value: string, format: Format) => {
  switch (field) {
    case "name":
    case "note":
      return { [field]: value.trim() || null };
    case "started":
    case "ended": {
      const iso = format.fromInput(value);
      return iso && { [field]: iso };
    }
    case "outcome":
      return { outcome: value as Outcome };
    case "part_count":
      return /^\d+$/.test(value) && Number(value) >= 1 ? { part_count: Number(value) } : undefined;
  }
};

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
  @state() private failed = false;
  /** Set while the delete confirmation is open. */
  @state() private drop?: Drop;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runId")) {
      this.run = undefined;
      this.missing = false;
      this.failed = false;
      this.drop = undefined;
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

  /** Show the Run as a command returned it; `undo` puts the field back on failure. */
  private async save(result: Promise<RunDetail>, undo = () => {}) {
    this.failed = false;
    try {
      ++this.request;
      this.run = await result;
    } catch {
      this.failed = true;
      undo();
    }
  }

  private onFieldChange(event: Event) {
    if (!this.run) return;
    const input = event.target as HTMLInputElement;
    const field = input.name as Field;
    const format = formatter(this.hass);
    const shown = fieldValues(this.run, format)[field];
    const undo = () => (input.value = shown);
    const changes = correction(field, input.value, format);
    if (!changes) return undo();
    void this.save(updateRun(this.hass, this.runId, changes), undo);
  }

  private async confirmDelete() {
    this.failed = false;
    try {
      this.drop = await previewDelete(this.hass, [this.runId]);
    } catch {
      this.failed = true;
    }
  }

  private async delete() {
    try {
      await deleteRuns(this.hass, [this.runId]);
      navigate(this.basePath);
    } catch {
      this.failed = true;
    }
    this.drop = undefined;
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
        <span class="spacer"></span>
        <span class="muted small">${t("run.saves")}</span>
        ${
          run.ended === null
            ? html`<button
                class="btn end-run"
                @click=${() => this.save(endRun(this.hass, this.runId))}
              >
                ${t("run.end_now")}
              </button>`
            : nothing
        }
        <button
          class="btn danger delete-run"
          ?disabled=${!run.finalised}
          @click=${this.confirmDelete}
        >
          ${t("run.delete")}
        </button>
      </div>
      <div class="grid">
        <div class="card facts">
          <div class="no-image">${t("run.no_image")}</div>
          ${this.renderFields(run, t, format)}
          <dl>
            <dt>${t("run.device")}</dt>
            <dd>${run.device_name}</dd>
            <dt>${t("run.running_time")}</dt>
            <dd>${format.duration(run.running_seconds)}</dd>
          </dl>
        </div>
        <div class="items">
          ${
            run.flags.length
              ? html`<div class="flags">
                  ${run.flags.map(
                    (flag) =>
                      html`<div class="flag">
                        <span>⚑</span><span class="text">${flagLabel(flag, t)}</span>
                        <button
                          class="btn small"
                          @click=${() => this.save(clearFlag(this.hass, this.runId, flag))}
                        >
                          ${t("run.mark_checked")}
                        </button>
                      </div>`,
                  )}
                </div>`
              : nothing
          }
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
            <span class="big">${t("run.total")}</span
            ><span class="big num">${format.money(run.total)}</span>
            <span class="muted">${t("run.cost_per_part", { count: run.part_count })}</span
            ><span class="muted num">${format.money(run.cost_per_part)}</span>
          </div>
        </div>
      </div>
      ${this.drop ? this.renderDeleteDialog(run, this.drop, t, format) : nothing}
    `;
  }

  private renderFields(run: RunDetail, t: Localize, format: Format) {
    const values = fieldValues(run, format);
    const locked = !run.finalised;
    return html`<div class="fields" @change=${this.onFieldChange}>
      <label class="wide"
        >${t("run.name")}<input
          name="name"
          .value=${values.name}
          placeholder=${run.job_name ?? t("run.untitled")}
      /></label>
      <label
        >${t("run.started")}<input
          type="datetime-local"
          name="started"
          .value=${values.started}
          ?disabled=${locked}
      /></label>
      <label
        >${t("run.ended")}<input
          type="datetime-local"
          name="ended"
          .value=${values.ended}
          ?disabled=${locked}
      /></label>
      <label
        >${t("run.outcome")}<select name="outcome" ?disabled=${locked}>
          ${run.outcome === null ? html`<option value="" selected>—</option>` : nothing}
          ${OUTCOMES.map(
            (outcome) =>
              html`<option value=${outcome} ?selected=${outcome === run.outcome}>
                ${t(`outcome.${outcome}`)}
              </option>`,
          )}
        </select></label
      >
      <label
        >${t("run.part_count")}<input
          type="number"
          name="part_count"
          min="1"
          step="1"
          .value=${values.part_count}
      /></label>
      <label class="wide"
        >${t("run.note")}<textarea name="note" .value=${values.note}></textarea>
      </label>
      <p class="wide muted small">${t(locked ? "run.locked_hint" : "run.times_hint")}</p>
      ${this.failed ? html`<p class="wide error small">${t("run.save_failed")}</p>` : nothing}
    </div>`;
  }

  private renderDeleteDialog(run: RunDetail, drop: Drop, t: Localize, format: Format) {
    const rows = [
      [t("sensor.total_cost"), format.money(drop.cost)],
      [t("sensor.energy_in_runs"), format.quantity(drop.energy_kwh, "kWh")],
      [t("sensor.material_used"), format.quantity(drop.material_grams, "g")],
      [t("runs.title"), String(drop.runs)],
      [t("sensor.flagged_runs"), String(drop.flagged_runs)],
    ];
    return html`<div class="scrim">
      <div class="dialog card" role="alertdialog" aria-modal="true">
        <h2>${t("delete.title", { name: runName(run, t) })}</h2>
        <p>${t("delete.drop")}</p>
        <dl>
          ${rows.map(
            ([label, value]) =>
              html`<dt>${label}</dt>
                <dd class="num">${value}</dd>`,
          )}
        </dl>
        <p class="muted small">${t("delete.warning")}</p>
        <div class="row end">
          <button class="btn cancel" @click=${() => (this.drop = undefined)}>
            ${t("delete.cancel")}
          </button>
          <button class="btn danger confirm" @click=${this.delete}>${t("delete.confirm")}</button>
        </div>
      </div>
    </div>`;
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
      .spacer {
        flex: 1;
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
      .facts .no-image {
        border-radius: 10px;
        margin-bottom: 12px;
      }
      .fields {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-bottom: 12px;
      }
      .fields > * {
        min-width: 0;
      }
      .fields p {
        margin: 0;
      }
      .wide {
        grid-column: span 2;
      }
      label {
        display: flex;
        flex-direction: column;
        gap: 3px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      input,
      select,
      textarea {
        font: inherit;
        font-size: 14px;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 6px 8px;
        width: 100%;
        box-sizing: border-box;
      }
      textarea {
        resize: vertical;
        min-height: 56px;
      }
      :disabled {
        opacity: 0.6;
      }
      .error {
        color: var(--error-color, #db4437);
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
      .flags {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .flag {
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 8px 10px;
        border-radius: 8px;
        background: color-mix(in srgb, var(--warning-color, #ffa600) 12%, transparent);
      }
      .flag .text {
        flex: 1;
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
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 4px 16px;
      }
      .big {
        font-size: 22px;
        font-weight: 600;
      }
      .scrim {
        position: fixed;
        inset: 0;
        z-index: 5;
        display: grid;
        place-items: center;
        padding: 16px;
        background: rgba(0, 0, 0, 0.4);
      }
      .dialog {
        width: min(480px, 100%);
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .dialog p {
        margin: 0;
      }
      .end {
        justify-content: flex-end;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-page": RunPage;
  }
}
