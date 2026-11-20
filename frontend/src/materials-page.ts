// The Materials tab: the global catalogue, edited in place. The list itself comes
// from the panel's catalogue subscription, so every open panel shows each change.
// Opening the tab reads Spoolman's Filaments, which refreshes the linked Materials.
import {
  mdiArchiveArrowUpOutline,
  mdiArchiveOutline,
  mdiClose,
  mdiDelete,
  mdiPencil,
  mdiPlus,
  mdiStar,
  mdiStarOutline,
} from "@mdi/js";
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  archiveMaterial,
  createMaterial,
  createMaterialFromSpoolman,
  deleteMaterial,
  getMaterialTypes,
  listFilaments,
  restoreMaterial,
  updateMaterial,
  type Filament,
  type Filaments,
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
import { table, tableStyles } from "./table";

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
  price_source: "fixed" as Material["price"]["source"],
  filament_id: "",
});

type Draft = ReturnType<typeof blankDraft>;

const draftOf = ({ price, ...material }: Material): Draft => ({
  ...blankDraft(),
  name: material.name,
  form: material.form,
  type: material.type,
  density: String(material.density),
  vendor: material.vendor ?? "",
  colour: material.colour ?? "",
  diameter: material.diameter === null ? DEFAULT_DIAMETER : String(material.diameter),
  default_for_type: material.default_for_type,
  price_source: price.source,
  ...(price.source === "fixed"
    ? {
        pack_price: String(price.pack_price),
        pack_size: String(price.pack_size),
        pack_unit: price.pack_unit,
      }
    : { pack_unit: usualUnit(material.form), filament_id: String(price.filament_id) }),
});

/** Spoolman supplies everything else of a linked Material. */
const linkOf = (draft: Draft) => ({
  name: draft.name,
  default_for_type: draft.default_for_type,
  price: { source: "spoolman" as const, filament_id: Number(draft.filament_id) },
});

const filamentName = (filament: Filament) =>
  [filament.vendor, filament.name].filter(Boolean).join(" ") || filament.type || `#${filament.id}`;

const COLOUR = /^#[0-9a-f]{6}$/i;

/** The fields of a draft that the backend would refuse, so they can be marked. */
function problems(draft: Draft) {
  const positive = (value: string) => value.trim() !== "" && Number(value) > 0;
  if (draft.price_source === "spoolman")
    return new Set([
      ...(draft.name.trim() ? [] : ["name"]),
      ...(draft.filament_id ? [] : ["filament_id"]),
    ]);
  const checks = {
    name: draft.name.trim() !== "",
    type: draft.type.trim() !== "",
    density: positive(draft.density),
    diameter: draft.form !== "filament" || draft.diameter.trim() === "" || positive(draft.diameter),
    colour: draft.colour.trim() === "" || COLOUR.test(draft.colour.trim()),
    pack_price: draft.pack_price.trim() !== "" && Number(draft.pack_price) >= 0,
    pack_size: positive(draft.pack_size),
  };
  return new Set(Object.keys(checks).filter((name) => !checks[name as keyof typeof checks]));
}

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

@customElement("coinop-materials-page")
export class MaterialsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined until the catalogue arrives. */
  @property({ attribute: false }) materials?: Material[];
  @property({ type: Boolean, reflect: true }) narrow = false;

  @state() private types: MaterialType[] = [];
  /** The form's values, while creating (no `editing`) or editing a Material. */
  @state() private draft?: Draft;
  @state() private editing?: string;
  /** The backend refused the last save. */
  @state() private invalid = false;
  /** Set once the user tried to save: the form marks what is missing or wrong from then on. */
  @state() private checked = false;
  @state() private confirming?: string;
  @state() private notice?: string;
  /** Undefined until read, or when the backend couldn't answer. */
  @state() private spoolman?: Filaments;
  private typesRequested = false;
  private focusForm = false;

  protected override updated() {
    if (!this.focusForm) return;
    this.focusForm = false;
    const form = this.renderRoot.querySelector("form.material");
    form?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    form?.querySelector<HTMLInputElement>("[name=name]")?.focus({ preventScroll: true });
  }

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("hass") && this.hass && !this.typesRequested) {
      this.typesRequested = true;
      getMaterialTypes(this.hass).then(
        (types) => (this.types = types),
        () => (this.typesRequested = false),
      );
      listFilaments(this.hass).then(
        (spoolman) => (this.spoolman = spoolman),
        () => undefined,
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
      ${
        this.draft
          ? nothing
          : html`<ha-button class="new-material fab" @click=${() => this.open()}>
              <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
              ${t("materials.new")}
            </ha-button>`
      }
      ${this.notice ? html`<p class="notice">${this.notice}</p>` : nothing}
      ${this.draft ? this.renderForm(this.draft, t) : nothing}
      ${
        this.materials.length
          ? html`
              ${
                active.length
                  ? this.renderTable(active, "active", t, format)
                  : html`<p class="muted none-active">${t("materials.all_archived")}</p>`
              }
              ${
                archived.length
                  ? html`<details class="archived">
                      <summary>${t("materials.archived", { count: archived.length })}</summary>
                      ${this.renderTable(archived, "", t, format)}
                    </details>`
                  : nothing
              }
              <p class="muted small">${t("materials.frozen")}</p>
            `
          : html`<p class="muted">${t("materials.empty")}</p>`
      }
      ${this.renderSpoolman(t, format)}
    `;
  }

  private renderSpoolman(t: Localize, format: Format) {
    const spoolman = this.spoolman;
    if (!spoolman || spoolman.status === "not_configured") return nothing;
    const linkedTo = (filament: Filament) =>
      this.materials?.find(
        (material) =>
          !material.archived &&
          material.price.source === "spoolman" &&
          material.price.filament_id === filament.id,
      );
    const rows = spoolman.filaments.map((filament) => {
      const linked = linkedTo(filament);
      return html`<tr class="filament">
        <td class="name">
          <div class="row">
            <span class="swatch" style="background: ${filament.colour ?? "transparent"}"></span>
            <span class="strong">${filamentName(filament)}</span>
          </div>
        </td>
        <td>${filament.type ?? ""}</td>
        <td class="num">
          ${
            filament.price_per_gram === null
              ? html`<span class="muted">${t("spoolman.no_price")}</span>`
              : `${format.money(filament.price_per_gram * 1000)} / kg`
          }
        </td>
        <td class="actions">
          ${
            linked
              ? html`<span class="muted">${t("spoolman.linked", { name: linked.name })}</span>`
              : html`<ha-button
                  class="small"
                  appearance="plain"
                  @click=${() => this.createFrom(filament)}
                >
                  ${t("spoolman.create")}
                </ha-button>`
          }
        </td>
      </tr>`;
    });
    return html`<section class="spoolman">
      <h3>${t("spoolman.title")}</h3>
      ${
        spoolman.status === "unreachable"
          ? html`<p class="muted">${t("spoolman.unreachable")}</p>`
          : rows.length
            ? table({
                columns: [
                  { label: t("spoolman.filament") },
                  { label: t("materials.type") },
                  { label: t("materials.price_per_kg"), num: true },
                  {},
                ],
                rows,
              })
            : html`<p class="muted">${t("spoolman.empty")}</p>`
      }
    </section>`;
  }

  private renderTable(materials: Material[], name: string, t: Localize, format: Format) {
    const number = (value: number) => value.toLocaleString(this.hass.language);
    return table({
      name,
      columns: [
        { label: t("materials.name") },
        { label: t("materials.form_type") },
        { label: t("materials.properties") },
        { label: t("materials.pack") },
        { label: t("materials.price_per_kg"), num: true },
        { label: t("materials.default_for_type"), class: "center" },
        {},
      ],
      rows: materials.map(
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
              ${
                material.price.source === "fixed"
                  ? `${format.money(material.price.pack_price)} / ${format.quantity(
                      material.price.pack_size,
                      material.price.pack_unit,
                    )}`
                  : t("materials.from_spoolman")
              }
            </td>
            <td class="num">${format.money(material.price_per_gram * 1000)} / kg</td>
            <td>
              ${
                material.archived
                  ? nothing
                  : html`<ha-icon-button
                      class="star"
                      .label=${t("materials.default_for", { type: material.type })}
                      .path=${material.default_for_type ? mdiStar : mdiStarOutline}
                      .selected=${material.default_for_type}
                      @click=${() =>
                        this.act(() =>
                          updateMaterial(this.hass, material.id, {
                            default_for_type: !material.default_for_type,
                          }),
                        )}
                    ></ha-icon-button>`
              }
            </td>
            <td class="actions">${this.renderActions(material, t)}</td>
          </tr>`,
      ),
    });
  }

  private renderActions(material: Material, t: Localize) {
    if (this.confirming === material.id) {
      return html`<ha-button class="small" variant="danger" @click=${() => this.delete(material)}>
          ${t("materials.delete_confirm")}
        </ha-button>
        <ha-button class="small" appearance="plain" @click=${() => (this.confirming = undefined)}>
          ${t("materials.cancel")}
        </ha-button>`;
    }
    const action = (name: string, label: string, path: string, run: () => void) =>
      html`<ha-icon-button
        class=${name}
        .label=${label}
        .path=${path}
        @click=${run}
      ></ha-icon-button>`;
    const remove = action("delete", t("materials.delete"), mdiDelete, () => {
      this.confirming = material.id;
    });
    return material.archived
      ? html`${action("restore", t("materials.restore"), mdiArchiveArrowUpOutline, () =>
          this.act(() => restoreMaterial(this.hass, material.id)),
        )}${remove}`
      : html`${action("edit", t("materials.edit"), mdiPencil, () => this.open(material))}${action(
          "archive",
          t("materials.archive"),
          mdiArchiveOutline,
          () => this.act(() => archiveMaterial(this.hass, material.id)),
        )}${remove}`;
  }

  private renderForm(draft: Draft, t: Localize) {
    const set = (changes: Partial<Draft>) => (this.draft = { ...draft, ...changes });
    const wrong = this.checked ? problems(draft) : new Set<string>();
    const marked = (name: string) => (wrong.has(name) ? "true" : "false");
    const required = (name: string) => !["vendor", "colour", "diameter"].includes(name);
    const text = (name: "name" | "vendor", label: string) =>
      html`<label
        >${label}<input
          name=${name}
          ?required=${required(name)}
          aria-invalid=${marked(name)}
          .value=${draft[name]}
          @input=${(event: Event) => set({ [name]: (event.target as HTMLInputElement).value })}
      /></label>`;
    const number = (name: "density" | "diameter" | "pack_price" | "pack_size", label: string) =>
      html`<label
        >${label}<input
          name=${name}
          type="number"
          step="any"
          min="0"
          ?required=${required(name)}
          aria-invalid=${marked(name)}
          .value=${draft[name]}
          @input=${(event: Event) => set({ [name]: (event.target as HTMLInputElement).value })}
      /></label>`;
    const colour = draft.colour.trim();
    const known = [
      ...new Set([
        ...this.types.map((entry) => entry.type),
        ...(this.materials ?? []).map((material) => material.type),
      ]),
    ];
    const linked = draft.price_source === "spoolman";
    const details = html`<label
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
          required
          aria-invalid=${marked("type")}
          .value=${draft.type}
          @input=${(event: Event) => this.setType((event.target as HTMLInputElement).value)}
        /><datalist id="material-types">
          ${known.map((type) => html`<option value=${type}></option>`)}
        </datalist></label
      >
      ${number("density", t("materials.density"))}
      ${draft.form === "filament" ? number("diameter", t("materials.diameter")) : nothing}
      ${text("vendor", t("materials.vendor"))}
      <div class="label colour">
        ${t("materials.colour")}
        <div class="colour-row">
          <input
            type="color"
            class="colour-picker"
            aria-label=${t("materials.pick_colour")}
            .value=${COLOUR.test(colour) ? colour.toLowerCase() : "#000000"}
            @input=${(event: Event) => set({ colour: (event.target as HTMLInputElement).value })}
          />
          <input
            name="colour"
            aria-label=${t("materials.colour")}
            aria-invalid=${marked("colour")}
            placeholder="#rrggbb"
            .value=${draft.colour}
            @input=${(event: Event) => set({ colour: (event.target as HTMLInputElement).value })}
          />
          ${
            colour
              ? html`<ha-icon-button
                  class="clear-colour"
                  .label=${t("materials.clear_colour")}
                  .path=${mdiClose}
                  @click=${() => set({ colour: "" })}
                ></ha-icon-button>`
              : nothing
          }
        </div>
      </div>
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
      </div>`;
    return html`<form class="card material" novalidate @submit=${this.save}>
      <h3>${this.editing ? t("materials.edit_title") : t("materials.new_title")}</h3>
      <div class="fields">
        ${text("name", t("materials.name"))} ${this.renderCostSource(draft, set, t)}
        ${linked ? nothing : details}
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
      ${linked ? html`<p class="muted small">${t("materials.synced")}</p>` : nothing}
      ${this.invalid || wrong.size ? html`<p class="error">${t("materials.invalid")}</p>` : nothing}
      <div class="row">
        <ha-button type="submit">${t("materials.save")}</ha-button>
        <ha-button appearance="plain" @click=${this.close}>${t("materials.cancel")}</ha-button>
      </div>
    </form>`;
  }

  /** Linking happens on existing Materials; new ones come from the Filament list. */
  private renderCostSource(draft: Draft, set: (changes: Partial<Draft>) => void, t: Localize) {
    const linked = draft.price_source === "spoolman";
    if (!this.editing || (!linked && this.spoolman?.status !== "ok")) return nothing;
    const filaments = this.spoolman?.filaments ?? [];
    const known = filaments.some((filament) => String(filament.id) === draft.filament_id);
    const pick = (event: Event) => (event.target as HTMLSelectElement).value;
    return html`<label
        >${t("materials.price_source")}<select
          name="price_source"
          @change=${(event: Event) => set({ price_source: pick(event) as Draft["price_source"] })}
        >
          <option value="fixed" ?selected=${!linked}>${t("materials.price_fixed")}</option>
          <option value="spoolman" ?selected=${linked}>${t("materials.price_spoolman")}</option>
        </select></label
      >${
        linked
          ? html`<label
              >${t("materials.filament")}<select
                name="filament_id"
                aria-invalid=${this.checked && !draft.filament_id ? "true" : "false"}
                @change=${(event: Event) => set({ filament_id: pick(event) })}
              >
                <option value="" disabled ?selected=${!draft.filament_id}>
                  ${t("materials.pick_filament")}
                </option>
                ${
                  draft.filament_id && !known
                    ? html`<option value=${draft.filament_id} selected>
                        #${draft.filament_id}
                      </option>`
                    : nothing
                }
                ${filaments.map(
                  (filament) =>
                    html`<option
                      value=${filament.id}
                      ?selected=${String(filament.id) === draft.filament_id}
                    >
                      ${filamentName(filament)}
                    </option>`,
                )}
              </select></label
            >`
          : nothing
      }`;
  }

  private async createFrom(filament: Filament) {
    this.notice = undefined;
    try {
      await createMaterialFromSpoolman(this.hass, filament.id);
    } catch (error) {
      this.spoolmanFailed(error);
    }
  }

  /** Says so when Spoolman went away; otherwise the list was stale, so read it again. */
  private spoolmanFailed(error: unknown) {
    if ((error as { code?: string }).code === "spoolman_unreachable") {
      this.notice = localize(this.hass)("spoolman.unreachable");
    }
    listFilaments(this.hass).then(
      (spoolman) => (this.spoolman = spoolman),
      () => undefined,
    );
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
    this.invalid = this.checked = false;
    this.notice = undefined;
    this.focusForm = true;
  }

  private close = () => {
    this.draft = this.editing = undefined;
    this.invalid = this.checked = false;
  };

  private save = async (event: Event) => {
    event.preventDefault();
    if (!this.draft) return;
    const draft = this.draft;
    const linking = draft.price_source === "spoolman";
    this.checked = true;
    this.invalid = false;
    if (problems(draft).size) return;
    try {
      await (this.editing
        ? updateMaterial(this.hass, this.editing, linking ? linkOf(draft) : fieldsOf(draft))
        : createMaterial(this.hass, fieldsOf(draft)));
      this.close();
    } catch (error) {
      if (linking) this.spoolmanFailed(error);
      else this.invalid = true;
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
    tableStyles,
    css`
      .star {
        --ha-icon-button-size: 36px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .star[selected] {
        color: var(--warning-color, #ffa600);
      }
      .colour-row {
        display: flex;
        gap: 6px;
        align-items: center;
      }
      .colour-row input[name="colour"] {
        flex: 1;
      }
      .colour-picker {
        flex: none;
        width: 56px;
        height: 56px;
        padding: 4px;
        cursor: pointer;
      }
      .clear-colour {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
      }
      [aria-invalid="true"] {
        border-color: var(--error-color, #db4437);
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
      .spoolman {
        margin-top: 20px;
      }
      .spoolman h3 {
        margin: 0 0 8px;
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
      label,
      .label {
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
    "coinop-materials-page": MaterialsPage;
  }
}
