// Refetches the Run whenever its summary changes, so it follows live updates.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  KINDS,
  OUTCOMES,
  addLineItem,
  addTemplateLineItem,
  clearFlag,
  deleteLineItem,
  deleteRuns,
  endRun,
  getRun,
  previewDelete,
  resetLineItem,
  saveAsTemplate,
  updateLineItem,
  updateRun,
  type Device,
  type Totals,
  type LineItem,
  type Material,
  type LineItemTemplate,
  type Outcome,
  type RunDetail,
  type RunSummary,
} from "./api";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { isKey, localize, type Localize } from "./localize";
import "./run-images";
import { deleteDialog, deviceName, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";
import "./tag-input";

/** How a measured length became grams, so the user can check the conversion. */
const lengthEvidence = ({ length, material }: LineItem, t: Localize, format: Format) => {
  if (length === null) return undefined;
  const measured = format.quantity(length, "mm");
  return material?.diameter
    ? t("evidence.length", {
        length: measured,
        diameter: format.quantity(material.diameter, "mm"),
        density: format.quantity(material.density, "g/cm³"),
      })
    : t("evidence.length_only", { length: measured });
};

const evidence = (item: LineItem, t: Localize, format: Format) =>
  [
    item.method && t(`method.${item.method}`),
    item.template_id && t("evidence.template"),
    item.basis === "running_hours" && t("evidence.running_hours"),
    item.segments.length > 1 && t("evidence.segments", { count: item.segments.length }),
    item.measured && (lengthEvidence(item, t, format) ?? t("evidence.measured")),
    item.share !== null && t("evidence.share", { share: format.percent(item.share) }),
  ]
    .filter(Boolean)
    .join(" · ");

/** How far corrected split Line Items are from the printer's measured total, in grams. */
const splitHint = (items: LineItem[], t: Localize, format: Format) => {
  const split = items.filter((item) => item.share !== null);
  if (!split.length) return nothing;
  const sum = (values: (number | null)[]) => values.reduce<number>((a, b) => a + (b ?? 0), 0);
  const measured = sum(split.map((item) => (item.computed ?? item).quantity));
  const total = sum(split.map((item) => item.quantity));
  const difference = total - measured;
  const shown = (grams: number) => format.quantity(grams, "g");
  const off = shown(Math.abs(difference)) !== shown(0);
  return html`<p class="split-hint muted small">
    ${t("split.measured", { measured: shown(measured) })}
    ${
      off
        ? t("split.difference", {
            total: shown(total),
            difference: `${difference > 0 ? "+" : "−"}${shown(Math.abs(difference))}`,
          })
        : nothing
    }
  </p>`;
};

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
  material_id: item.material_id ?? "",
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
    case "material_id":
      return value ? { material_id: value } : undefined;
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
  @property({ attribute: false }) tags: string[] = [];
  /** The Materials catalogue, archived ones included. */
  @property({ attribute: false }) materials: Material[] = [];
  @property({ attribute: false }) templates: LineItemTemplate[] = [];
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private run?: RunDetail;
  @state() private missing = false;
  /** Where the last change that could not be saved was made. */
  @state() private failed?: "fields" | "items";
  /** Set while the delete confirmation is open. */
  @state() private drop?: Totals;
  /** Which form for a new Line Item is open: Material, Other by hand or from a template. */
  @state() private adding?: "material" | "other" | "template";
  /** The template picked in its form; the first one until the user picks. */
  @state() private templateId?: string;
  /** The label of the Line Item last saved as a template. */
  @state() private savedTemplate?: string;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runId")) {
      this.run = undefined;
      this.missing = false;
      this.failed = undefined;
      this.drop = undefined;
      this.adding = this.savedTemplate = undefined;
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
    if (quantity === undefined) return;
    if (this.adding === "material") {
      if (!entered.material_id) return;
      const material = {
        kind: "material" as const,
        material_id: entered.material_id,
        quantity,
        unit: entered.unit,
      };
      if (await this.saveItems(addLineItem(this.hass, this.runId, material)))
        this.adding = undefined;
      return;
    }
    const unitPrice = parseNumber(entered.unit_price ?? "");
    if (unitPrice === undefined || unitPrice === null) return;
    const item = {
      kind: "other" as const,
      label: (entered.label ?? "").trim() || null,
      quantity,
      unit: (entered.unit ?? "").trim(),
      unit_price: unitPrice,
    };
    if (await this.saveItems(addLineItem(this.hass, this.runId, item))) this.adding = undefined;
  }

  /** Materials a Line Item can pick: current ones, plus its own even when archived. */
  private pickable(current: string | null) {
    return this.materials.filter((material) => !material.archived || material.id === current);
  }

  private async onAddTemplate(event: SubmitEvent, template: LineItemTemplate) {
    event.preventDefault();
    const entered = new FormData(event.target as HTMLFormElement).get("quantity");
    const quantity = parseNumber(typeof entered === "string" ? entered : "");
    if (quantity === undefined || (quantity !== null && quantity < 0)) return;
    const added = addTemplateLineItem(this.hass, this.runId, template.id, quantity ?? undefined);
    if (await this.saveItems(added)) this.adding = undefined;
  }

  private async onSaveTemplate(item: LineItem) {
    const t = localize(this.hass);
    const label = item.label ?? t(`kind.${item.kind}`);
    this.failed = this.savedTemplate = undefined;
    try {
      await saveAsTemplate(this.hass, this.runId, item.id, item.label ? undefined : label);
      this.savedTemplate = label;
    } catch {
      this.failed = "items";
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
          ${
            this.savedTemplate
              ? html`<p class="saved small">
                  ${t("item.saved_as_template", { label: this.savedTemplate })}
                </p>`
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
                ${
                  items.length
                    ? items.map((item) => this.renderItem(item, t, format))
                    : html`<p class="muted small">${t("run.none")}</p>`
                }
                ${kind === "other" ? this.renderAdd(run, t, format) : nothing}
                ${kind === "material" ? splitHint(items, t, format) : nothing}
                ${kind === "material" ? this.renderAddMaterial(t) : nothing}
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
      ${
        this.drop
          ? deleteDialog(t("delete.title", { name: runName(run, t) }), this.drop, t, format, {
              cancel: () => (this.drop = undefined),
              confirm: () => void this.delete(),
            })
          : nothing
      }
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

  private renderItem(item: LineItem, t: Localize, format: Format) {
    const why = evidence(item, t, format);
    const shown = itemValues(item, format);
    const { computed, locked } = item;
    // Labels and units WattBill sets stay as they are, rendered in the output language;
    // a Material Line Item is named by its Material and counts g or ml.
    const entered = item.kind === "other";
    // Running hours are hours, whatever the template called them.
    const unitEntered = entered && item.basis !== "running_hours";
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
          item.kind === "material"
            ? this.renderMaterialPicker(item, t)
            : entered
              ? html`<input name="label" aria-label=${t("item.label")} .value=${shown.label} />`
              : html`<div>${item.label ?? t(`kind.${item.kind}`)}</div>`
        }
        ${why ? html`<div class="evidence">${why}</div>` : nothing}
        ${item.slots.map(
          (slot) =>
            html`<div class="evidence slot">
              ${t("evidence.slot", { number: slot.number, type: slot.type })}
              ${
                slot.colour
                  ? html`<span class="swatch" style="background: ${slot.colour}"></span
                      >${slot.colour}`
                  : nothing
              }
            </div>`,
        )}
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
          unitEntered
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
        <button
          class="icon save-template"
          title=${t("item.save_as_template")}
          @click=${() => this.onSaveTemplate(item)}
        >
          ☆
        </button>
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

  private renderMaterialPicker(item: LineItem, t: Localize) {
    const options = this.pickable(item.material_id);
    // The catalogue may still be loading; the Line Item's copy names its Material meanwhile.
    const own = item.material_id !== null && !options.some(({ id }) => id === item.material_id);
    return html`<select
      name="material_id"
      aria-label=${t("item.material")}
      ?disabled=${item.locked}
    >
      ${
        item.material_id === null
          ? html`<option value="" selected>${t("item.no_material")}</option>`
          : nothing
      }
      ${
        own
          ? html`<option value=${item.material_id} selected>${item.material?.name}</option>`
          : nothing
      }
      ${options.map(
        (material) =>
          html`<option value=${material.id} ?selected=${material.id === item.material_id}>
            ${material.archived ? t("materials.archived_name", { name: material.name }) : material.name}
          </option>`,
      )}
    </select>`;
  }

  private renderAddMaterial(t: Localize) {
    return html`<div class="add-item">
      ${
        this.adding === "material"
          ? html`<form class="material" @submit=${this.onAdd}>
              <select name="material_id" class="label" required aria-label=${t("item.material")}>
                ${this.pickable(null).map(
                  (material) => html`<option value=${material.id}>${material.name}</option>`,
                )}
              </select>
              <input
                type="number"
                step="any"
                min="0"
                name="quantity"
                required
                aria-label=${t("item.quantity")}
              />
              <select name="unit" aria-label=${t("item.unit")}>
                <option value="g">g</option>
                <option value="ml">ml</option>
              </select>
              <div class="row">
                <button class="btn" type="submit">${t("item.add")}</button>
                <button class="btn" type="button" @click=${() => (this.adding = undefined)}>
                  ${t("item.cancel")}
                </button>
              </div>
            </form>`
          : html`<button class="btn small add-material" @click=${() => (this.adding = "material")}>
              ${t("item.add_material")}
            </button>`
      }
    </div>`;
  }

  private renderAdd(run: RunDetail, t: Localize, format: Format) {
    if (this.adding === "template") return this.renderAddTemplate(run, t, format);
    return html`<div class="add-item">
      ${
        this.adding === "other"
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
                <button class="btn" type="button" @click=${() => (this.adding = undefined)}>
                  ${t("item.cancel")}
                </button>
              </div>
            </form>`
          : html`<div class="row">
              <button class="btn small add-other" @click=${() => (this.adding = "other")}>
                ${t("item.add_other")}
              </button>
              ${
                this.templates.length
                  ? html`<button
                      class="btn small add-template"
                      @click=${() => (this.adding = "template")}
                    >
                      ${t("item.add_template")}
                    </button>`
                  : nothing
              }
            </div>`
      }
    </div>`;
  }

  private renderAddTemplate(run: RunDetail, t: Localize, format: Format) {
    const template =
      this.templates.find((candidate) => candidate.id === this.templateId) ?? this.templates[0];
    if (!template) return nothing;
    return html`<div class="add-item">
      <form class="template" @submit=${(event: SubmitEvent) => this.onAddTemplate(event, template)}>
        <select
          name="template"
          class="label"
          aria-label=${t("item.template")}
          @change=${(event: Event) => (this.templateId = (event.target as HTMLSelectElement).value)}
        >
          ${this.templates.map(
            (option) =>
              html`<option value=${option.id} ?selected=${option.id === template.id}>
                ${`${option.label} · ${format.unitPrice(option.unit_price)}${option.unit ? `/${option.unit}` : ""}`}
              </option>`,
          )}
        </select>
        ${
          template.basis === "running_hours"
            ? html`<p class="muted small">
                ${t("item.running_hours_hint", {
                  hours: format.quantity(run.running_seconds / 3600, "h"),
                })}
              </p>`
            : html`<input
                type="number"
                step="any"
                min="0"
                name="quantity"
                placeholder=${t("item.default_quantity", {
                  quantity: format.toNumberInput(template.default_quantity, 4),
                })}
                aria-label=${t("item.quantity")}
              />`
        }
        <div class="row">
          <button class="btn" type="submit">${t("item.add")}</button>
          <button class="btn" type="button" @click=${() => (this.adding = undefined)}>
            ${t("item.cancel")}
          </button>
        </div>
      </form>
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
        grid-template-columns: minmax(120px, 1fr) 140px 96px 96px 76px;
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
        grid-template-columns: 1fr 1fr 1fr 76px;
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
      .add-item form.material {
        grid-template-columns: 1fr 96px 72px;
      }
      .add-item form > :is(p, .row) {
        grid-column: 1 / -1;
        margin: 0;
      }
      .add-item form.template {
        grid-template-columns: 1fr 140px;
      }
      :host([narrow]) .add-item form {
        grid-template-columns: 1fr 1fr;
      }
      .saved {
        color: var(--success-color, #43a047);
        margin: 0;
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
      .slot {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .swatch {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        flex: none;
      }
      .split-hint {
        margin: 6px 0 0;
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-page": RunPage;
  }
}
