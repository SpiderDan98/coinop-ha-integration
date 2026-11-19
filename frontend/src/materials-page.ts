// The Materials tab: the global catalogue, edited in place. The list itself comes
// from the panel's catalogue subscription, so every open panel shows each change.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  archiveMaterial,
  createMaterial,
  deleteMaterial,
  getMaterialTypes,
  restoreMaterial,
  updateMaterial,
  type Material,
  type MaterialFields,
  type MaterialForm,
  type MaterialType,
  type PackUnit,
} from "./api";
import { formatter, type Format } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";

const FORMS: MaterialForm[] = ["filament", "resin"];
const PACK_UNITS: PackUnit[] = ["g", "ml"];
const DEFAULT_DIAMETER = "1.75";
const usualUnit = (form: MaterialForm): PackUnit => (form === "resin" ? "ml" : "g");

// Inputs keep their text as typed; numbers are read only when saving.
const blankDraft = () => ({
  name: "",
  form: "filament" as MaterialForm,
  type: "",
  density: "",
  vendor: "",
  colour: "",
  diameter: DEFAULT_DIAMETER,
  pack_price: "",
  pack_size: "1000",
  pack_unit: "g" as PackUnit,
  default_for_type: false,
});

type Draft = ReturnType<typeof blankDraft>;

const draftOf = (material: Material): Draft => ({
  name: material.name,
  form: material.form,
  type: material.type,
  density: String(material.density),
  vendor: material.vendor ?? "",
  colour: material.colour ?? "",
  diameter: material.diameter === null ? DEFAULT_DIAMETER : String(material.diameter),
  pack_price: String(material.price.pack_price),
  pack_size: String(material.price.pack_size),
  pack_unit: material.price.pack_unit,
  default_for_type: material.default_for_type,
});

const fieldsOf = (draft: Draft): MaterialFields => ({
  name: draft.name,
  form: draft.form,
  type: draft.type,
  density: Number(draft.density),
  vendor: draft.vendor.trim() || null,
  colour: draft.colour.trim() || null,
  diameter: draft.form === "filament" ? Number(draft.diameter) || null : null,
  default_for_type: draft.default_for_type,
  price: {
    source: "fixed",
    pack_price: Number(draft.pack_price),
    pack_size: Number(draft.pack_size),
    pack_unit: draft.pack_unit,
  },
});

@customElement("wattbill-materials-page")
export class MaterialsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) materials?: Material[];
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private types: MaterialType[] = [];
  /** The form's values, while creating (no `editing`) or editing a Material. */
  @state() private draft?: Draft;
  @state() private editing?: string;
  @state() private invalid = false;
  @state() private confirming?: string;
  @state() private notice?: string;
  private typesRequested = false;

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("hass") && this.hass && !this.typesRequested) {
      this.typesRequested = true;
      getMaterialTypes(this.hass).then(
        (types) => (this.types = types),
        () => (this.typesRequested = false),
      );
    }
  }

  override render() {
    const t = localize(this.hass);
    if (!this.materials) return html`<p class="muted">${t("materials.loading")}</p>`;
    const format = formatter(this.hass);
    const active = this.materials.filter((material) => !material.archived);
    const archived = this.materials.filter((material) => material.archived);
    return html`
      <div class="head row between">
        <h2>${t("tab.materials")}</h2>
        <button class="primary" @click=${() => this.open()}>${t("materials.new")}</button>
      </div>
      ${this.notice ? html`<p class="notice">${this.notice}</p>` : nothing}
      ${this.draft ? this.renderForm(this.draft, t) : nothing}
      ${
        this.materials.length
          ? html`
              <div class="card flush active">${this.renderTable(active, t, format)}</div>
              ${
                archived.length
                  ? html`<details class="archived">
                      <summary>${t("materials.archived", { count: archived.length })}</summary>
                      <div class="card flush">${this.renderTable(archived, t, format)}</div>
                    </details>`
                  : nothing
              }
              <p class="muted small">${t("materials.frozen")}</p>
            `
          : html`<p class="muted">${t("materials.empty")}</p>`
      }
    `;
  }

  private renderTable(materials: Material[], t: Localize, format: Format) {
    const number = (value: number) => value.toLocaleString(this.hass.language);
    return html`<table>
      ${materials.map(
        (material) =>
          html`<tr class="material">
            <td class="name">
              <div class="row">
                <span class="swatch" style="background: ${material.colour ?? "transparent"}"></span>
                <div>
                  <div class="strong">${material.name}</div>
                  ${material.vendor ? html`<div class="muted small">${material.vendor}</div>` : nothing}
                </div>
              </div>
            </td>
            <td>${t(`form.${material.form}`)} · ${material.type}</td>
            <td class="small">
              ${number(material.density)}
              g/cm³${material.diameter === null ? "" : ` · ⌀ ${number(material.diameter)} mm`}
            </td>
            <td class="small">
              ${format.money(material.price.pack_price)} /
              ${format.quantity(material.price.pack_size, material.price.pack_unit)}
            </td>
            <td class="num">${format.unitPrice(material.price_per_gram)} / g</td>
            <td>
              ${
                material.archived
                  ? nothing
                  : html`<button
                      class="star ${material.default_for_type ? "on" : ""}"
                      title=${t("materials.default_for", { type: material.type })}
                      aria-pressed=${material.default_for_type}
                      @click=${() =>
                        this.act(() =>
                          updateMaterial(this.hass, material.id, {
                            default_for_type: !material.default_for_type,
                          }),
                        )}
                    >
                      ${material.default_for_type ? "★" : "☆"}
                    </button>`
              }
            </td>
            <td class="actions">${this.renderActions(material, t)}</td>
          </tr>`,
      )}
    </table>`;
  }

  private renderActions(material: Material, t: Localize) {
    if (this.confirming === material.id) {
      return html`<button class="danger" @click=${() => this.delete(material)}>
          ${t("materials.delete_confirm")}</button
        ><button @click=${() => (this.confirming = undefined)}>${t("materials.cancel")}</button>`;
    }
    const confirm = () => (this.confirming = material.id);
    return material.archived
      ? html`<button @click=${() => this.act(() => restoreMaterial(this.hass, material.id))}>
            ${t("materials.restore")}</button
          ><button @click=${confirm}>${t("materials.delete")}</button>`
      : html`<button @click=${() => this.open(material)}>${t("materials.edit")}</button
          ><button @click=${() => this.act(() => archiveMaterial(this.hass, material.id))}>
            ${t("materials.archive")}</button
          ><button @click=${confirm}>${t("materials.delete")}</button>`;
  }

  private renderForm(draft: Draft, t: Localize) {
    const set = (changes: Partial<Draft>) => (this.draft = { ...draft, ...changes });
    const text = (name: "name" | "vendor" | "colour", label: string, placeholder = "") =>
      html`<label
        >${label}<input
          name=${name}
          .value=${draft[name]}
          placeholder=${placeholder}
          @input=${(event: Event) => set({ [name]: (event.target as HTMLInputElement).value })}
      /></label>`;
    const number = (name: "density" | "diameter" | "pack_price" | "pack_size", label: string) =>
      html`<label
        >${label}<input
          name=${name}
          type="number"
          step="any"
          min="0"
          .value=${draft[name]}
          @input=${(event: Event) => set({ [name]: (event.target as HTMLInputElement).value })}
      /></label>`;
    const known = [
      ...new Set([
        ...this.types.map((entry) => entry.type),
        ...(this.materials ?? []).map((material) => material.type),
      ]),
    ];
    return html`<form class="card material" @submit=${this.save}>
      <h3>${this.editing ? t("materials.edit_title") : t("materials.new_title")}</h3>
      <div class="fields">
        ${text("name", t("materials.name"))}
        <label
          >${t("materials.form")}<select
            name="form"
            @change=${(event: Event) => {
              const form = (event.target as HTMLSelectElement).value as MaterialForm;
              set({ form, pack_unit: usualUnit(form) });
            }}
          >
            ${FORMS.map(
              (form) =>
                html`<option value=${form} ?selected=${draft.form === form}>
                  ${t(`form.${form}`)}
                </option>`,
            )}
          </select></label
        >
        <label
          >${t("materials.type")}<input
            name="type"
            list="material-types"
            .value=${draft.type}
            @input=${(event: Event) => this.setType((event.target as HTMLInputElement).value)}
          /><datalist id="material-types">
            ${known.map((type) => html`<option value=${type}></option>`)}
          </datalist></label
        >
        ${number("density", t("materials.density"))}
        ${draft.form === "filament" ? number("diameter", t("materials.diameter")) : nothing}
        ${text("vendor", t("materials.vendor"))} ${text("colour", t("materials.colour"), "#rrggbb")}
        ${number("pack_price", t("materials.pack_price"))}
        <div class="pack">
          ${number("pack_size", t("materials.pack_size"))}
          <select
            name="pack_unit"
            aria-label=${t("materials.pack_unit")}
            @change=${(event: Event) =>
              set({ pack_unit: (event.target as HTMLSelectElement).value as PackUnit })}
          >
            ${PACK_UNITS.map(
              (unit) =>
                html`<option value=${unit} ?selected=${draft.pack_unit === unit}>${unit}</option>`,
            )}
          </select>
        </div>
        <label class="check"
          ><input
            name="default_for_type"
            type="checkbox"
            .checked=${draft.default_for_type}
            @change=${(event: Event) =>
              set({ default_for_type: (event.target as HTMLInputElement).checked })}
          />${t("materials.default_for_type")}</label
        >
      </div>
      ${this.invalid ? html`<p class="error">${t("materials.invalid")}</p>` : nothing}
      <div class="row">
        <button class="primary" type="submit">${t("materials.save")}</button>
        <button type="button" @click=${this.close}>${t("materials.cancel")}</button>
      </div>
    </form>`;
  }

  /** A built-in type pre-fills its form, density and usual pack unit. */
  private setType(type: string) {
    if (!this.draft) return;
    const known = this.types.find(
      (entry) => entry.type.toLocaleLowerCase() === type.trim().toLocaleLowerCase(),
    );
    this.draft = known
      ? {
          ...this.draft,
          type,
          form: known.form,
          density: String(known.density),
          pack_unit: usualUnit(known.form),
        }
      : { ...this.draft, type };
  }

  private open(material?: Material) {
    this.draft = material ? draftOf(material) : blankDraft();
    this.editing = material?.id;
    this.invalid = false;
    this.notice = undefined;
  }

  private close = () => {
    this.draft = this.editing = undefined;
    this.invalid = false;
  };

  private save = async (event: Event) => {
    event.preventDefault();
    if (!this.draft) return;
    const fields = fieldsOf(this.draft);
    try {
      await (this.editing
        ? updateMaterial(this.hass, this.editing, fields)
        : createMaterial(this.hass, fields));
      this.close();
    } catch {
      this.invalid = true;
    }
  };

  private async delete(material: Material) {
    this.confirming = undefined;
    const deleted = await deleteMaterial(this.hass, material.id);
    this.notice = deleted
      ? undefined
      : localize(this.hass)("materials.archived_instead", { name: material.name });
  }

  private async act(change: () => Promise<unknown>) {
    this.notice = undefined;
    await change();
  }

  static override styles = [
    shared,
    css`
      .head {
        margin: 8px 0 12px;
      }
      button {
        font: inherit;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        border-radius: 8px;
        padding: 6px 12px;
        cursor: pointer;
      }
      button.primary {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      button.danger {
        color: var(--error-color, #db4437);
      }
      button.star {
        border: 0;
        background: none;
        font-size: 18px;
        padding: 2px 6px;
        color: var(--secondary-text-color);
      }
      button.star.on {
        color: var(--warning-color, #ffa600);
      }
      .card.flush {
        padding: 0;
        overflow-x: auto;
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      td {
        padding: 8px 12px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      tr:first-child td {
        border-top: 0;
      }
      .actions {
        white-space: nowrap;
        text-align: right;
      }
      .actions button + button {
        margin-left: 6px;
      }
      .swatch {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        flex: none;
      }
      .archived {
        margin-top: 12px;
      }
      .archived summary {
        cursor: pointer;
        margin-bottom: 8px;
        color: var(--secondary-text-color);
      }
      .archived tr {
        opacity: 0.7;
      }
      .notice {
        padding: 8px 12px;
        border-radius: 8px;
        background: color-mix(in srgb, var(--warning-color, #ffa600) 16%, transparent);
      }
      form.material {
        margin-bottom: 12px;
      }
      .fields {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 10px 14px;
        margin: 12px 0;
      }
      label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      label.check {
        flex-direction: row;
        align-items: center;
        align-self: end;
        font-size: 14px;
        color: var(--primary-text-color);
      }
      input,
      select {
        font: inherit;
        font-size: 14px;
        padding: 6px 8px;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
      }
      .pack {
        display: flex;
        gap: 6px;
        align-items: end;
      }
      .pack label {
        flex: 1;
        min-width: 0;
      }
      .pack select {
        flex: none;
      }
      input {
        min-width: 0;
      }
      .error {
        color: var(--error-color, #db4437);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-materials-page": MaterialsPage;
  }
}
