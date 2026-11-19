// One Run as its own page: its fields on the left, Flags and Line Items by kind on the
// right. Every change saves at once. Refetches the Run whenever its summary changes,
// so it follows live updates.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  KINDS,
  OUTCOMES,
  addLineItem,
  clearFlag,
  deleteLineItem,
  deleteRuns,
  endRun,
  getRun,
  previewDelete,
  resetLineItem,
  updateLineItem,
  updateRun,
  type Device,
  type Drop,
  type LineItem,
  type Outcome,
  type RunDetail,
  type RunSummary,
} from "./api";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { isKey, localize, type Localize } from "./localize";
import "./run-images";
import { deviceName, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";
import "./tag-input";

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

/** A number input's number: null when emptied, undefined if it is no number. */
const parseNumber = (value: string) => {
  if (value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
};

/** What each Line Item field shows, as its input's value. */
const itemValues = (item: LineItem, format: Format) => ({
  label: item.label ?? "",
  unit: item.unit,
  quantity: format.toNumberInput(item.quantity, 4),
  unit_price: format.toNumberInput(item.unit_price, 4),
  amount: format.toAmountInput(item.amount),
});

type ItemField = keyof ReturnType<typeof itemValues>;

/** The change an edited Line Item field asks for; undefined if it is no valid value. */
const itemChange = (field: ItemField, value: string) => {
  switch (field) {
    case "label":
      return { label: value.trim() || null };
    case "unit":
      return { unit: value.trim() };
    case "quantity": {
      const quantity = parseNumber(value);
      return quantity === undefined ? undefined : { quantity };
    }
    case "unit_price":
    case "amount": {
      const price = parseNumber(value);
      return price === undefined || price === null ? undefined : { [field]: price };
    }
  }
};

const VALUES = ["quantity", "unit_price", "amount"] as const;

/** A Line Item value as the user reads it, e.g. "0.15 kWh" or "€0.30". */
const shownValue = (
  item: LineItem,
  values: NonNullable<LineItem["computed"]>,
  field: (typeof VALUES)[number],
  format: Format,
) => {
  if (field === "amount") return format.money(values.amount);
  if (field === "unit_price") return format.unitPrice(values.unit_price);
  return values.quantity === null ? "—" : format.quantity(values.quantity, item.unit);
};

@customElement("wattbill-run-page")
export class RunPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) runId = "";
  /** The Run's entry in the live list; a new object means the Run changed. */
  @property({ attribute: false }) summary?: RunSummary;
  /** Current Devices; any other Device is shown as removed. */
  @property({ attribute: false }) devices?: Device[];
  /** Every Tag there is, for suggestions. */
  @property({ attribute: false }) tags: string[] = [];
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private run?: RunDetail;
  @state() private missing = false;
  /** Where the last change that could not be saved was made. */
  @state() private failed?: "fields" | "items";
  /** Set while the delete confirmation is open. */
  @state() private drop?: Drop;
  /** Set while the form for a new Other Line Item is open. */
  @state() private adding = false;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runId")) {
      this.run = undefined;
      this.missing = false;
      this.failed = undefined;
      this.drop = undefined;
      this.adding = false;
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
  private async save(
    result: Promise<RunDetail>,
    undo = () => {},
    where: "fields" | "items" = "fields",
  ) {
    this.failed = undefined;
    try {
      ++this.request;
      this.run = await result;
      return true;
    } catch {
      this.failed = where;
      undo();
      return false;
    }
  }

  /** Run a Line Item command; its failure is shown with the Line Items. */
  private saveItems(result: Promise<RunDetail>, undo?: () => void) {
    return this.save(result, undo, "items");
  }

  private onItemChange(item: LineItem, event: Event) {
    const input = event.target as HTMLInputElement;
    const field = input.name as ItemField;
    const shown = itemValues(item, formatter(this.hass))[field];
    const undo = () => (input.value = shown);
    const changes = itemChange(field, input.value);
    if (!changes) return undo();
    void this.saveItems(updateLineItem(this.hass, this.runId, item.id, changes), undo);
  }

  private async onAdd(event: SubmitEvent) {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const entered = Object.fromEntries(new FormData(form)) as Record<string, string>;
    const quantity = parseNumber(entered.quantity ?? "");
    const unitPrice = parseNumber(entered.unit_price ?? "");
    if (quantity === undefined || unitPrice === undefined || unitPrice === null) return;
    const item = {
      label: (entered.label ?? "").trim() || null,
      quantity,
      unit: (entered.unit ?? "").trim(),
      unit_price: unitPrice,
    };
    if (await this.saveItems(addLineItem(this.hass, this.runId, item))) this.adding = false;
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

  private onImagesChanged(event: CustomEvent<RunDetail>) {
    ++this.request;
    this.run = event.detail;
  }

  private async confirmDelete() {
    this.failed = undefined;
    try {
      this.drop = await previewDelete(this.hass, [this.runId]);
    } catch {
      this.failed = "fields";
    }
  }

  private async delete() {
    try {
      await deleteRuns(this.hass, [this.runId]);
      navigate(this.basePath);
    } catch {
      this.failed = "fields";
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
    const device = deviceName(run, this.devices, t);
    return html`
      <div class="runbar row">
        ${outcomeChip(run, t)}
        <span class="muted">${device} · ${format.dateTime(run.started)}</span>
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
          <wattbill-run-images
            .hass=${this.hass}
            .run=${run}
            @run-changed=${this.onImagesChanged}
          ></wattbill-run-images>
          ${this.renderFields(run, t, format)}
          <dl>
            <dt>${t("run.device")}</dt>
            <dd>${device}</dd>
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
          ${this.failed === "items" ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
          ${KINDS.map((kind) => {
            const items = run.line_items.filter((item) => item.kind === kind);
            return html`
              <div class="card kind" style="--kind-color: var(--wattbill-${kind})">
                <div class="row between">
                  <h3>${t(`kind.${kind}`)}</h3>
                  <b class="num">${format.money(run.subtotals[kind])}</b>
                </div>
                ${
                  items.length
                    ? items.map((item) => this.renderItem(item, t, format))
                    : html`<p class="muted small">${t("run.none")}</p>`
                }
                ${kind === "other" ? this.renderAdd(t) : nothing}
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
      <div class="wide label">
        ${t("run.tags")}
        <wattbill-tag-input
          .hass=${this.hass}
          .tags=${run.tags}
          .catalog=${this.tags}
          .label=${t("run.tags")}
          @tags-change=${(event: CustomEvent<string[]>) =>
            this.save(updateRun(this.hass, this.runId, { tags: event.detail }))}
        ></wattbill-tag-input>
      </div>
      <p class="wide muted small">${t(locked ? "run.locked_hint" : "run.times_hint")}</p>
      ${this.failed === "fields" ? html`<p class="wide error small">${t("run.save_failed")}</p>` : nothing}
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
    const shown = itemValues(item, format);
    const { computed, locked } = item;
    // Labels and units WattBill sets stay as they are, rendered in the output language.
    const entered = item.kind !== "electricity";
    const number = (field: (typeof VALUES)[number]) => {
      const manual = computed !== null && computed[field] !== item[field];
      return html`<input
        type="number"
        step="any"
        name=${field}
        class=${manual ? "manual" : ""}
        title=${manual ? t("item.computed", { value: shownValue(item, computed, field, format) }) : ""}
        aria-label=${t(`item.${field}`)}
        min=${field === "quantity" || item.kind !== "other" ? "0" : nothing}
        .value=${shown[field]}
        ?disabled=${locked}
      />`;
    };
    return html`<div
      class="item ${computed ? "manual" : ""} ${locked ? "locked" : ""}"
      data-id=${item.id}
      @change=${(event: Event) => this.onItemChange(item, event)}
    >
      <div class="label">
        ${
          entered
            ? html`<input name="label" aria-label=${t("item.label")} .value=${shown.label} />`
            : html`<div>${item.label ?? t(`kind.${item.kind}`)}</div>`
        }
        ${why ? html`<div class="evidence">${why}</div>` : nothing}
        ${
          item.segments.length > 1
            ? html`<ul class="evidence segments">
                ${item.segments.map(
                  (segment) =>
                    html`<li>
                      ${format.timeRange(segment.start, segment.end)} ·
                      ${format.quantity(segment.kwh, "kWh")} ×
                      ${format.unitPrice(segment.unit_price)}
                    </li>`,
                )}
              </ul>`
            : nothing
        }
      </div>
      <div class="quantity">
        ${number("quantity")}
        ${
          entered
            ? html`<input
                name="unit"
                class="unit"
                aria-label=${t("item.unit")}
                .value=${shown.unit}
              />`
            : html`<span class="unit muted small">${item.unit}</span>`
        }
      </div>
      ${number("unit_price")} ${number("amount")}
      <div class="actions">
        ${locked ? html`<span class="lock" title=${t("item.locked")}>🔒</span>` : nothing}
        ${
          computed
            ? html`<button
                class="icon reset"
                title=${t(
                  "item.reset",
                  Object.fromEntries(
                    VALUES.map((field) => [field, shownValue(item, computed, field, format)]),
                  ),
                )}
                @click=${() => this.saveItems(resetLineItem(this.hass, this.runId, item.id))}
              >
                ↺
              </button>`
            : nothing
        }
        ${
          item.deletable
            ? html`<button
                class="icon delete"
                title=${t("item.delete")}
                @click=${() => this.saveItems(deleteLineItem(this.hass, this.runId, item.id))}
              >
                🗑
              </button>`
            : nothing
        }
      </div>
    </div>`;
  }

  private renderAdd(t: Localize) {
    return html`<div class="add-item">
      ${
        this.adding
          ? html`<form @submit=${this.onAdd}>
              <input
                name="label"
                class="label"
                placeholder=${t("item.label")}
                aria-label=${t("item.label")}
              />
              <input
                type="number"
                step="any"
                min="0"
                name="quantity"
                value="1"
                aria-label=${t("item.quantity")}
              />
              <input name="unit" placeholder=${t("item.unit")} aria-label=${t("item.unit")} />
              <input
                type="number"
                step="any"
                name="unit_price"
                required
                placeholder=${t("item.unit_price")}
                aria-label=${t("item.unit_price")}
              />
              <p class="muted small">${t("item.negative_hint")}</p>
              <div class="row">
                <button class="btn" type="submit">${t("item.add")}</button>
                <button class="btn" type="button" @click=${() => (this.adding = false)}>
                  ${t("item.cancel")}
                </button>
              </div>
            </form>`
          : html`<button class="btn small add-other" @click=${() => (this.adding = true)}>
              ${t("item.add_other")}
            </button>`
      }
    </div>`;
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
      label,
      .label {
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
      .kind > p {
        margin: 6px 0 0;
      }
      .item {
        display: grid;
        grid-template-columns: minmax(120px, 1fr) 140px 96px 96px 52px;
        gap: 6px;
        align-items: start;
        padding: 6px 4px;
      }
      .item + .item {
        border-top: 1px dotted var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .item > * {
        min-width: 0;
      }
      .item.manual {
        box-shadow: inset 3px 0 var(--wattbill-manual);
        padding-left: 10px;
      }
      :host([narrow]) .item {
        grid-template-columns: 1fr 1fr 1fr 52px;
      }
      :host([narrow]) .item .label {
        grid-column: 1 / -1;
      }
      .item .label > div:first-child {
        padding-top: 6px;
      }
      .item input[type="number"] {
        text-align: right;
      }
      .item input.manual {
        border-color: var(--wattbill-manual);
        color: var(--wattbill-manual);
      }
      .quantity {
        display: flex;
        gap: 4px;
        align-items: center;
      }
      .quantity .unit {
        flex: 0 0 44px;
      }
      .actions {
        display: flex;
        gap: 2px;
        align-items: center;
        justify-content: flex-end;
        padding-top: 4px;
      }
      .icon {
        font: inherit;
        border: 0;
        background: none;
        cursor: pointer;
        padding: 2px 4px;
        border-radius: 6px;
        color: var(--secondary-text-color);
      }
      .icon.reset {
        color: var(--wattbill-manual);
        font-weight: 700;
      }
      .add-item {
        margin-top: 8px;
      }
      .add-item form {
        display: grid;
        grid-template-columns: 1fr 72px 72px 110px;
        gap: 6px;
      }
      .add-item form > :is(p, .row) {
        grid-column: 1 / -1;
        margin: 0;
      }
      :host([narrow]) .add-item form {
        grid-template-columns: 1fr 1fr;
      }
      :host([narrow]) .add-item form .label {
        grid-column: 1 / -1;
      }
      .evidence {
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      .segments {
        margin: 2px 0 0;
        padding-left: 16px;
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
