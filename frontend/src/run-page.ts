// The Run page: the Run's facts and its Line Items by kind, read like a receipt. Both are
// corrected in dialogs. Refetches the Run whenever its summary changes, so it follows
// live updates.
import {
  mdiBookmarkPlusOutline,
  mdiDelete,
  mdiLockOutline,
  mdiPencil,
  mdiPlus,
  mdiRestore,
  mdiStopCircleOutline,
} from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
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
  shownKinds,
  updateLineItem,
  updateRun,
  type Device,
  type Kind,
  type Totals,
  type LineItem,
  type Material,
  type LineItemTemplate,
  type Outcome,
  type RunDetail,
  type RunSummary,
} from "./api";
import { confirmDialog, formDialog } from "./dialog";
import { field, input, numberInput, select, textarea, withUnit } from "./fields";
import { formatter, priceUnit, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import "./run-images";
import { deleteDialog, deviceName, flagLabel, outcomeChip, runName } from "./run-parts";
import { shared } from "./styles";
import { tagChip } from "./tag-input";

/** How a measured length became grams, so the user can check the conversion. */
const lengthEvidence = ({ length, material }: LineItem, t: Localize, format: Format) => {
  if (length === null) return undefined;
  const measured = format.quantity(length, "mm");
  return material?.diameter && material.density
    ? t("evidence.length", {
        length: measured,
        diameter: format.quantity(material.diameter, "mm"),
        density: format.quantity(material.density, "g/cm³"),
      })
    : t("evidence.length_only", { length: measured });
};

const evidence = (item: LineItem, t: Localize, format: Format) =>
  [
    item.method &&
      t(
        item.kind === "water" && item.method === "measured"
          ? "method.water_measured"
          : `method.${item.method}`,
      ),
    item.dose_source && t(`dose_source.${item.dose_source}`),
    item.template_id && t("evidence.template"),
    item.basis === "running_hours" && t("evidence.running_hours"),
    item.segments.length > 1 && t("evidence.segments", { count: item.segments.length }),
    item.measured && (lengthEvidence(item, t, format) ?? t("evidence.measured")),
    item.share !== null && t("evidence.share", { share: format.percent(item.share) }),
  ]
    .filter(Boolean)
    .join(" · ");

/** When an open Run is expected to end and what its Projected Total includes. */
function projection(run: RunDetail, t: Localize, format: Format) {
  const parts = format.list(run.projected_parts.map((part) => t(`projected_part.${part}`)));
  return [
    ...(run.projected_end
      ? [t("run.projected_end", { end: format.dateTime(run.projected_end) })]
      : []),
    t("run.projected_parts", { parts }),
  ].join(" · ");
}

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

/** What each field shows, as its input's value. */
const fieldValues = (run: RunDetail, format: Format) => ({
  name: run.name ?? "",
  note: run.note ?? "",
  started: format.toInput(run.started),
  ended: run.ended ? format.toInput(run.ended) : "",
  outcome: run.outcome ?? "",
  part_count: String(run.part_count ?? ""),
  program: run.program ?? "",
});

type Field = keyof ReturnType<typeof fieldValues>;

/** The correction a field's new value asks for; undefined if it is no valid value. */
const correction = (field: Field, value: string, format: Format) => {
  switch (field) {
    case "name":
    case "note":
    case "program":
      return { [field]: value.trim() || null };
    case "started":
    case "ended": {
      const iso = format.fromInput(value);
      return iso ? { [field]: iso } : undefined;
    }
    case "outcome":
      return { outcome: value as Outcome };
    case "part_count":
      return /^\d+$/.test(value) && Number(value) >= 1 ? { part_count: Number(value) } : undefined;
  }
};

/** The Run's fields and Tags as its dialog edits them. */
const runDraft = (run: RunDetail, format: Format) => ({
  ...fieldValues(run, format),
  tags: run.tags,
});

/** What the edited fields change, and which of them hold no valid value. */
const runChanges = (run: RunDetail, draft: ReturnType<typeof runDraft>, format: Format) => {
  const shown = fieldValues(run, format);
  const corrections = (Object.keys(shown) as Field[])
    .filter((name) => draft[name] !== shown[name])
    .map((name) => [name, correction(name, draft[name], format)] as const);
  const changes: Parameters<typeof updateRun>[2] = Object.assign(
    JSON.stringify(draft.tags) === JSON.stringify(run.tags) ? {} : { tags: draft.tags },
    ...corrections.map(([, change]) => change),
  );
  return { changes, invalid: corrections.filter(([, change]) => !change).map(([name]) => name) };
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
  unit_price: format.toNumberInput(item.unit_price * priceUnit(item.unit).factor, 4),
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

/** A Line Item's fields as its dialog edits them. Of unit price and amount the one
 * typed last (`entered`) stands and the other follows, as the backend computes it. */
const itemDraft = (item: LineItem, format: Format) => ({
  id: item.id,
  ...itemValues(item, format),
  entered: undefined as "unit_price" | "amount" | undefined,
});

/** The unit price and amount fields while editing: the one not typed follows the other. */
const followed = (item: LineItem, draft: ReturnType<typeof itemDraft>, format: Format) => {
  const shown = itemValues(item, format);
  const { factor } = priceUnit(item.unit);
  const quantity = parseNumber(draft.quantity) ?? 0;
  if (draft.entered === "amount") {
    const amount = parseNumber(draft.amount);
    return {
      amount: draft.amount,
      unit_price:
        quantity && typeof amount === "number"
          ? format.toNumberInput((amount / quantity) * factor, 4)
          : shown.unit_price,
    };
  }
  const price = parseNumber(draft.unit_price);
  const changed = draft.quantity !== shown.quantity || draft.unit_price !== shown.unit_price;
  return {
    unit_price: draft.unit_price,
    amount:
      changed && typeof price === "number"
        ? format.toAmountInput((quantity * price) / factor)
        : shown.amount,
  };
};

/** What the edited fields change, and which of them hold no valid value. */
const itemChanges = (item: LineItem, draft: ReturnType<typeof itemDraft>, format: Format) => {
  const shown = itemValues(item, format);
  const edited = (["label", "material_id", "unit", "quantity", draft.entered] as const)
    .filter((name) => name !== undefined)
    .filter((name) => draft[name] !== shown[name])
    .map((name) => [name, itemChange(name, draft[name])] as const);
  const changes: Parameters<typeof updateLineItem>[3] = Object.assign(
    {},
    ...edited.map(([, change]) => change),
  );
  if (changes.unit_price !== undefined) changes.unit_price /= priceUnit(item.unit).factor;
  return { changes, invalid: edited.filter(([, change]) => !change).map(([name]) => name) };
};

/** The unit a consumed kind's Line Item counts in when added by hand. */
const CONSUMED_UNITS = { electricity: "kWh", water: "L" } as const;

/** A new Line Item as its dialog fills it in; what applies depends on the `kind`. */
const newItem = (kind: Kind | "template") => ({
  kind,
  label: "",
  material_id: "",
  template_id: "",
  unit: "",
  quantity: kind === "other" ? "1" : "",
  unit_price: "",
});

const VALUES = ["quantity", "unit_price", "amount"] as const;

/** A price per `unit`, per the unit it is shown in when that is another. */
const priced = (price: number, unit: string, format: Format) => {
  const shown = priceUnit(unit);
  const per = shown.unit === unit ? "" : `/${shown.unit}`;
  return `${format.unitPrice(price * shown.factor)}${per}`;
};

/** A Line Item value as the user reads it, e.g. "0.15 kWh" or "€0.30". */
const shownValue = (
  item: LineItem,
  values: NonNullable<LineItem["computed"]>,
  field: (typeof VALUES)[number],
  format: Format,
) => {
  if (field === "amount") return format.money(values.amount);
  if (field === "unit_price") return priced(values.unit_price, item.unit, format);
  return values.quantity === null ? "—" : format.quantity(values.quantity, item.unit);
};

@customElement("coinop-run-page")
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
  /** The Runs tab as the user left it. */
  @property({ attribute: false }) runsPath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private run?: RunDetail;
  @state() private missing = false;
  /** Where the last action that failed was taken. */
  @state() private failed?: "facts" | "items";
  /** Set while the delete confirmation is open. */
  @state() private drop?: Totals;
  /** The Line Item whose delete confirmation is open. */
  @state() private deleting?: string;
  /** Set while the Run's dialog is open. */
  @state() private editing?: ReturnType<typeof runDraft>;
  /** Set while a Line Item's dialog is open. */
  @state() private editingItem?: ReturnType<typeof itemDraft>;
  /** Set while the dialog for a new Line Item is open. */
  @state() private adding?: ReturnType<typeof newItem>;
  /** The open dialog tried to save: it marks what holds no valid value from then on. */
  @state() private checked = false;
  @state() private saving = false;
  /** The backend refused what the open dialog saved. */
  @state() private refused = false;
  /** The label of the Line Item last saved as a template. */
  @state() private savedTemplate?: string;
  private request = 0;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("runId")) {
      this.run = undefined;
      this.missing = false;
      this.failed = undefined;
      this.drop = undefined;
      this.savedTemplate = undefined;
      this.closeDialog();
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

  /** Show the Run as a one-click action returned it. */
  private async act(result: Promise<RunDetail>, where: "facts" | "items" = "items") {
    this.failed = undefined;
    try {
      ++this.request;
      this.run = await result;
    } catch {
      this.failed = where;
    }
  }

  /** Show the Run as the open dialog's command returned it and close the dialog; a
   * refused one stays open. */
  private async submit(result: Promise<RunDetail>) {
    this.saving = true;
    this.refused = false;
    try {
      ++this.request;
      this.run = await result;
      this.closeDialog();
    } catch {
      this.refused = true;
    } finally {
      this.saving = false;
    }
  }

  private closeDialog() {
    this.editing = this.editingItem = this.adding = this.deleting = undefined;
    this.checked = this.refused = false;
  }

  private saveRun(run: RunDetail, draft: ReturnType<typeof runDraft>) {
    const { changes, invalid } = runChanges(run, draft, formatter(this.hass));
    this.checked = true;
    if (invalid.length) return;
    if (!Object.keys(changes).length) return this.closeDialog();
    void this.submit(updateRun(this.hass, this.runId, changes));
  }

  private saveItem(item: LineItem, draft: ReturnType<typeof itemDraft>) {
    const { changes, invalid } = itemChanges(item, draft, formatter(this.hass));
    this.checked = true;
    if (invalid.length) return;
    if (!Object.keys(changes).length) return this.closeDialog();
    void this.submit(updateLineItem(this.hass, this.runId, item.id, changes));
  }

  /** The new Line Item's command, or the fields that hold no valid value. */
  private added(adding: ReturnType<typeof newItem>) {
    const quantity = parseNumber(adding.quantity);
    const price = parseNumber(adding.unit_price);
    const amount = typeof quantity === "number" && quantity >= 0;
    const add = (item: Parameters<typeof addLineItem>[2]) => ({
      command: () => addLineItem(this.hass, this.runId, item),
    });
    if (adding.kind === "template") {
      const template = this.template(adding);
      return template && (quantity === null || amount)
        ? {
            command: () =>
              addTemplateLineItem(this.hass, this.runId, template.id, quantity ?? undefined),
          }
        : { invalid: ["quantity"] };
    }
    if (adding.kind === "material") {
      const { picked, unit } = this.materialOf(adding);
      return picked && amount
        ? add({ kind: "material", material_id: picked.id, quantity, unit: adding.unit || unit })
        : { invalid: ["quantity"] };
    }
    const { kind } = adding;
    const priced = typeof price === "number";
    const { valid, item } =
      kind === "other"
        ? {
            valid: { quantity: quantity === null || amount, unit_price: priced },
            item: (unit_price: number) => ({
              kind,
              label: adding.label.trim() || null,
              quantity,
              unit: adding.unit.trim(),
              unit_price,
            }),
          }
        : {
            valid: { quantity: amount, unit_price: priced && price >= 0 },
            item: (unit_price: number) => ({
              kind,
              quantity,
              unit_price: unit_price / priceUnit(CONSUMED_UNITS[kind]).factor,
            }),
          };
    const invalid = Object.entries(valid).flatMap(([name, ok]) => (ok ? [] : [name]));
    return invalid.length || typeof price !== "number" ? { invalid } : add(item(price));
  }

  private saveNew(adding: ReturnType<typeof newItem>) {
    const added = this.added(adding);
    this.checked = true;
    if (added.command) void this.submit(added.command());
  }

  /** Materials a Line Item can pick: current ones, plus its own even when archived. */
  private pickable(current: string | null) {
    return this.materials.filter((material) => !material.archived || material.id === current);
  }

  /** The Material a new Line Item is of, the first one until the user picks, and the
   * units it can count in, led by its usual one. */
  private materialOf({ material_id }: ReturnType<typeof newItem>) {
    const materials = this.pickable(null);
    const picked = materials.find(({ id }) => id === material_id) ?? materials[0];
    const byVolume =
      picked?.form === "resin" ||
      (picked?.price.source === "fixed" && picked.price.pack_unit === "ml");
    const units = picked && picked.price_per_piece !== null ? ["pcs"] : ["g", "ml"];
    return {
      materials,
      picked,
      units,
      unit: units.length === 1 ? units[0] : byVolume ? "ml" : "g",
    };
  }

  /** The template a new Line Item copies, the first one until the user picks. */
  private template({ template_id }: ReturnType<typeof newItem>) {
    return this.templates.find(({ id }) => id === template_id) ?? this.templates[0];
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

  private onImagesChanged(event: CustomEvent<RunDetail>) {
    ++this.request;
    this.run = event.detail;
  }

  private async confirmDelete() {
    this.failed = undefined;
    try {
      this.drop = await previewDelete(this.hass, [this.runId]);
    } catch {
      this.failed = "facts";
    }
  }

  private async delete() {
    try {
      await deleteRuns(this.hass, [this.runId]);
      navigate(this.runsPath);
    } catch {
      this.failed = "facts";
    }
    this.drop = undefined;
  }

  override render() {
    const t = localize(this.hass);
    if (this.missing) {
      return html`<p>${t("run.not_found")}</p>
        <a href=${this.runsPath} @click=${followLink}>${t("run.back")}</a>`;
    }
    if (!this.run) return html`<p class="muted">${t("run.loading")}</p>`;
    const run = this.run;
    const format = formatter(this.hass);
    const device = deviceName(run, this.devices, t);
    const devices = this.devices?.filter(({ id }) => id === run.device_id);
    const water = devices?.some(({ capabilities }) => capabilities.includes("water"));
    const electricity = run.line_items.some(({ kind }) => kind === "electricity");
    const kinds = shownKinds(devices, run.line_items).filter(
      (kind) => kind !== "electricity" || electricity,
    );
    const add = (kind: Parameters<typeof newItem>[0], label: string) =>
      html`<ha-button
        class="small add-${kind}"
        appearance="filled"
        @click=${() => (this.adding = newItem(kind))}
      >
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${label}
      </ha-button>`;
    return html`
      <div class="runbar row">
        ${outcomeChip(run, t)}
        <span class="muted">${device} · ${format.dateTime(run.started)}</span>
        <span class="spacer"></span>
        ${
          run.ended === null
            ? html`<ha-button
                class="end-run"
                appearance="plain"
                @click=${() => this.act(endRun(this.hass, this.runId), "facts")}
              >
                <ha-svg-icon slot="start" .path=${mdiStopCircleOutline}></ha-svg-icon>
                ${t("run.end_now")}
              </ha-button>`
            : nothing
        }
        <ha-button
          class="delete-run"
          appearance="plain"
          variant="danger"
          ?disabled=${!run.finalised}
          @click=${this.confirmDelete}
        >
          <ha-svg-icon slot="start" .path=${mdiDelete}></ha-svg-icon>
          ${t("run.delete")}
        </ha-button>
      </div>
      <div class="grid">
        <div class="card facts">
          <coinop-run-images
            .hass=${this.hass}
            .run=${run}
            @run-changed=${this.onImagesChanged}
          ></coinop-run-images>
          ${this.renderFacts(run, device, t, format)}
        </div>
        <div class="items">
          ${
            run.flags.length
              ? html`<div class="flags">
                  ${run.flags.map(
                    (flag) =>
                      html`<div class="flag">
                        <span>⚑</span><span class="text">${flagLabel(flag, t)}</span>
                        <ha-button
                          class="small"
                          appearance="plain"
                          @click=${() => this.act(clearFlag(this.hass, this.runId, flag), "facts")}
                        >
                          ${t("run.mark_checked")}
                        </ha-button>
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
          ${
            electricity
              ? nothing
              : html`<div class="row">${add("electricity", t("item.add_electricity"))}</div>`
          }
          ${kinds.map((kind) => {
            const items = run.line_items.filter((item) => item.kind === kind);
            const adds = [
              ...(kind === "water" && water && !items.length
                ? [add("water", t("item.add_water"))]
                : []),
              ...(kind === "material" ? [add("material", t("item.add_material"))] : []),
              ...(kind === "other" ? [add("other", t("item.add_other"))] : []),
              ...(kind === "other" && this.templates.length
                ? [add("template", t("item.add_template"))]
                : []),
            ];
            return html`
              <div class="card kind" style="--kind-color: var(--coinop-${kind})">
                <div class="row between">
                  <h3>${t(`kind.${kind}`)}</h3>
                  <b class="num">${format.money(run.subtotals[kind])}</b>
                </div>
                ${
                  items.length
                    ? html`<div class="item-head muted small" aria-hidden="true">
                          <span></span><span>${t("item.quantity")}</span
                          ><span>${t("item.unit_price")}</span><span>${t("item.amount")}</span
                          ><span></span>
                        </div>
                        ${items.map((item) => this.renderItem(item, t, format))}`
                    : html`<p class="muted small">${t("run.none")}</p>`
                }
                ${kind === "material" ? splitHint(items, t, format) : nothing}
                ${adds.length ? html`<div class="add-item row">${adds}</div>` : nothing}
              </div>
            `;
          })}
          <div class="card totals">
            <span class="big">${t("run.total")}</span
            ><span class="big num">${format.money(run.total)}</span>
            ${
              run.projected_total === null
                ? nothing
                : html`<span class="projected"
                      ><span class="muted">${t("run.projected_total")}</span
                      ><span class="muted num"
                        >${t("run.projected", { amount: format.money(run.projected_total) })}</span
                      ></span
                    ><span class="muted small projection">${projection(run, t, format)}</span>`
            }
            ${
              run.part_count === null || run.cost_per_part === null
                ? nothing
                : html`<span class="muted"
                      >${t("run.cost_per_part", { count: run.part_count })}</span
                    ><span class="muted num">${format.money(run.cost_per_part)}</span>`
            }
          </div>
        </div>
      </div>
      ${this.renderDialog(run, t, format)}
    `;
  }

  /** A removed Device's Run shows the Program it has. */
  private hasProgram(run: RunDetail) {
    const device = this.devices?.find((d) => d.id === run.device_id);
    return device ? device.capabilities.includes("program") : run.program !== null;
  }

  private renderFacts(run: RunDetail, device: string, t: Localize, format: Format) {
    const none = html`<span class="muted">${t("run.none")}</span>`;
    return html`<div class="head">
        <h3 class="ellipsis">${runName(run, t)}</h3>
        <ha-icon-button
          class="edit"
          .label=${t("run.edit")}
          .path=${mdiPencil}
          @click=${() => {
            this.failed = undefined;
            this.editing = runDraft(run, format);
          }}
        ></ha-icon-button>
      </div>
      <dl>
        <dt>${t("run.device")}</dt>
        <dd>${device}</dd>
        ${
          this.hasProgram(run)
            ? html`<dt>${t("run.program")}</dt>
                <dd class="program">${run.program ?? none}</dd>`
            : nothing
        }
        <dt>${t("run.started")}</dt>
        <dd>${format.dateTime(run.started)}</dd>
        <dt>${t("run.ended")}</dt>
        <dd class="ended">${run.ended ? format.dateTime(run.ended) : "—"}</dd>
        <dt>${t("run.running_time")}</dt>
        <dd>${format.duration(run.running_seconds)}</dd>
        ${
          run.part_count === null
            ? nothing
            : html`<dt>${t("run.part_count")}</dt>
                <dd class="part-count">${run.part_count}</dd>`
        }
        <dt>${t("run.tags")}</dt>
        <dd class="tags row">${run.tags.length ? run.tags.map(tagChip) : none}</dd>
        ${
          run.note
            ? html`<dt>${t("run.note")}</dt>
                <dd class="note">${run.note}</dd>`
            : nothing
        }
      </dl>
      ${this.failed === "facts" ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}`;
  }

  /** A Material Line Item by its Material's current name; the Line Item's copy names it
   * while the catalogue loads or once the Material is gone. */
  private materialName(item: LineItem, t: Localize) {
    const material = this.materials.find(({ id }) => id === item.material_id);
    if (!material) return item.material?.name ?? t("item.no_material");
    return material.archived
      ? t("materials.archived_name", { name: material.name })
      : material.name;
  }

  private itemName(item: LineItem, t: Localize) {
    return item.kind === "material" ? this.materialName(item, t) : item.label;
  }

  private renderItem(item: LineItem, t: Localize, format: Format) {
    const why = evidence(item, t, format);
    const { computed, locked } = item;
    const name = this.itemName(item, t);
    const value = (field: (typeof VALUES)[number]) => {
      const manual = computed !== null && computed[field] !== item[field];
      return html`<div
        class="num ${field} ${manual ? "manual" : ""}"
        title=${manual ? t("item.computed", { value: shownValue(item, computed, field, format) }) : ""}
      >
        ${shownValue(item, item, field, format)}
      </div>`;
    };
    return html`<div
      class="item ${computed ? "manual" : ""} ${locked ? "locked" : ""}"
      data-id=${item.id}
    >
      <div class="label">
        ${name ? html`<div class="name">${name}</div>` : nothing}
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
                      ${format.quantity(segment.kwh, item.unit)} ×
                      ${priced(segment.unit_price, item.unit, format)}
                    </li>`,
                )}
              </ul>`
            : nothing
        }
      </div>
      ${VALUES.map(value)}
      <div class="actions">
        ${
          locked
            ? html`<ha-svg-icon
                class="lock"
                title=${t("item.locked")}
                .path=${mdiLockOutline}
              ></ha-svg-icon>`
            : html`<ha-icon-button
                class="edit"
                .label=${t("item.edit")}
                .path=${mdiPencil}
                @click=${() => {
                  this.failed = undefined;
                  this.editingItem = itemDraft(item, format);
                }}
              ></ha-icon-button>`
        }
        ${
          computed
            ? html`<ha-icon-button
                class="reset"
                .label=${t(
                  "item.reset",
                  Object.fromEntries(
                    VALUES.map((field) => [field, shownValue(item, computed, field, format)]),
                  ),
                )}
                .path=${mdiRestore}
                @click=${() => this.act(resetLineItem(this.hass, this.runId, item.id))}
              ></ha-icon-button>`
            : nothing
        }
        <ha-icon-button
          class="save-template"
          .label=${t("item.save_as_template")}
          .path=${mdiBookmarkPlusOutline}
          @click=${() => this.onSaveTemplate(item)}
        ></ha-icon-button>
        ${
          item.deletable
            ? html`<ha-icon-button
                class="delete"
                .label=${t("item.delete")}
                .path=${mdiDelete}
                @click=${() => (this.deleting = item.id)}
              ></ha-icon-button>`
            : nothing
        }
      </div>
    </div>`;
  }

  /** What a unit price counts in, e.g. "€/kWh"; the currency alone without a unit. */
  private per(unit: string, format: Format) {
    const shown = priceUnit(unit).unit;
    return shown ? `${format.currencySymbol}/${shown}` : format.currencySymbol;
  }

  private renderDialog(run: RunDetail, t: Localize, format: Format) {
    const dialog = { t, busy: this.saving, onCancel: () => this.closeDialog() };
    const error = this.refused && t("run.save_failed");
    if (this.editing) return this.renderRunDialog(run, this.editing, { ...dialog, error }, format);
    const item = run.line_items.find(({ id }) => id === this.editingItem?.id);
    if (this.editingItem && item)
      return this.renderItemDialog(item, this.editingItem, { ...dialog, error }, format);
    if (this.adding) return this.renderNewDialog(run, this.adding, { ...dialog, error }, format);
    const deleting = run.line_items.find(({ id }) => id === this.deleting);
    if (deleting)
      return confirmDialog({
        t,
        title: t("delete.title", {
          name: this.itemName(deleting, t) ?? t(`kind.${deleting.kind}`),
        }),
        name: "delete-item-dialog",
        content: html`<p>${t("item.delete_warning")}</p>`,
        onCancel: () => this.closeDialog(),
        onConfirm: () => {
          this.closeDialog();
          void this.act(deleteLineItem(this.hass, this.runId, deleting.id));
        },
      });
    if (this.drop)
      return deleteDialog(t("delete.title", { name: runName(run, t) }), this.drop, t, format, {
        cancel: () => (this.drop = undefined),
        confirm: () => void this.delete(),
      });
    return nothing;
  }

  private renderRunDialog(
    run: RunDetail,
    draft: ReturnType<typeof runDraft>,
    dialog: Pick<Parameters<typeof formDialog>[0], "t" | "busy" | "error" | "onCancel">,
    format: Format,
  ) {
    const { t } = dialog;
    const set = (changes: Partial<typeof draft>) => (this.editing = { ...draft, ...changes });
    const locked = !run.finalised;
    const wrong = new Set(this.checked ? runChanges(run, draft, format).invalid : []);
    return formDialog({
      ...dialog,
      title: t("run.edit"),
      name: "run-dialog",
      onSubmit: () => this.saveRun(run, draft),
      content: html`${field(
          t("run.name"),
          input({
            name: "name",
            autofocus: true,
            value: draft.name,
            placeholder: run.job_name ?? t("run.untitled"),
            onInput: (name) => set({ name }),
          }),
        )}
        ${
          this.hasProgram(run)
            ? field(
                t("run.program"),
                input({
                  name: "program",
                  value: draft.program,
                  onInput: (program) => set({ program }),
                }),
                { name: "program", hint: t("run.program_hint") },
              )
            : nothing
        }
        <div class="field-row">
          ${field(
            t("run.started"),
            input({
              type: "datetime-local",
              name: "started",
              value: draft.started,
              disabled: locked,
              invalid: wrong.has("started"),
              onInput: (started) => set({ started }),
            }),
          )}
          ${field(
            t("run.ended"),
            input({
              type: "datetime-local",
              name: "ended",
              value: draft.ended,
              disabled: locked,
              invalid: wrong.has("ended"),
              onInput: (ended) => set({ ended }),
            }),
          )}
        </div>
        <p class="muted small times-hint">${t(locked ? "run.locked_hint" : "run.times_hint")}</p>
        <div class="field-row">
          ${field(
            t("run.outcome"),
            select({
              name: "outcome",
              value: draft.outcome,
              disabled: locked,
              options: [
                ...(run.outcome === null ? [["", "—"] as const] : []),
                ...OUTCOMES.map((outcome) => [outcome, t(`outcome.${outcome}`)] as const),
              ],
              onChange: (outcome) => set({ outcome: outcome as Outcome }),
            }),
          )}
          ${
            run.part_count === null
              ? nothing
              : field(
                  t("run.part_count"),
                  input({
                    type: "number",
                    name: "part_count",
                    min: "1",
                    step: "1",
                    value: draft.part_count,
                    invalid: wrong.has("part_count"),
                    onInput: (part_count) => set({ part_count }),
                  }),
                )
          }
        </div>
        ${field(
          t("run.note"),
          textarea({ name: "note", value: draft.note, onInput: (note) => set({ note }) }),
        )}
        ${field(
          t("run.tags"),
          html`<coinop-tag-input
            .hass=${this.hass}
            .tags=${draft.tags}
            .catalog=${this.tags}
            .label=${t("run.tags")}
            @tags-change=${(event: CustomEvent<string[]>) => set({ tags: event.detail })}
          ></coinop-tag-input>`,
          { group: true },
        )}`,
    });
  }

  private renderItemDialog(
    item: LineItem,
    draft: ReturnType<typeof itemDraft>,
    dialog: Pick<Parameters<typeof formDialog>[0], "t" | "busy" | "error" | "onCancel">,
    format: Format,
  ) {
    const { t } = dialog;
    const set = (changes: Partial<typeof draft>) => (this.editingItem = { ...draft, ...changes });
    const wrong = new Set<string>(this.checked ? itemChanges(item, draft, format).invalid : []);
    // Labels and units Coin-op sets stay as they are, rendered in the output language;
    // a Material Line Item is named by its Material and counts g or ml.
    const entered = item.kind === "other";
    // Running hours are hours, whatever the template called them.
    const unitEntered = entered && item.basis !== "running_hours";
    const shown = followed(item, draft, format);
    const materials = this.pickable(item.material_id);
    const quantity = numberInput({
      name: "quantity",
      value: draft.quantity,
      invalid: wrong.has("quantity"),
      autofocus: !entered,
      onInput: (typed) => set({ quantity: typed }),
    });
    const price = (name: "unit_price" | "amount") =>
      numberInput({
        name,
        min: entered ? undefined : "0",
        value: shown[name],
        invalid: wrong.has(name),
        onInput: (typed) => set({ [name]: typed, entered: name }),
      });
    return formDialog({
      ...dialog,
      title: t("item.edit"),
      name: "item-dialog",
      onSubmit: () => this.saveItem(item, draft),
      content: html`${
          item.kind === "material"
            ? field(
                t("item.material"),
                select({
                  name: "material_id",
                  value: draft.material_id,
                  options: [
                    ...(item.material_id === null ? [["", t("item.no_material")] as const] : []),
                    // The catalogue may still be loading; the Line Item's copy names its Material meanwhile.
                    ...(item.material_id === null ||
                    materials.some(({ id }) => id === item.material_id)
                      ? []
                      : [[item.material_id, item.material?.name] as const]),
                    ...materials.map(
                      ({ id, name, archived }) =>
                        [id, archived ? t("materials.archived_name", { name }) : name] as const,
                    ),
                  ],
                  onChange: (material_id) => set({ material_id }),
                }),
              )
            : nothing
        }
        ${
          entered
            ? field(
                t("item.label"),
                input({
                  name: "label",
                  autofocus: true,
                  value: draft.label,
                  onInput: (label) => set({ label }),
                }),
              )
            : nothing
        }
        <div class="field-row">
          ${field(t("item.quantity"), unitEntered ? quantity : withUnit(quantity, item.unit))}
          ${
            unitEntered
              ? field(
                  t("item.unit"),
                  input({ name: "unit", value: draft.unit, onInput: (unit) => set({ unit }) }),
                )
              : nothing
          }
        </div>
        <div class="field-row">
          ${field(t("item.unit_price"), withUnit(price("unit_price"), this.per(item.unit, format)))}
          ${field(t("item.amount"), withUnit(price("amount"), format.currencySymbol))}
        </div>
        ${entered ? html`<p class="muted small">${t("item.negative_hint")}</p>` : nothing}`,
    });
  }

  private renderNewDialog(
    run: RunDetail,
    adding: ReturnType<typeof newItem>,
    dialog: Pick<Parameters<typeof formDialog>[0], "t" | "busy" | "error" | "onCancel">,
    format: Format,
  ) {
    const { t } = dialog;
    const set = (changes: Partial<typeof adding>) => (this.adding = { ...adding, ...changes });
    const added = this.added(adding);
    const wrong = new Set(this.checked ? added.invalid : []);
    const quantity = (options: Parameters<typeof numberInput>[0] = {}) =>
      numberInput({
        name: "quantity",
        value: adding.quantity,
        invalid: wrong.has("quantity"),
        onInput: (typed) => set({ quantity: typed }),
        ...options,
      });
    const price = (unit: string, options: Parameters<typeof numberInput>[0] = {}) =>
      field(
        t("item.unit_price"),
        withUnit(
          numberInput({
            name: "unit_price",
            value: adding.unit_price,
            invalid: wrong.has("unit_price"),
            onInput: (unit_price) => set({ unit_price }),
            ...options,
          }),
          unit,
        ),
      );
    const { materials, picked, units, unit } = this.materialOf(adding);
    const template = this.template(adding);
    const consumed = (unit: string) =>
      html`<div class="field-row">
        ${field(t("item.quantity"), withUnit(quantity({ autofocus: true }), unit))}
        ${price(this.per(unit, format))}
      </div>`;
    const content = {
      electricity: () => consumed(CONSUMED_UNITS.electricity),
      water: () => consumed(CONSUMED_UNITS.water),
      material: () =>
        picked
          ? html`${field(
                t("item.material"),
                select({
                  name: "material_id",
                  value: picked.id,
                  autofocus: true,
                  options: materials.map(({ id, name }) => [id, name] as const),
                  onChange: (material_id) => set({ material_id, unit: "" }),
                }),
              )}
              <div class="field-row">
                ${field(t("item.quantity"), quantity())}
                ${field(
                  t("item.unit"),
                  select({
                    name: "unit",
                    value: adding.unit || unit,
                    options: units.map((option) => [option, option] as const),
                    onChange: (option) => set({ unit: option }),
                  }),
                )}
              </div>`
          : html`<p class="no-materials">
              ${t("item.no_materials")}
              <a href="${this.basePath}/materials" @click=${followLink}
                >${t("item.to_materials")}</a
              >
            </p>`,
      other: () =>
        html`${field(
            t("item.label"),
            input({
              name: "label",
              autofocus: true,
              value: adding.label,
              onInput: (label) => set({ label }),
            }),
          )}
          <div class="field-row">
            ${field(t("item.quantity"), quantity())}
            ${field(
              t("item.unit"),
              input({ name: "unit", value: adding.unit, onInput: (typed) => set({ unit: typed }) }),
            )}
          </div>
          ${price(format.currencySymbol, { min: undefined })}
          <p class="muted small">${t("item.negative_hint")}</p>`,
      template: () =>
        html`${field(
          t("item.template"),
          select({
            name: "template",
            value: template?.id,
            autofocus: true,
            options: this.templates.map(
              (option) =>
                [
                  option.id,
                  `${option.label} · ${format.unitPrice(option.unit_price)}${option.unit ? `/${option.unit}` : ""}`,
                ] as const,
            ),
            onChange: (template_id) => set({ template_id }),
          }),
        )}
        ${
          template?.basis === "running_hours"
            ? html`<p class="muted small">
                ${t("item.running_hours_hint", {
                  hours: format.quantity(run.running_seconds / 3600, "h"),
                })}
              </p>`
            : field(
                t("item.quantity"),
                withUnit(
                  quantity({
                    placeholder: t("item.default_quantity", {
                      quantity: format.toNumberInput(template?.default_quantity ?? null, 4),
                    }),
                  }),
                  template?.unit,
                ),
              )
        }`,
    };
    return formDialog({
      ...dialog,
      title: adding.kind === "template" ? t("item.new_template") : t(`item.add_${adding.kind}`),
      name: "new-item-dialog",
      submit: t("item.add"),
      disabled: adding.kind === "material" && !picked,
      onSubmit: () => this.saveNew(adding),
      content: content[adding.kind](),
    });
  }

  static override styles = [
    shared,
    css`
      .runbar {
        margin-bottom: 14px;
      }
      coinop-run-images {
        margin-bottom: 16px;
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
      .head {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .head h3 {
        flex: 1;
      }
      .head .edit {
        margin: -8px -8px -8px 0;
        --ha-icon-button-size: 40px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .facts dl {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        gap: 6px 12px;
        margin: 12px 0 0;
      }
      dt {
        color: var(--secondary-text-color);
      }
      .facts dd {
        margin: 0;
        overflow-wrap: anywhere;
      }
      .facts .tags {
        gap: 4px;
      }
      .facts .note {
        white-space: pre-wrap;
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
      .item,
      .item-head {
        display: grid;
        grid-template-columns: minmax(120px, 1fr) 96px 96px 88px 136px;
        gap: 8px;
        align-items: start;
        padding: 6px 4px;
      }
      .item + .item {
        border-top: 1px dotted var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .item > * {
        min-width: 0;
      }
      .item > .num {
        padding-top: 6px;
        white-space: normal;
      }
      .item.manual {
        box-shadow: inset 3px 0 var(--coinop-manual);
        padding-left: 10px;
      }
      .item .num.manual {
        color: var(--coinop-manual);
      }
      :host([narrow]) :is(.item, .item-head) {
        grid-template-columns: 1fr 1fr 1fr;
      }
      :host([narrow]) .item :is(.label, .actions) {
        grid-column: 1 / -1;
      }
      .item-head {
        padding-block: 2px 0;
        text-align: right;
      }
      :host([narrow]) .item-head > :is(:first-child, :last-child) {
        display: none;
      }
      .item .name {
        padding-top: 6px;
      }
      .actions {
        display: flex;
        gap: 2px;
        align-items: center;
        justify-content: flex-end;
      }
      .actions ha-icon-button {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .actions ha-icon-button.reset {
        color: var(--coinop-manual);
      }
      .lock {
        --mdc-icon-size: 18px;
        margin-inline-end: 7px;
        color: var(--secondary-text-color);
      }
      .add-item {
        margin-top: 8px;
      }
      .saved {
        color: var(--success-color, #43a047);
        margin: 0;
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
      .totals .projected {
        display: contents;
      }
      .totals .projection {
        grid-column: 1 / -1;
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
    "coinop-run-page": RunPage;
  }
}
