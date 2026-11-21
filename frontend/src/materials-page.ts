// The Materials tab: the global catalogue, listed read-only and edited in a dialog. The
// list itself comes from the panel's catalogue subscription, so every open panel shows
// each change.
// Opening the tab reads Spoolman, which creates, refreshes and archives the Materials from
// it and tells which own Materials could be merged into its Filaments.
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
  deleteMaterial,
  getMaterialTypes,
  mergeSpoolman,
  readSpoolman,
  restoreMaterial,
  updateMaterial,
  MATERIAL_FORMS,
  PACK_UNITS,
  type Material,
  type MaterialFields,
  type MaterialForm,
  type MaterialType,
  type PackUnit,
  type SpoolmanState,
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
const USUAL_UNIT = {
  filament: "g",
  resin: "ml",
  detergent: "ml",
  fabric_softener: "ml",
  laundry_additive: "g",
  dishwasher_product: "pcs",
  beverage_ingredient: "g",
  other: null,
} satisfies Record<MaterialForm, PackUnit | null>;
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
});

type Draft = ReturnType<typeof blankDraft>;

const fromSpoolman = (material: Material) => material.price.source === "spoolman";

/** A Material from Spoolman is copied at the price Spoolman has for it now, else at the
 * last price read. */
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
  ...(price.source === "fixed"
    ? {
        pack_price: String(price.pack_price),
        pack_size: String(price.pack_size),
        pack_unit: price.pack_unit,
      }
    : price.pack_price !== null && price.pack_weight !== null
      ? { pack_price: String(price.pack_price), pack_size: String(price.pack_weight) }
      : { pack_price: price.per_gram === null ? "" : String(+(price.per_gram * 1000).toFixed(2)) }),
});

/** A copy leaves its type's default with the original and is an own Material. */
const copyOf = (material: Material): Draft => ({ ...draftOf(material), default_for_type: false });

const ORIGINS = ["all", "spoolman", "own"] as const;
type Origin = (typeof ORIGINS)[number];

const COLOUR = /^#[0-9a-f]{6}$/i;

const hasBuiltInTypes = (form: MaterialForm) => form !== "other";
const byPiece = (draft: Draft) => draft.pack_unit === "pcs";
const hasDiameter = (draft: Draft) => draft.form === "filament" && !byPiece(draft);

/** The fields of a draft that the backend would refuse, so they can be marked. */
function problems(draft: Draft) {
  const positive = (value: string) => value.trim() !== "" && Number(value) > 0;
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
  @state() private spoolman?: SpoolmanState;
  @state() private origin: Origin = "all";
  /** The merge dialog's pick per own Material: a Filament id, or "" to keep it own. */
  @state() private picks?: Record<string, string>;
  @state() private mergeFailure?: Key;
  private typesRequested = false;
  private readonly pages = {
    active: new Pagination(this),
    archived: new Pagination(this),
  };

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("hass") && this.hass && !this.typesRequested) {
      this.typesRequested = true;
      getMaterialTypes(this.hass).then(
        (types) => (this.types = types),
        () => (this.typesRequested = false),
      );
      this.readSpoolman();
    }
  }

  private readSpoolman() {
    readSpoolman(this.hass).then(
      (spoolman) => (this.spoolman = spoolman),
      () => undefined,
    );
  }

  private get connected() {
    return !!this.spoolman && this.spoolman.status !== "not_configured";
  }

  override render() {
    const t = localize(this.hass);
    if (!this.materials) return html`<p class="muted">${t("materials.loading")}</p>`;
    const format = formatter(this.hass);
    const origin = this.connected ? this.origin : "all";
    const shown = this.materials.filter(
      (material) => origin === "all" || fromSpoolman(material) === (origin === "spoolman"),
    );
    const active = shown.filter((material) => !material.archived);
    const archived = shown.filter((material) => material.archived);
    return html`
      <ha-button class="new-material fab" @click=${() => this.open()}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("materials.new")}
      </ha-button>
      ${this.renderSpoolmanNotices(t)}
      ${this.notice ? html`<p class="notice">${this.notice}</p>` : nothing}
      ${this.connected ? this.renderOrigins(t) : nothing}
      ${
        this.materials.length
          ? html`
              ${
                active.length
                  ? this.renderTable(active, "active", this.pages.active, t, format)
                  : html`<p class="muted none-active">
                      ${t(origin === "all" ? "materials.all_archived" : "materials.none_shown")}
                    </p>`
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
      ${this.draft ? this.renderDialog(this.draft, t, format) : nothing}
      ${this.deleting ? this.renderDeleteDialog(this.deleting, t) : nothing}
      ${this.picks ? this.renderMergeDialog(this.picks, t) : nothing}
    `;
  }

  private renderSpoolmanNotices(t: Localize) {
    if (this.spoolman?.status === "unreachable")
      return html`<p class="notice spoolman-notice">${t("spoolman.unreachable")}</p>`;
    const count = this.spoolman?.merges.length ?? 0;
    if (!count) return nothing;
    return html`<p class="notice merge-notice row">
      <span>
        ${
          count === 1
            ? t("spoolman.merge_notice_one")
            : t("spoolman.merge_notice", { count: count })
        }
      </span>
      <ha-button class="small" appearance="plain" @click=${() => this.openMerge()}>
        ${t("spoolman.review")}
      </ha-button>
    </p>`;
  }

  private renderOrigins(t: Localize) {
    return html`<div class="origin" role="group" aria-label=${t("materials.origin")}>
      ${ORIGINS.map(
        (origin) =>
          html`<button
            aria-pressed=${this.origin === origin ? "true" : "false"}
            @click=${() => {
              this.origin = origin;
              this.pages.active.reset();
              this.pages.archived.reset();
            }}
          >
            ${t(`materials.origin_${origin}`)}
          </button>`,
      )}
    </div>`;
  }

  private properties(material: Material) {
    const number = (value: number) => value.toLocaleString(this.hass.language);
    return material.density === null
      ? nothing
      : `${number(material.density)} g/cm³${
          material.diameter === null ? "" : ` · ⌀ ${number(material.diameter)} mm`
        }`;
  }

  private pack({ price }: Material, t: Localize, format: Format) {
    if (price.source === "fixed")
      return `${format.money(price.pack_price)} / ${format.quantity(price.pack_size, price.pack_unit)}`;
    return html`<span class="badge">${t("spoolman.badge")}</span> ${
        price.pack_price === null || price.pack_weight === null
          ? html`<span class="no-price">${t("spoolman.no_price")}</span>`
          : `${format.money(price.pack_price)} / ${
              price.pack_weight >= 1000
                ? format.quantity(price.pack_weight / 1000, "kg")
                : format.quantity(price.pack_weight, "g")
            }`
      }`;
  }

  private renderTable(
    materials: Material[],
    name: string,
    pages: Pagination,
    t: Localize,
    format: Format,
  ) {
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
            <td class="small">${this.properties(material)}</td>
            <td class="small">${this.pack(material, t, format)}</td>
            <td class="num">
              ${
                material.price.source === "spoolman" && material.price.per_gram === null
                  ? "—"
                  : material.price_per_piece === null
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
    // A Material from Spoolman goes when its Filament does: it can only be archived.
    const remove = fromSpoolman(material)
      ? nothing
      : action("delete", t("materials.delete"), mdiDelete, () => {
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

  private renderDialog(draft: Draft, t: Localize, format: Format) {
    const set = (changes: Partial<Draft>) => (this.draft = { ...draft, ...changes });
    const edited = this.materials?.find((material) => material.id === this.editing);
    if (edited && fromSpoolman(edited)) return this.renderSyncedDialog(edited, draft, t, format);
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
      ${details} ${this.renderDefault(draft, t)}`,
    });
  }

  private renderDefault(draft: Draft, t: Localize) {
    return checkbox({
      name: "default_for_type",
      label: t("materials.default_for_type"),
      checked: draft.default_for_type,
      onChange: (default_for_type) => (this.draft = { ...draft, default_for_type }),
    });
  }

  /** Spoolman supplies everything of its Materials but their default. */
  private renderSyncedDialog(material: Material, draft: Draft, t: Localize, format: Format) {
    const detail = (label: string, value: unknown) =>
      html`<dt class="muted small">${label}</dt>
        <dd>${value}</dd>`;
    return formDialog({
      t,
      title: t("materials.edit_title"),
      name: "material-dialog",
      busy: this.saving,
      error: this.failure && t(this.failure),
      onCancel: () => this.close(),
      onSubmit: () => this.save(draft),
      content: html`<p class="strong synced-name">${material.name}</p>
        <dl class="synced">
          ${detail(t("materials.form_type"), `${t(`form.${material.form}`)} · ${material.type}`)}
          ${detail(t("materials.properties"), this.properties(material))}
          ${material.vendor ? detail(t("materials.vendor_name"), material.vendor) : nothing}
          ${
            material.colour
              ? detail(
                  t("materials.colour_name"),
                  html`<span class="row">
                    <span class="swatch" style="background: ${material.colour}"></span>
                    ${material.colour}
                  </span>`,
                )
              : nothing
          }
          ${detail(t("materials.pack"), this.pack(material, t, format))}
        </dl>
        ${this.renderDefault(draft, t)}
        <p class="muted small">${t("materials.synced")}</p>`,
    });
  }

  /** One picker per own Material with Filaments waiting; a Filament picked for one is
   * taken for the others. */
  private renderMergeDialog(picks: Record<string, string>, t: Localize) {
    const merges = this.spoolman?.merges ?? [];
    const taken = (materialId: string, filamentId: string) =>
      Object.entries(picks).some(([other, pick]) => other !== materialId && pick === filamentId);
    return formDialog({
      t,
      title: t("spoolman.merge_title"),
      name: "merge-dialog",
      submit: t("spoolman.merge_save"),
      busy: this.saving,
      error: this.mergeFailure && t(this.mergeFailure),
      onCancel: () => (this.picks = undefined),
      onSubmit: () => this.merge(picks),
      content: html`<p class="muted small">${t("spoolman.merge_intro")}</p>
        ${merges.map(({ material_id, candidates }) => {
          const material = this.materials?.find((candidate) => candidate.id === material_id);
          return field(
            material ? `${material.name} · ${material.type}` : material_id,
            select({
              name: `merge-${material_id}`,
              value: picks[material_id] ?? "",
              options: [
                ...candidates.map(
                  (filament) =>
                    [
                      String(filament.id),
                      filament.name,
                      taken(material_id, String(filament.id)),
                    ] as const,
                ),
                ["", t("spoolman.keep_own")],
              ],
              onChange: (pick) => (this.picks = { ...picks, [material_id]: pick }),
            }),
          );
        })}`,
    });
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

  /** Each own Material starts at its best match not picked for an earlier one. */
  private openMerge() {
    const picks: Record<string, string> = {};
    for (const { material_id, candidates } of this.spoolman?.merges ?? []) {
      const free = candidates.find(
        (filament) => !Object.values(picks).includes(String(filament.id)),
      );
      picks[material_id] = free ? String(free.id) : "";
    }
    this.mergeFailure = undefined;
    this.picks = picks;
  }

  private async merge(picks: Record<string, string>) {
    this.saving = true;
    this.mergeFailure = undefined;
    try {
      this.spoolman = await mergeSpoolman(
        this.hass,
        Object.entries(picks).map(([material_id, pick]) => ({
          material_id,
          filament_id: pick ? Number(pick) : null,
        })),
      );
      this.picks = undefined;
    } catch (error) {
      const code = (error as { code?: string }).code;
      this.mergeFailure =
        code === "not_allowed"
          ? "spoolman.merge_stale"
          : code === "spoolman_unreachable"
            ? "spoolman.unreachable"
            : "run.save_failed";
      this.readSpoolman();
    } finally {
      this.saving = false;
    }
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
    const edited = this.materials?.find((material) => material.id === this.editing);
    const synced = !!edited && fromSpoolman(edited);
    this.checked = true;
    this.failure = undefined;
    if (!synced && problems(draft).size) return;
    this.saving = true;
    try {
      await (this.editing
        ? updateMaterial(
            this.hass,
            this.editing,
            synced ? { default_for_type: draft.default_for_type } : fieldsOf(draft),
          )
        : createMaterial(this.hass, fieldsOf(draft)));
      this.close();
    } catch {
      this.failure = synced ? "run.save_failed" : "materials.invalid";
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
      .origin {
        display: inline-flex;
        margin-bottom: 12px;
        border: 1px solid var(--outline-color, var(--divider-color, rgba(0, 0, 0, 0.12)));
        border-radius: 10px;
        overflow: hidden;
      }
      .origin button {
        padding: 6px 12px;
        border: 0;
        cursor: pointer;
        font: inherit;
        color: var(--secondary-text-color);
        background: var(--card-background-color, #fff);
      }
      .origin button[aria-pressed="true"] {
        color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent);
      }
      .origin button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }
      .badge {
        display: inline-block;
        padding: 0 6px;
        border-radius: 6px;
        font-size: 0.85em;
        color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent);
      }
      .no-price {
        color: var(--warning-color, #ffa600);
      }
      .merge-notice {
        justify-content: space-between;
        gap: 8px;
      }
      .synced-name {
        margin: 0 0 8px;
      }
      .synced {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 6px 16px;
        margin: 0 0 12px;
      }
      .synced dd {
        margin: 0;
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
