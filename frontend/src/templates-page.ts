// The Line Item Templates tab: the global catalogue as a table edited in place, each
// field saved as it is changed, with the Devices that add a template automatically.
import { mdiDelete, mdiPlus } from "@mdi/js";
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
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";

const BASES: QuantityBasis[] = ["entered", "running_hours"];

/** What each field shows, as its input's value. */
const fieldValues = (template: LineItemTemplate) => ({
  label: template.label,
  unit: template.unit,
  unit_price: String(template.unit_price),
  default_quantity: String(template.default_quantity),
  basis: template.basis,
});

type Field = keyof ReturnType<typeof fieldValues>;

const number = (value: string) =>
  value.trim() === "" || !Number.isFinite(Number(value)) ? undefined : Number(value);

/** The change a field's new value asks for; undefined if it is no valid value. */
const fieldChange = (field: Field, value: string) => {
  switch (field) {
    case "label":
      return value.trim() ? { label: value.trim() } : undefined;
    case "unit":
      return { unit: value.trim() };
    case "unit_price": {
      const price = number(value);
      return price === undefined ? undefined : { unit_price: price };
    }
    case "default_quantity": {
      const quantity = number(value);
      return quantity === undefined || quantity < 0 ? undefined : { default_quantity: quantity };
    }
    case "basis":
      return { basis: value as QuantityBasis };
  }
};

@customElement("wattbill-templates-page")
export class TemplatesPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) templates?: LineItemTemplate[];
  /** Current Devices, for which add a template automatically. */
  @property({ attribute: false }) devices?: Device[];
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** The new template's basis while its form is open. */
  @state() private adding?: QuantityBasis;
  @state() private failed = false;
  /** The template whose delete confirmation is open. */
  @state() private confirming?: string;

  override render() {
    const t = localize(this.hass);
    if (!this.templates) return html`<p class="muted">${t("templates.loading")}</p>`;
    return html`
      <div class="row between head">
        <h2>${t("templates.title")}</h2>
        ${
          this.adding
            ? nothing
            : html`<ha-button class="new-template" @click=${() => (this.adding = "entered")}>
                <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
                ${t("templates.new")}
              </ha-button>`
        }
      </div>
      ${this.adding ? this.renderNew(this.adding, t) : nothing}
      ${
        this.templates.length
          ? html`<table>
              <thead>
                <tr>
                  <th>${t("item.label")}</th>
                  <th>${t("item.unit")}</th>
                  <th class="num">${t("item.unit_price")}</th>
                  <th class="num">${t("templates.default_quantity")}</th>
                  <th>${t("templates.basis")}</th>
                  <th>${t("templates.automatic_for")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${this.templates.map((template) => this.renderTemplate(template, t))}
              </tbody>
            </table>`
          : html`<p class="muted">${t("templates.empty")}</p>`
      }
      ${this.failed ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
      <p class="muted small">${t("templates.copied")}</p>
    `;
  }

  private renderTemplate(template: LineItemTemplate, t: Localize) {
    const shown = fieldValues(template);
    const automatic = (this.devices ?? [])
      .filter((device) => device.settings.automatic_templates.includes(template.id))
      .map((device) => device.name)
      .join(", ");
    const confirming = this.confirming === template.id;
    return html`<tr
      class="template"
      data-id=${template.id}
      @change=${(event: Event) => this.onChange(template, event)}
    >
      <td><input name="label" aria-label=${t("item.label")} .value=${shown.label} /></td>
      <td><input name="unit" class="unit" aria-label=${t("item.unit")} .value=${shown.unit} /></td>
      <td class="num">
        <input
          type="number"
          step="any"
          name="unit_price"
          aria-label=${t("item.unit_price")}
          .value=${shown.unit_price}
        />
      </td>
      <td class="num">
        ${
          template.basis === "running_hours"
            ? html`<span class="muted small">${t("templates.from_run")}</span>`
            : html`<input
                type="number"
                step="any"
                min="0"
                name="default_quantity"
                aria-label=${t("templates.default_quantity")}
                .value=${shown.default_quantity}
              />`
        }
      </td>
      <td>${this.renderBasis(template.basis, t)}</td>
      <td class="automatic small">${automatic || html`<span class="muted">–</span>`}</td>
      <td class="actions">
        ${
          confirming
            ? html`<div class="delete-hint muted small">
                  ${t("templates.delete_hint", { label: template.label })}
                  ${automatic ? t("templates.delete_automatic", { devices: automatic }) : nothing}
                </div>
                <ha-button
                  class="small confirm-delete"
                  variant="danger"
                  @click=${() => this.delete(template)}
                >
                  ${t("templates.delete_confirm")}
                </ha-button>
                <ha-button
                  class="small"
                  appearance="plain"
                  @click=${() => (this.confirming = undefined)}
                >
                  ${t("item.cancel")}
                </ha-button>`
            : html`<ha-icon-button
                class="delete"
                .label=${t("templates.delete")}
                .path=${mdiDelete}
                @click=${() => (this.confirming = template.id)}
              ></ha-icon-button>`
        }
      </td>
    </tr>`;
  }

  private renderBasis(basis: QuantityBasis, t: Localize) {
    return html`<select name="basis" aria-label=${t("templates.basis")}>
      ${BASES.map(
        (option) =>
          html`<option value=${option} ?selected=${option === basis}>
            ${t(`basis.${option}`)}
          </option>`,
      )}
    </select>`;
  }

  private renderNew(basis: QuantityBasis, t: Localize) {
    return html`<form class="card new" @submit=${this.create}>
      <label>${t("item.label")}<input name="label" required /></label>
      <label>${t("templates.unit")}<input name="unit" /></label>
      <label
        >${t("item.unit_price")}<input type="number" step="any" name="unit_price" required
      /></label>
      <label
        >${t("templates.basis")}<select
          name="basis"
          @change=${(event: Event) =>
            (this.adding = (event.target as HTMLSelectElement).value as QuantityBasis)}
        >
          ${BASES.map(
            (option) =>
              html`<option value=${option} ?selected=${option === basis}>
                ${t(`basis.${option}`)}
              </option>`,
          )}
        </select></label
      >
      ${
        basis === "entered"
          ? html`<label
              >${t("templates.default_quantity")}<input
                type="number"
                step="any"
                min="0"
                name="default_quantity"
                value="1"
            /></label>`
          : nothing
      }
      <div class="row">
        <ha-button type="submit">${t("templates.create")}</ha-button>
        <ha-button appearance="plain" @click=${() => (this.adding = undefined)}>
          ${t("item.cancel")}
        </ha-button>
      </div>
    </form>`;
  }

  private async delete(template: LineItemTemplate) {
    this.confirming = undefined;
    await this.attempt(deleteTemplate(this.hass, template.id));
  }

  private onChange(template: LineItemTemplate, event: Event) {
    const input = event.target as HTMLInputElement;
    const field = input.name as Field;
    const shown = fieldValues(template)[field];
    const undo = () => (input.value = shown);
    const changes = fieldChange(field, input.value);
    if (!changes) return undo();
    void this.attempt(updateTemplate(this.hass, template.id, changes), undo);
  }

  private async create(event: SubmitEvent) {
    event.preventDefault();
    const entered = Object.fromEntries(new FormData(event.target as HTMLFormElement)) as Record<
      string,
      string
    >;
    const label = (entered.label ?? "").trim();
    const unitPrice = number(entered.unit_price ?? "");
    const quantity = entered.default_quantity === undefined ? 1 : number(entered.default_quantity);
    if (!label || unitPrice === undefined || quantity === undefined || quantity < 0) return;
    const template = {
      label,
      unit: (entered.unit ?? "").trim(),
      unit_price: unitPrice,
      default_quantity: quantity,
      basis: (entered.basis ?? "entered") as QuantityBasis,
    };
    if (await this.attempt(createTemplate(this.hass, template))) this.adding = undefined;
  }

  private async attempt(request: Promise<unknown>, undo = () => {}) {
    this.failed = false;
    try {
      await request;
      return true;
    } catch {
      this.failed = true;
      undo();
      return false;
    }
  }

  static override styles = [
    shared,
    css`
      .head {
        margin: 8px 0 12px;
      }
      table {
        width: 100%;
        max-width: 1100px;
        border-collapse: collapse;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 12px;
      }
      th,
      td {
        padding: 6px 10px;
        text-align: left;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        vertical-align: middle;
      }
      th {
        font-weight: 500;
        color: var(--secondary-text-color);
      }
      th.num,
      td.num {
        text-align: right;
      }
      tr:last-child td {
        border-bottom: 0;
      }
      input,
      select {
        font: inherit;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 4px 8px;
        width: 100%;
        box-sizing: border-box;
      }
      input[type="number"] {
        max-width: 110px;
        text-align: right;
      }
      input.unit {
        max-width: 80px;
      }
      .actions {
        text-align: right;
      }
      .delete-hint {
        max-width: 260px;
        margin: 0 0 6px auto;
        text-align: left;
      }
      .actions ha-icon-button {
        --ha-icon-button-size: 36px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      form.new {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 10px;
        margin-bottom: 12px;
        max-width: 1100px;
        box-sizing: border-box;
      }
      form.new label {
        display: grid;
        gap: 4px;
        color: var(--secondary-text-color);
        font-size: 12px;
      }
      form.new .row {
        grid-column: 1 / -1;
      }
      p.small {
        margin: 10px 0 0;
      }
      .error {
        color: var(--error-color, #db4437);
      }
      :host([narrow]) table,
      :host([narrow]) thead,
      :host([narrow]) tbody,
      :host([narrow]) tr,
      :host([narrow]) td {
        display: block;
      }
      :host([narrow]) thead {
        display: none;
      }
      :host([narrow]) tr {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px;
        padding: 8px;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      :host([narrow]) td {
        border: 0;
        padding: 0;
      }
      :host([narrow]) td:first-child {
        grid-column: 1 / -1;
      }
      :host([narrow]) input[type="number"] {
        max-width: none;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-templates-page": TemplatesPage;
  }
}
