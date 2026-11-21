// The Materials tab: the global catalogue, listed read-only and edited in a dialog. The
// list itself comes from the panel's catalogue subscription, so every open panel shows
// each change.
// Opening the tab reads Spoolman's Filaments, which refreshes the linked Materials.
import {
  mdiArchiveArrowUpOutline,
  mdiArchiveOutline,
  mdiClose,
  mdiContentCopy,
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
  MATERIAL_FORMS,
  PACK_UNITS,
  type Filament,
  type Filaments,
  type Material,
  type MaterialFields,
  type MaterialForm,
  type MaterialType,
  type PackUnit,
} from "./api";
import { confirmDialog, formDialog } from "./dialog";
import { checkbox, field, input, numberInput, select, withUnit } from "./fields";
import { formatter, type Format } from "./format";
import type { HomeAssistant } from "./hass";
import { localize, type Key, type Localize } from "./localize";
import { Pagination, pagerStyles } from "./pagination";
import { shared } from "./styles";
import { table, tableStyles } from "./table";

const DEFAULT_DIAMETER = "1.75";
// The form Other has no usual pack unit: it keeps the one picked.
const USUAL_UNIT: Partial<Record<MaterialForm, PackUnit>> = {
  filament: "g",
  resin: "ml",
  detergent: "ml",
  fabric_softener: "ml",
  laundry_additive: "g",
  dishwasher_product: "pcs",
  beverage_ingredient: "g",
};
const usualUnit = (form: MaterialForm, picked: PackUnit) => USUAL_UNIT[form] ?? picked;

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
  density: material.density === null ? "" : String(material.density),
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
    : { pack_unit: usualUnit(material.form, "g"), filament_id: String(price.filament_id) }),
});

/** A copy leaves its type's default and a Spoolman link with the original. */
const copyOf = (material: Material): Draft => ({
  ...draftOf(material),
  default_for_type: false,
  price_source: "fixed",
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

const UNLINKED_FORMS = new Set<MaterialForm>([
  "dishwasher_product",
  "beverage_ingredient",
  "other",
]);
const hasBuiltInTypes = (form: MaterialForm) => form !== "other";
const byPiece = (draft: Draft) => draft.pack_unit === "pcs";
const hasDiameter = (draft: Draft) => draft.form === "filament" && !byPiece(draft);

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
    density: byPiece(draft) || positive(draft.density),
    diameter: !hasDiameter(draft) || draft.diameter.trim() === "" || positive(draft.diameter),
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
  density: byPiece(draft) ? null : Number(draft.density),
  vendor: draft.vendor.trim() || null,
  colour: draft.colour.trim() || null,
  diameter: hasDiameter(draft) ? Number(draft.diameter) || null : null,
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
  /** The dialog's values, while creating (no `editing`) or editing a Material. */
  @state() private draft?: Draft;
  @state() private editing?: string;
  @state() private saving = false;
  /** Why the last save failed. */
  @state() private failure?: Key;
  /** Set once the user tried to save: the dialog marks what is missing or wrong from then on. */
  @state() private checked = false;
  @state() private deleting?: Material;
  @state() private notice?: string;
  /** Undefined until read, or when the backend couldn't answer. */
  @state() private spoolman?: Filaments;
  private typesRequested = false;
  private readonly pages = {
    active: new Pagination(this),
    archived: new Pagination(this),
    filaments: new Pagination(this),
  };

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
      <ha-button class="new-material fab" @click=${() => this.open()}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("materials.new")}
      </ha-button>
      ${this.notice ? html`<p class="notice">${this.notice}</p>` : nothing}
      ${
        this.materials.length
          ? html`
              ${
                active.length
                  ? this.renderTable(active, "active", this.pages.active, t, format)
                  : html`<p class="muted none-active">${t("materials.all_archived")}</p>`
              }
              ${
                archived.length
                  ? html`<details class="archived">
                      <summary>${t("materials.archived", { count: archived.length })}</summary>
                      ${this.renderTable(archived, "", this.pages.archived, t, format)}
                    </details>`
                  : nothing
              }
              <p class="muted small">${t("materials.frozen")}</p>
            `
          : html`<p class="muted">${t("materials.empty")}</p>`
      }
      ${this.renderSpoolman(t, format)} ${this.draft ? this.renderDialog(this.draft, t) : nothing}
      ${this.deleting ? this.renderDeleteDialog(this.deleting, t) : nothing}
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
    const rows = this.pages.filaments.of(spoolman.filaments).map((filament) => {
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
                pager: this.pages.filaments.controls(spoolman.filaments.length, t),
              })
            : html`<p class="muted">${t("spoolman.empty")}</p>`
      }
    </section>`;
  }

  private renderTable(
    materials: Material[],
    name: string,
    pages: Pagination,
    t: Localize,
    format: Format,
  ) {
    const number = (value: number) => value.toLocaleString(this.hass.language);
    return table({
      name,
      columns: [
        { label: t("materials.name") },
        { label: t("materials.form_type") },
        { label: t("materials.properties") },
        { label: t("materials.pack") },
        { label: t("materials.unit_price"), num: true },
        { label: t("materials.default_for_type"), class: "center" },
        {},
      ],
      pager: pages.controls(materials.length, t),
      rows: pages.of(materials).map(
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
              ${
                material.density === null
                  ? nothing
                  : `${number(material.density)} g/cm³${
                      material.diameter === null ? "" : ` · ⌀ ${number(material.diameter)} mm`
                    }`
              }
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
            <td class="num">
              ${
                material.price_per_piece === null
                  ? `${format.money((material.price_per_gram ?? 0) * 1000)} / kg`
                  : `${format.money(material.price_per_piece)} / pcs`
              }
            </td>
            <td class="center">
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
    const action = (name: string, label: string, path: string, run: () => void) =>
      html`<ha-icon-button
        class=${name}
        .label=${label}
        .path=${path}
        @click=${run}
      ></ha-icon-button>`;
    const remove = action("delete", t("materials.delete"), mdiDelete, () => {
      this.deleting = material;
    });
    return material.archived
      ? html`${action("restore", t("materials.restore"), mdiArchiveArrowUpOutline, () =>
          this.act(() => restoreMaterial(this.hass, material.id)),
        )}${remove}`
      : html`${action("edit", t("materials.edit"), mdiPencil, () =>
          this.open(draftOf(material), material.id),
        )}${action("duplicate", t("materials.duplicate"), mdiContentCopy, () =>
          this.open(copyOf(material)),
        )}${action("archive", t("materials.archive"), mdiArchiveOutline, () =>
          this.act(() => archiveMaterial(this.hass, material.id)),
        )}${remove}`;
  }

  private renderDialog(draft: Draft, t: Localize) {
    const set = (changes: Partial<Draft>) => (this.draft = { ...draft, ...changes });
    const wrong = this.checked ? problems(draft) : new Set<string>();
    const failure = this.failure ?? (wrong.size ? "materials.invalid" : undefined);
    const number = (name: "density" | "diameter" | "pack_price" | "pack_size", label?: string) =>
      numberInput({
        name,
        label,
        required: name !== "diameter",
        invalid: wrong.has(name),
        value: draft[name],
        onInput: (value) => set({ [name]: value }),
      });
    const colour = draft.colour.trim();
    const setColour = (value: string) => set({ colour: value });
    const builtIn = hasBuiltInTypes(draft.form);
    const known = [
      ...new Set([
        ...(builtIn ? this.types.map((entry) => entry.type) : []),
        ...(this.materials ?? [])
          .filter((material) => builtIn || material.form === draft.form)
          .map((material) => material.type),
      ]),
    ];
    const linked = draft.price_source === "spoolman";
    const details = html`<div class="field-row">
        ${field(
          t("materials.form"),
          select({
            name: "form",
            value: draft.form,
            options: MATERIAL_FORMS.map((form) => [form, t(`form.${form}`)]),
            onChange: (picked) => {
              const form = picked as MaterialForm;
              set({ form, pack_unit: usualUnit(form, draft.pack_unit) });
            },
          }),
        )}
        ${field(
          t("materials.type"),
          input({
            name: "type",
            list: known,
            required: true,
            invalid: wrong.has("type"),
            value: draft.type,
            onInput: (type) => this.setType(type),
          }),
        )}
      </div>
      ${
        byPiece(draft)
          ? nothing
          : html`<div class="field-row">
              ${field(t("materials.density"), withUnit(number("density"), "g/cm³"))}
              ${
                hasDiameter(draft)
                  ? field(t("materials.diameter"), withUnit(number("diameter"), "mm"))
                  : nothing
              }
            </div>`
      }
      <div class="field-row">
        ${field(
          t("materials.vendor"),
          input({ name: "vendor", value: draft.vendor, onInput: (vendor) => set({ vendor }) }),
        )}
        ${field(
          t("materials.colour"),
          html`<div class="group">
            ${input({
              type: "color",
              label: t("materials.pick_colour"),
              value: COLOUR.test(colour) ? colour.toLowerCase() : "#000000",
              onInput: setColour,
            })}
            ${input({
              name: "colour",
              label: t("materials.colour"),
              placeholder: "#rrggbb",
              invalid: wrong.has("colour"),
              value: draft.colour,
              onInput: setColour,
            })}
            ${
              colour
                ? html`<ha-icon-button
                    class="clear-colour"
                    .label=${t("materials.clear_colour")}
                    .path=${mdiClose}
                    @click=${() => setColour("")}
                  ></ha-icon-button>`
                : nothing
            }
          </div>`,
          { name: "colour", group: true },
        )}
      </div>
      <div class="field-row">
        ${field(
          t("materials.pack_price"),
          withUnit(number("pack_price"), formatter(this.hass).currencySymbol),
        )}
        ${field(
          t("materials.pack_size"),
          html`<div class="group">
            ${number("pack_size", t("materials.pack_size"))}
            ${select({
              name: "pack_unit",
              label: t("materials.pack_unit"),
              value: draft.pack_unit,
              options: PACK_UNITS.map((unit) => [unit, unit]),
              onChange: (unit) => set({ pack_unit: unit as PackUnit }),
            })}
          </div>`,
          { name: "pack", group: true },
        )}
      </div>`;
    return formDialog({
      t,
      title: this.editing ? t("materials.edit_title") : t("materials.new_title"),
      name: "material-dialog",
      busy: this.saving,
      error: failure && t(failure),
      onCancel: () => this.close(),
      onSubmit: () => this.save(draft),
      content: html`${field(
        t("materials.name"),
        input({
          name: "name",
          autofocus: true,
          required: true,
          invalid: wrong.has("name"),
          value: draft.name,
          onInput: (name) => set({ name }),
        }),
      )}
      ${this.renderCostSource(draft, set, t)} ${linked ? nothing : details}
      ${checkbox({
        name: "default_for_type",
        label: t("materials.default_for_type"),
        checked: draft.default_for_type,
        onChange: (default_for_type) => set({ default_for_type }),
      })}
      ${linked ? html`<p class="muted small">${t("materials.synced")}</p>` : nothing}`,
    });
  }

  /** Linking happens on existing Materials; new ones come from the Filament list.
   * A Material bought by the piece or of a form in `UNLINKED_FORMS` is never linked. */
  private renderCostSource(draft: Draft, set: (changes: Partial<Draft>) => void, t: Localize) {
    const linked = draft.price_source === "spoolman";
    const edited = this.materials?.find((material) => material.id === this.editing);
    if (!edited || edited.price_per_piece !== null || byPiece(draft)) return nothing;
    if (UNLINKED_FORMS.has(edited.form) || UNLINKED_FORMS.has(draft.form)) return nothing;
    if (!linked && this.spoolman?.status !== "ok") return nothing;
    const filaments = this.spoolman?.filaments ?? [];
    const known = filaments.some((filament) => String(filament.id) === draft.filament_id);
    return html`<div class="field-row">
      ${field(
        t("materials.price_source"),
        select({
          name: "price_source",
          value: draft.price_source,
          options: [
            ["fixed", t("materials.price_fixed")],
            ["spoolman", t("materials.price_spoolman")],
          ],
          onChange: (source) => set({ price_source: source as Draft["price_source"] }),
        }),
      )}
      ${
        linked
          ? field(
              t("materials.filament"),
              select({
                name: "filament_id",
                value: draft.filament_id,
                invalid: this.checked && !draft.filament_id,
                options: [
                  ["", t("materials.pick_filament"), true],
                  ...(draft.filament_id && !known
                    ? [[draft.filament_id, `#${draft.filament_id}`] as const]
                    : []),
                  ...filaments.map(
                    (filament) => [String(filament.id), filamentName(filament)] as const,
                  ),
                ],
                onChange: (filament_id) => set({ filament_id }),
              }),
            )
          : nothing
      }
    </div>`;
  }

  private renderDeleteDialog(material: Material, t: Localize) {
    return confirmDialog({
      t,
      title: t("delete.title", { name: material.name }),
      name: "delete-dialog",
      content: html`<p class="muted small">${t("materials.delete_warning")}</p>`,
      confirm: t("materials.delete_confirm"),
      onCancel: () => (this.deleting = undefined),
      onConfirm: () => this.delete(material),
    });
  }

  private async createFrom(filament: Filament) {
    this.notice = undefined;
    try {
      await createMaterialFromSpoolman(this.hass, filament.id);
    } catch (error) {
      const failure = this.spoolmanFailure(error);
      if (failure) this.notice = localize(this.hass)(failure);
    }
  }

  /** What to say when Spoolman went away; otherwise the list was stale, so it is read again. */
  private spoolmanFailure(error: unknown) {
    listFilaments(this.hass).then(
      (spoolman) => (this.spoolman = spoolman),
      () => undefined,
    );
    return (error as { code?: string }).code === "spoolman_unreachable"
      ? "spoolman.unreachable"
      : undefined;
  }

  /** A built-in type pre-fills its form, density and pack unit, except under a form without any. */
  private setType(type: string) {
    if (!this.draft) return;
    const known =
      hasBuiltInTypes(this.draft.form) &&
      this.types.find(
        (entry) => entry.type.toLocaleLowerCase() === type.trim().toLocaleLowerCase(),
      );
    this.draft = known
      ? {
          ...this.draft,
          type,
          form: known.form,
          density: known.density === null ? "" : String(known.density),
          pack_unit: known.pack_unit,
        }
      : { ...this.draft, type };
  }

  private open(draft = blankDraft(), editing?: string) {
    this.draft = draft;
    this.editing = editing;
    this.failure = undefined;
    this.checked = false;
    this.notice = undefined;
  }

  private close() {
    this.draft = this.editing = undefined;
  }

  private async save(draft: Draft) {
    const linking = draft.price_source === "spoolman";
    this.checked = true;
    this.failure = undefined;
    if (problems(draft).size) return;
    this.saving = true;
    try {
      await (this.editing
        ? updateMaterial(this.hass, this.editing, linking ? linkOf(draft) : fieldsOf(draft))
        : createMaterial(this.hass, fieldsOf(draft)));
      this.close();
    } catch (error) {
      this.failure = linking
        ? (this.spoolmanFailure(error) ?? "run.save_failed")
        : "materials.invalid";
    } finally {
      this.saving = false;
    }
  }

  private async delete(material: Material) {
    this.deleting = undefined;
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
    pagerStyles,
    css`
      .star {
        --ha-icon-button-size: 36px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      .star[selected] {
        color: var(--warning-color, #ffa600);
      }
      .group {
        display: flex;
        gap: 6px;
        align-items: center;
      }
      .group input[type="color"] {
        flex: none;
        width: 48px;
        padding: 4px;
        cursor: pointer;
      }
      .group select {
        flex: none;
        width: auto;
      }
      .clear-colour {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-materials-page": MaterialsPage;
  }
}
