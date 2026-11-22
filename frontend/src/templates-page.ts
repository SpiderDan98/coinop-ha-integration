// The Line Item Templates tab: the global catalogue as a read-only table, with the
// Devices that add a template automatically. A template is created, edited and copied in
// a dialog and deleted once confirmed. The catalogue follows by subscription.
import { mdiContentCopy, mdiDelete, mdiPencil, mdiPlus } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  createTemplate,
  deleteTemplate,
  updateTemplate,
  type Device,
  type LineItemTemplate,
  type QuantityBasis,
} from "./api";
import { confirmDialog, formDialog } from "./dialog";
import { field, input, numberInput, select, withUnit } from "./fields";
import { formatter } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { Pagination, pagerStyles } from "./pagination";
import { shared } from "./styles";
import { table, tableStyles } from "./table";

const BASES: QuantityBasis[] = ["entered", "running_hours"];

/** A template's fields as the dialog's fields hold them. */
const fieldValues = (template: LineItemTemplate) => ({
  label: template.label,
  unit: template.unit,
  unit_price: String(template.unit_price),
  default_quantity: String(template.default_quantity),
  basis: template.basis,
});

type Draft = ReturnType<typeof fieldValues>;

const NEW: Draft = { label: "", unit: "", unit_price: "", default_quantity: "1", basis: "entered" };

const number = (value: string) =>
  value.trim() === "" || !Number.isFinite(Number(value)) ? undefined : Number(value);

/** What a draft asks for; undefined for a field that holds no valid value. */
const valuesOf = (draft: Draft, kept = 1) => {
  // A running-hours template has no default quantity field, so its quantity is kept.
  const quantity = draft.basis === "entered" ? number(draft.default_quantity) : kept;
  return {
    label: draft.label.trim() || undefined,
    unit: draft.unit.trim(),
    unit_price: number(draft.unit_price),
    default_quantity: quantity !== undefined && quantity < 0 ? undefined : quantity,
    basis: draft.basis,
  };
};

/** A price, or the currency alone, with the unit it counts in: "€0.15/h", "€/h". */
const per = (price: string, unit: string) => (unit ? `${price}/${unit}` : price);

@customElement("coinop-templates-page")
export class TemplatesPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) templates?: LineItemTemplate[];
  /** Current Devices, for which add a template automatically. */
  @property({ attribute: false }) devices?: Device[];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** The dialog's draft, for a new template without `template`; `tried` marks invalid fields. */
  @state() private editing?: { template?: LineItemTemplate; draft: Draft; tried: boolean };
  /** Set while its delete confirmation is open. */
  @state() private deleting?: LineItemTemplate;
  @state() private saving = false;
  /** What could not be done: "save" shows in the dialog, "delete" on the page. */
  @state() private failed?: "save" | "delete";
  private readonly pages = new Pagination(this);

  override render() {
    const t = localize(this.hass);
    if (!this.templates) return html`<p class="muted">${t("templates.loading")}</p>`;
    return html`
      <ha-button class="new-template fab" @click=${() => this.open(NEW)}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("templates.new")}
      </ha-button>
      ${
        this.templates.length
          ? table({
              name: "templates",
              columns: [
                { label: t("item.label") },
                { label: t("item.unit") },
                { label: t("item.unit_price"), num: true },
                { label: t("templates.default_quantity"), num: true },
                { label: t("templates.basis") },
                { label: t("templates.automatic_for") },
                {},
              ],
              rows: this.pages
                .of(this.templates)
                .map((template) => this.renderTemplate(template, t)),
              pager: this.pages.controls(this.templates.length, t),
            })
          : html`<p class="muted">${t("templates.empty")}</p>`
      }
      ${this.failed === "delete" ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
      <p class="muted small">${t("templates.copied")}</p>
      ${this.editing ? this.renderDialog(this.editing, t) : nothing}
      ${this.deleting ? this.renderDeleteDialog(this.deleting, t) : nothing}
    `;
  }

  /** The names of the Devices that add the template to their Runs. */
  private automaticFor({ id }: LineItemTemplate) {
    return (this.devices ?? [])
      .filter((device) => device.settings.automatic_templates.includes(id))
      .map((device) => device.name)
      .join(", ");
  }

  private renderTemplate(template: LineItemTemplate, t: Localize) {
    const format = formatter(this.hass);
    const none = html`<span class="muted">–</span>`;
    return html`<tr class="template" data-id=${template.id}>
      <td>${template.label}</td>
      <td>${template.unit || none}</td>
      <td class="num">${per(format.unitPrice(template.unit_price), template.unit)}</td>
      <td class="num">
        ${
          template.basis === "running_hours"
            ? html`<span class="muted small">${t("templates.from_run")}</span>`
            : format.quantity(template.default_quantity, template.unit).trim()
        }
      </td>
      <td>${t(`basis.${template.basis}`)}</td>
      <td class="automatic small">${this.automaticFor(template) || none}</td>
      <td class="actions">
        <ha-icon-button
          class="edit"
          .label=${t("templates.edit")}
          .path=${mdiPencil}
          @click=${() => this.open(fieldValues(template), template)}
        ></ha-icon-button>
        <ha-icon-button
          class="duplicate"
          .label=${t("templates.duplicate")}
          .path=${mdiContentCopy}
          @click=${() => this.open(fieldValues(template))}
        ></ha-icon-button>
        <ha-icon-button
          class="delete"
          .label=${t("templates.delete")}
          .path=${mdiDelete}
          @click=${() => (this.deleting = template)}
        ></ha-icon-button>
      </td>
    </tr>`;
  }

  private renderDialog(editing: NonNullable<typeof this.editing>, t: Localize) {
    const { template, draft, tried } = editing;
    const change = (changes: Partial<Draft>) =>
      (this.editing = { ...editing, draft: { ...draft, ...changes } });
    const values = valuesOf(draft, template?.default_quantity);
    const invalid = (name: keyof Draft) => tried && values[name] === undefined;
    const unit = draft.unit.trim();
    return formDialog({
      t,
      title: template ? t("templates.edit_title") : t("templates.new"),
      name: "template-dialog",
      busy: this.saving,
      error: this.failed === "save" && t("run.save_failed"),
      onCancel: () => (this.editing = undefined),
      onSubmit: () => this.save(editing),
      content: html`${field(
          t("item.label"),
          input({
            name: "label",
            required: true,
            autofocus: true,
            value: draft.label,
            invalid: invalid("label"),
            onInput: (label) => change({ label }),
          }),
        )}
        <div class="field-row">
          ${field(
            t("item.unit_price"),
            withUnit(
              numberInput({
                name: "unit_price",
                min: undefined,
                required: true,
                value: draft.unit_price,
                invalid: invalid("unit_price"),
                onInput: (unit_price) => change({ unit_price }),
              }),
              per(formatter(this.hass).currencySymbol, unit),
            ),
          )}
          ${field(
            t("item.unit"),
            input({
              name: "unit",
              value: draft.unit,
              onInput: (entered) => change({ unit: entered }),
            }),
          )}
        </div>
        <div class="field-row">
          ${field(
            t("templates.basis"),
            select({
              name: "basis",
              value: draft.basis,
              options: BASES.map((basis) => [basis, t(`basis.${basis}`)]),
              onChange: (basis) => change({ basis: basis as QuantityBasis }),
            }),
          )}
          ${
            draft.basis === "entered"
              ? field(
                  t("templates.default_quantity"),
                  withUnit(
                    numberInput({
                      name: "default_quantity",
                      value: draft.default_quantity,
                      invalid: invalid("default_quantity"),
                      onInput: (default_quantity) => change({ default_quantity }),
                    }),
                    unit,
                  ),
                )
              : nothing
          }
        </div>`,
    });
  }

  private renderDeleteDialog(template: LineItemTemplate, t: Localize) {
    const devices = this.automaticFor(template);
    return confirmDialog({
      t,
      title: t("delete.title", { name: template.label }),
      name: "delete-template-dialog",
      content: html`<p>${t("templates.delete_hint", { label: template.label })}</p>
        ${devices ? html`<p>${t("templates.delete_automatic", { devices })}</p>` : nothing}`,
      confirm: t("templates.delete_confirm"),
      onCancel: () => (this.deleting = undefined),
      onConfirm: () => this.delete(template),
    });
  }

  /** Without `template` the draft becomes a new one, as for a copy. */
  private open(draft: Draft, template?: LineItemTemplate) {
    this.failed = undefined;
    this.editing = { template, draft, tried: false };
  }

  /** Creates the template, or sends what changed of the one being edited. */
  private async save(editing: NonNullable<typeof this.editing>) {
    const { template } = editing;
    const { label, unit_price, default_quantity, ...rest } = valuesOf(
      editing.draft,
      template?.default_quantity,
    );
    if (label === undefined || unit_price === undefined || default_quantity === undefined) {
      this.editing = { ...editing, tried: true };
      return;
    }
    const fields = { ...rest, label, unit_price, default_quantity };
    const changes = Object.fromEntries(
      Object.entries(fields).filter(
        ([name, value]) => value !== template?.[name as keyof typeof fields],
      ),
    );
    if (template && !Object.keys(changes).length) {
      this.editing = undefined;
      return;
    }
    this.saving = true;
    this.failed = undefined;
    try {
      await (template
        ? updateTemplate(this.hass, template.id, changes)
        : createTemplate(this.hass, fields));
      this.editing = undefined;
    } catch {
      this.failed = "save";
    } finally {
      this.saving = false;
    }
  }

  private async delete(template: LineItemTemplate) {
    this.deleting = undefined;
    this.failed = undefined;
    try {
      await deleteTemplate(this.hass, template.id);
    } catch {
      this.failed = "delete";
    }
  }

  static override styles = [
    shared,
    tableStyles,
    pagerStyles,
    css`
      :host > p.small {
        margin: 10px 0 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-templates-page": TemplatesPage;
  }
}
