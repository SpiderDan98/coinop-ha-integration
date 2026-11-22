// The Devices tab: a section per Device Type with a card per Device. A card shows the
// HA-side settings, which only the Device's reconfigure flow in HA changes, and a summary
// of Coin-op's own settings, edited in a dialog. Devices are added in HA too.
import { mdiArrowDown, mdiArrowUp, mdiClose, mdiPencil, mdiPlus } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  getMeasuredSuggestions,
  updateDeviceSettings,
  type Device,
  type LineItemTemplate,
  type Material,
} from "./api";
import { formDialog } from "./dialog";
import { field, input, numberInput, select } from "./fields";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";
import { table, tableStyles } from "./table";
import "./tag-input";

export const RECONFIGURE = "/config/integrations/integration/coinop";

const entityName = (hass: HomeAssistant, entityId: string) =>
  hass.states[entityId]?.attributes.friendly_name ?? entityId;

/** One line: the entity's name, its id as tooltip. `title` wraps the name, e.g. "From {entity}". */
const entity = (
  hass: HomeAssistant,
  entityId: string,
  details: unknown[] = [],
  title = (name: string) => name,
) => {
  const extra = details.filter(Boolean).join(" · ");
  return html`<span class="entity" title=${entityId}>${title(entityName(hass, entityId))}</span>${
      extra ? html` <span class="muted small">· ${extra}</span>` : nothing
    }`;
};

const consumptionDetails = (
  hass: HomeAssistant,
  { consumption }: Device["ha_settings"],
  t: Localize,
  format: Format,
) => {
  const running = (power: number | null) =>
    power !== null && t("consumption.running", { power: format.quantity(power, "W") });
  if (consumption.source === "estimate") {
    const details = [
      running(consumption.running_power),
      consumption.paused_power !== null &&
        t("consumption.paused", { power: format.quantity(consumption.paused_power, "W") }),
    ];
    return html`<div class="muted small">${details.filter(Boolean).join(" · ")}</div>`;
  }
  if (!("entity_id" in consumption)) return nothing;
  return html`<div>
    ${entity(hass, consumption.entity_id, [
      consumption.attribute,
      consumption.source === "power" && running(consumption.running_power),
    ])}
  </div>`;
};

/** A price section: fixed per `unit`, or the entity it follows. */
const priceOf = (
  hass: HomeAssistant,
  price: NonNullable<Device["ha_settings"]["price"]>,
  unit: string,
  t: Localize,
  format: Format,
) =>
  price.source === "fixed"
    ? t("price.fixed", { price: format.unitPrice(price.value), unit })
    : entity(hass, price.entity_id, [price.attribute], (name) =>
        t("price.entity", { entity: name }),
      );

/** A water section stored for a Device without the water Capability is no water source. */
const waterSource = ({ capabilities, ha_settings }: Device) =>
  capabilities.includes("water") ? ha_settings.water : undefined;

/** The water source with its entity, and the water price unless there's no water. */
const waterOf = (hass: HomeAssistant, device: Device, t: Localize, format: Format) => {
  const water = waterSource(device);
  const { water_price } = device.ha_settings;
  return water
    ? html`<dt>${t("device.water")}</dt>
        <dd class="water">
          <div>${t(`water.${water.source}`)}</div>
          ${
            "entity_id" in water
              ? html`<div>${entity(hass, water.entity_id, [water.attribute])}</div>`
              : nothing
          }
        </dd>
        ${
          water.source !== "none" && water_price
            ? html`<dt>${t("device.water_price")}</dt>
                <dd class="water-price">${priceOf(hass, water_price, "m³", t, format)}</dd>`
            : nothing
        }`
    : nothing;
};

type Settings = Device["settings"];
const COVER_KINDS = ["thumbnail", "snapshot", "upload"] as const satisfies Settings["cover_kind"][];

/** The kinds of image its Runs get; no choice without an automatic one. */
const coverKinds = ({ ha_settings: { images } }: Device) => {
  const has = {
    thumbnail: Boolean(images?.thumbnail),
    snapshot: Boolean(images?.camera && images.snapshot),
    upload: true,
  };
  return has.thumbnail || has.snapshot ? COVER_KINDS.filter((kind) => has[kind]) : [];
};

/** The unit a Dose of the Material counts in; Spoolman prices by weight. */
const unitOf = (material?: Material) =>
  material?.price.source === "fixed" ? material.price.pack_unit : "g";

type Stock = NonNullable<Settings["doses"][number]["stock"]>;

// HA's mass and volume units, as its unit converters know them.
const STOCK_UNITS = new Set(
  ["μg", "mg", "g", "kg", "oz", "lb", "st"].concat([
    "mL",
    "L",
    "fl. oz.",
    "gal",
    "m³",
    "ft³",
    "CCF",
    "MCF",
  ]),
);
const ATTRIBUTE_UNITS = ["g", "kg", "mL", "L"];

/** Unique enough per Device; `crypto.randomUUID` needs a secure context HA may not have. */
const newDoseId = () => `dose-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;

const chips = (names: string[], kind: "tag" | "template", none: string) =>
  names.length
    ? names.map(
        (name) => html`<span class="${kind}-chip"><span class="${kind}-name">${name}</span></span>`,
      )
    : html`<span class="muted">${none}</span>`;

@customElement("coinop-devices-page")
export class DevicesPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined while loading; null when loading failed. */
  @property({ attribute: false }) devices?: Device[] | null;
  /** Every Tag there is, for suggestions. */
  @property({ attribute: false }) tags: string[] = [];
  /** The Materials catalogue, archived ones included. */
  @property({ attribute: false }) materials: Material[] = [];
  /** Every Line Item Template there is, to pick automatic ones from. */
  @property({ attribute: false }) templates: LineItemTemplate[] = [];
  /** Where the panel lives, for links to its other tabs. */
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** Settings saved since the Devices were loaded, by Device id. */
  @state() private saved = new Map<string, Device["settings"]>();
  /** The Device whose settings the dialog edits, and the settings as edited so far. */
  @state() private editing?: { device: Device; draft: Device["settings"] };
  /** The measured suggestions for the Device being edited, once they arrive. */
  @state() private suggestions?: {
    deviceId: string;
    rows: Awaited<ReturnType<typeof getMeasuredSuggestions>>;
  };
  @state() private saving = false;
  @state() private failed = false;

  /** As last saved; a default Material no longer in the catalogue counts as none, as in the backend. */
  private settingsOf({ id, settings }: Device) {
    const current = this.saved.get(id) ?? settings;
    const known = this.materials.some((material) => material.id === current.default_material);
    return { ...current, default_material: known ? current.default_material : null };
  }

  private materialName(id: string | null) {
    const material = this.materials.find((candidate) => candidate.id === id);
    if (!material) return undefined;
    const t = localize(this.hass);
    return material.archived
      ? t("materials.archived_name", { name: material.name })
      : material.name;
  }

  private doseName(materialId: string, t: Localize) {
    return this.materialName(materialId) ?? t("device.material_gone");
  }

  private material(id: string) {
    return this.materials.find((material) => material.id === id);
  }

  override render() {
    const t = localize(this.hass);
    if (this.devices === null) return html`<p class="muted">${t("devices.error")}</p>`;
    if (!this.devices) return html`<p class="muted">${t("devices.loading")}</p>`;
    const devices = this.devices;
    // A Type Name may read like a Device Type's key or heading and is still its own group.
    const groupOf = ({ type, type_name }: Device) => JSON.stringify([type, type_name]);
    const groups = [...new Set(devices.map(groupOf))].map((group) =>
      devices.filter((device) => groupOf(device) === group),
    );
    return html`
      <ha-button class="new-device fab" @click=${() => navigate(RECONFIGURE)}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("devices.add")}
      </ha-button>
      ${
        devices.length
          ? groups.map(
              (group) =>
                html`<section class="device-type" data-type=${group[0].type}>
                  <h2>${group[0].type_name ?? t(`device_type.${group[0].type}`)}</h2>
                  <div class="cards">${group.map((device) => this.renderDevice(device, t))}</div>
                </section>`,
            )
          : html`<p class="muted">${t("devices.empty")}</p>`
      }
      ${this.editing ? this.renderDialog(this.editing.device, this.editing.draft, t) : nothing}
    `;
  }

  private renderDevice(device: Device, t: Localize) {
    const { name, ha_settings: ha } = device;
    const format = formatter(this.hass);
    const settings = this.settingsOf(device);
    const templates = settings.automatic_templates.flatMap((id) =>
      this.templates.filter((template) => template.id === id).map(({ label }) => label),
    );
    return html`<div class="card device">
      <div class="head">
        <h3 class="ellipsis">${name}</h3>
        <ha-icon-button
          class="edit"
          .label=${t("device.edit", { device: name })}
          .path=${mdiPencil}
          @click=${() => this.edit(device, settings)}
        ></ha-icon-button>
      </div>
      <dl>
        <dt>${t("device.status")}</dt>
        <dd>${entity(this.hass, ha.status.entity_id, [ha.status.attribute])}</dd>
        ${this.renderOptionalInputs(device, t)}
        <dt>${t("device.consumption")}</dt>
        <dd class="consumption">
          <div>${t(`consumption.${ha.consumption.source}`)}</div>
          ${consumptionDetails(this.hass, ha, t, format)}
        </dd>
        ${
          ha.consumption.source !== "none" && ha.price
            ? html`<dt>${t("device.price")}</dt>
                <dd class="price">${priceOf(this.hass, ha.price, "kWh", t, format)}</dd>`
            : nothing
        }
        ${waterOf(this.hass, device, t, format)}
      </dl>
      <a class="reconfigure small" href=${RECONFIGURE} @click=${followLink}
        >${t("device.reconfigure")}</a
      >
      <dl class="settings">
        ${
          device.capabilities.includes("material")
            ? html`<dt>${t("device.default_material")}</dt>
                <dd class="default-material">
                  ${
                    this.materialName(settings.default_material) ??
                    html`<span class="muted">${t("device.no_default_material")}</span>`
                  }
                </dd>`
            : nothing
        }
        ${device.capabilities.includes("doses") ? this.renderDoseSummary(settings, t, format) : nothing}
        ${
          device.capabilities.includes("program")
            ? html`<dt>${t("device.program_rows")}</dt>
                <dd class="program-rows">
                  ${
                    Object.keys(settings.program_defaults.programs).join(", ") ||
                    html`<span class="muted">${t("device.none")}</span>`
                  }
                </dd>`
            : nothing
        }
        ${
          coverKinds(device).length
            ? html`<dt>${t("device.cover_kind")}</dt>
                <dd class="cover-kind">${t(`cover_kind.${settings.cover_kind}`)}</dd>`
            : nothing
        }
        <dt>${t("device.tags_for_new_runs")}</dt>
        <dd class="new-run-tags">${chips(settings.tags_for_new_runs, "tag", t("device.none"))}</dd>
        <dt>${t("device.automatic_templates")}</dt>
        <dd class="automatic-templates">${chips(templates, "template", t("device.none"))}</dd>
      </dl>
    </div>`;
  }

  /** Each Dose with its Default row amount. */
  private renderDoseSummary({ doses, program_defaults }: Settings, t: Localize, format: Format) {
    const amounts = program_defaults.default.doses;
    return html`<dt>${t("device.doses")}</dt>
      <dd class="doses">
        ${
          doses.length
            ? html`<ul>
                ${doses.map(({ id, material_id, stock }) => {
                  const amount = amounts[id];
                  return html`<li>
                    <span class="dose-name">${this.doseName(material_id, t)}</span>
                    <span class="muted amount"
                      >${
                        amount === undefined
                          ? t("device.not_dosed")
                          : format.quantity(amount, unitOf(this.material(material_id)))
                      }</span
                    >
                    ${
                      stock
                        ? html`<span class="muted small stock"
                            >·
                            ${entity(this.hass, stock.entity_id, [], (name) =>
                              t("device.measured_by", { entity: name }),
                            )}</span
                          >`
                        : nothing
                    }
                  </li>`;
                })}
              </ul>`
            : html`<span class="muted">${t("device.none")}</span>`
        }
      </dd>`;
  }

  /** Of the Device Inputs its Device Type offers, the ones it has, then the ones it
   * doesn't use in one line. */
  private renderOptionalInputs({ capabilities, ha_settings }: Device, t: Localize) {
    const hass = this.hass;
    const { job = { entity_id: null, attribute: null }, images, program } = ha_settings;
    const rows = [
      [
        "program",
        t("device.program"),
        program?.entity_id && entity(hass, program.entity_id, [program.attribute]),
      ],
      ["job", t("device.job"), job.entity_id && entity(hass, job.entity_id, [job.attribute])],
      [
        "material-used",
        t("device.material"),
        job.material &&
          entity(hass, job.material.entity_id, [job.material.attribute, job.material.unit]),
      ],
      [
        "slots",
        t("device.slots"),
        job.slots?.length &&
          html`<ol>
              ${job.slots.map((slot) => html`<li>${entity(hass, slot)}</li>`)}
            </ol>
            ${
              job.colour_attribute
                ? html`<div class="muted small">
                    ${t("device.slot_colour", { attribute: job.colour_attribute })}
                  </div>`
                : nothing
            }
            ${
              job.loaded_slot
                ? html`<div class="loaded-slot">
                    ${entity(hass, job.loaded_slot, [], (name) =>
                      t("device.loaded_slot", { entity: name }),
                    )}
                  </div>`
                : nothing
            }`,
      ],
      ["thumbnail", t("device.thumbnail"), images?.thumbnail && entity(hass, images.thumbnail)],
      [
        "camera",
        t("device.camera"),
        images?.camera &&
          entity(hass, images.camera, [
            t(images.snapshot ? "device.snapshot_on" : "device.snapshot_off"),
          ]),
      ],
    ] as const;
    const needs = { program: "program", thumbnail: "images", camera: "images" } as const;
    const offered = rows.filter(([name]) =>
      capabilities.includes(name in needs ? needs[name as keyof typeof needs] : "job"),
    );
    const unused = offered.filter(([, , shown]) => !shown).map(([, label]) => label);
    return html`${offered.map(([name, label, shown]) =>
      shown
        ? html`<dt>${label}</dt>
            <dd class=${name}>${shown}</dd>`
        : nothing,
    )}
    ${
      unused.length
        ? html`<dt>${t("device.not_used")}</dt>
            <dd class="unused muted">${unused.join(", ")}</dd>`
        : nothing
    }`;
  }

  private renderDialog(device: Device, draft: Device["settings"], t: Localize) {
    const change = (changes: Partial<Device["settings"]>) =>
      (this.editing = { device, draft: { ...draft, ...changes } });
    const dosed = device.capabilities.includes("doses");
    const withProgramDefaults = dosed || device.capabilities.includes("program");
    return formDialog({
      t,
      title: t("device.settings_title", { device: device.name }),
      name: `settings-dialog ${withProgramDefaults ? "wide" : ""}`,
      busy: this.saving,
      error: this.failed && t("run.save_failed"),
      onCancel: () => this.close(),
      onSubmit: () => this.save(device, draft),
      content: html`${
          device.capabilities.includes("material")
            ? this.renderDefaultMaterial(device, draft.default_material, change, t)
            : nothing
        }
        ${
          coverKinds(device).length
            ? field(
                t("device.cover_kind"),
                select({
                  value: draft.cover_kind,
                  options: coverKinds(device).map(
                    (kind) => [kind, t(`cover_kind.${kind}`)] as const,
                  ),
                  onChange: (kind) => change({ cover_kind: kind as Settings["cover_kind"] }),
                }),
                { name: "cover-kind", hint: t("device.cover_kind_hint") },
              )
            : nothing
        }
        ${field(
          t("device.tags_for_new_runs"),
          html`<coinop-tag-input
            .hass=${this.hass}
            .tags=${draft.tags_for_new_runs}
            .catalog=${this.tags}
            .label=${t("device.tags_for_new_runs")}
            @tags-change=${(event: CustomEvent<string[]>) =>
              change({ tags_for_new_runs: event.detail })}
          ></coinop-tag-input>`,
          { name: "new-run-tags", group: true, hint: t("device.tags_hint") },
        )}
        ${dosed ? this.renderDoses(draft, change, t) : nothing}
        ${withProgramDefaults ? this.renderProgramDefaults(device, draft, change, t) : nothing}
        ${this.renderAutomatic(
          draft.automatic_templates,
          (ids) => change({ automatic_templates: ids }),
          t,
        )}
        <p class="muted small ha-settings">
          ${t("device.ha_settings")}
          <a href=${RECONFIGURE} @click=${followLink}>${t("device.reconfigure")}</a>
        </p>`,
    });
  }

  private renderDefaultMaterial(
    device: Device,
    chosen: string | null,
    change: (changes: Partial<Device["settings"]>) => void,
    t: Localize,
  ) {
    // The Device's archived default stays pickable; other archived Materials don't.
    const original = this.settingsOf(device).default_material;
    const pickable = this.materials.filter(
      (material) => !material.archived || material.id === original,
    );
    return field(
      t("device.default_material"),
      pickable.length
        ? select({
            autofocus: true,
            value: chosen,
            options: [
              ["", t("device.no_default_material")],
              ...pickable.map(({ id }) => [id, this.materialName(id)] as const),
            ],
            onChange: (id) => change({ default_material: id || null }),
          })
        : this.noMaterials(t),
      {
        name: "default-material",
        group: !pickable.length,
        hint: t("device.default_material_hint"),
      },
    );
  }

  private toMaterials(t: Localize) {
    return html`<a href="${this.basePath}/materials" @click=${followLink}
      >${t("item.to_materials")}</a
    >`;
  }

  private noMaterials(t: Localize) {
    return html`<p class="no-materials">${t("device.no_materials")} ${this.toMaterials(t)}</p>`;
  }

  /** The Dose list. A removed Dose takes its amounts in the Program Defaults with it. */
  private renderDoses(
    { doses, program_defaults }: Settings,
    change: (changes: Partial<Settings>) => void,
    t: Localize,
  ) {
    const { programs } = program_defaults;
    const setDoses = (next: Settings["doses"]) => {
      const kept = new Set(next.map(({ id }) => id));
      const prune = ({ doses: amounts, ...rest }: Settings["program_defaults"]["default"]) => ({
        ...rest,
        doses: Object.fromEntries(Object.entries(amounts).filter(([id]) => kept.has(id))),
      });
      change({
        doses: next,
        program_defaults: {
          default: prune(program_defaults.default),
          programs: Object.fromEntries(
            Object.entries(programs).map(([name, row]) => [name, prune(row)]),
          ),
        },
      });
    };
    const move = (index: number, by: number) => {
      const next = [...doses];
      const [dose] = next.splice(index, 1);
      if (dose) next.splice(index + by, 0, dose);
      setDoses(next);
    };
    const addable = this.materials.filter((material) => !material.archived);
    return field(
      t("device.doses"),
      html`<ol class="dose-list">
          ${doses.map((dose, index) => {
            const name = this.doseName(dose.material_id, t);
            const unit = unitOf(this.material(dose.material_id));
            const setStock = (stock?: Stock) => {
              const { id, material_id } = dose;
              setDoses(
                doses.map((other, at) =>
                  at === index ? { id, material_id, ...(stock && { stock }) } : other,
                ),
              );
            };
            return html`<li>
              <span class="dose-name">${name}</span>
              <span class="muted small">${unit}</span>
              <ha-icon-button
                class="up"
                .label=${t("device.move_dose_up", { dose: name })}
                .path=${mdiArrowUp}
                ?disabled=${index === 0}
                @click=${() => move(index, -1)}
              ></ha-icon-button>
              <ha-icon-button
                class="down"
                .label=${t("device.move_dose_down", { dose: name })}
                .path=${mdiArrowDown}
                ?disabled=${index === doses.length - 1}
                @click=${() => move(index, 1)}
              ></ha-icon-button>
              <ha-icon-button
                class="remove"
                .label=${t("device.remove_dose", { dose: name })}
                .path=${mdiClose}
                @click=${() => setDoses(doses.filter((_, other) => other !== index))}
              ></ha-icon-button>
              ${unit === "pcs" ? nothing : this.renderStock(dose.stock, name, unit, setStock, t)}
            </li>`;
          })}
        </ol>
        ${
          addable.length
            ? select({
                label: t("device.add_dose"),
                options: [
                  ["", t("device.add_dose")],
                  ...addable.map(({ id, name }) => [id, name] as const),
                ],
                onChange: (picked, control) => {
                  if (picked) setDoses([...doses, { id: newDoseId(), material_id: picked }]);
                  control.value = "";
                },
              })
            : this.noMaterials(t)
        }`,
      {
        name: "doses",
        group: true,
        hint: addable.length
          ? html`${t("device.doses_hint")} ${this.toMaterials(t)}`
          : t("device.doses_hint"),
      },
    );
  }

  /** The Program Defaults: the Default row, then a row per Program; a kWh and a litres
   * column where they can come per Program and the Device has a source for them, and a
   * column per Dose of a Device with Doses. Stored values of a hidden column are kept.
   * Known Programs without a row are suggested; a value stores their row. */
  private renderProgramDefaults(
    device: Device,
    { doses: doseList, program_defaults }: Settings,
    change: (changes: Partial<Settings>) => void,
    t: Localize,
  ) {
    const { id, capabilities, known_programs } = device;
    const { programs } = program_defaults;
    const dosed = capabilities.includes("doses");
    // As with water: a Dose list stored without the Capability adds no columns.
    const doses = dosed ? doseList : [];
    const perProgram = capabilities.includes("program_consumption");
    const water = waterSource(device);
    const consumed = [
      ...(perProgram && device.ha_settings.consumption.source !== "none" ? (["kwh"] as const) : []),
      ...(perProgram && water && water.source !== "none" ? (["litres"] as const) : []),
    ];
    if (!doses.length && !consumed.length) return nothing;
    /** `program` null is the Default row. */
    const rowOf = (program: string | null) =>
      program === null ? program_defaults.default : programs[program];
    const setRow = (program: string | null, row: Settings["program_defaults"]["default"]) =>
      change({
        program_defaults:
          program === null
            ? { ...program_defaults, default: row }
            : { ...program_defaults, programs: { ...programs, [program]: row } },
      });
    const setPrograms = (next: typeof programs) =>
      change({ program_defaults: { ...program_defaults, programs: next } });
    /** Writes a cell's value, or clears it unless `valid`; a suggested row is stored
     * only once it gets a valid value. */
    const setCell = (
      program: string | null,
      value: string,
      valid: (amount: number) => boolean,
      write: (row: Settings["program_defaults"]["default"], amount?: number) => typeof row,
    ) => {
      const row = rowOf(program);
      const amount = value.trim() === "" ? NaN : Number(value);
      if (row || valid(amount))
        setRow(program, write(row ?? { doses: {} }, valid(amount) ? amount : undefined));
    };
    const setAmount = (program: string | null, id: string, value: string) =>
      setCell(
        program,
        value,
        (amount) => amount > 0,
        (row, amount) => {
          const doses = Object.fromEntries(Object.entries(row.doses).filter(([own]) => own !== id));
          return { ...row, doses: amount === undefined ? doses : { ...doses, [id]: amount } };
        },
      );
    const setConsumed = (program: string | null, key: (typeof consumed)[number], value: string) =>
      setCell(
        program,
        value,
        (amount) => amount >= 0,
        ({ doses, ...row }, amount) => {
          const { kwh, litres } =
            key === "kwh" ? { ...row, kwh: amount } : { ...row, litres: amount };
          return {
            doses,
            ...(kwh !== undefined && { kwh }),
            ...(litres !== undefined && { litres }),
          };
        },
      );
    const suggestions = this.suggestions?.deviceId === id ? this.suggestions.rows : undefined;
    const format = formatter(this.hass);
    const suggestion = (program: string | null, key: (typeof consumed)[number]) => {
      const measured = (program === null ? suggestions?.default : suggestions?.programs[program])?.[
        key
      ];
      if (!measured) return nothing;
      const value = format.quantity(measured.mean, key === "kwh" ? "kWh" : "L");
      return html`<ha-button
        class="suggestion small"
        appearance="plain"
        title=${t("device.apply_suggestion")}
        @click=${() => setConsumed(program, key, String(measured.mean))}
      >
        ${
          measured.runs === 1
            ? t("device.suggestion_one", { value })
            : t("device.suggestion", { value, count: measured.runs })
        }
      </ha-button>`;
    };
    const consumedCells = (program: string | null) =>
      consumed.map(
        (key) =>
          html`<td class="num">
            ${numberInput({
              label:
                program === null
                  ? t(`device.default_${key}`)
                  : t(`device.program_${key}`, { program }),
              value: String(rowOf(program)?.[key] ?? ""),
              onChange: (value) => setConsumed(program, key, value),
            })}
            ${suggestion(program, key)}
          </td>`,
      );
    const amountCells = (program: string | null, label: (dose: string) => string) =>
      doses.map(
        ({ id, material_id }) =>
          html`<td class="num">
            ${numberInput({
              label: label(this.doseName(material_id, t)),
              value: String(rowOf(program)?.doses[id] ?? ""),
              onChange: (value) => setAmount(program, id, value),
            })}
          </td>`,
      );
    const kwh = consumed.includes("kwh");
    const litres = consumed.includes("litres");
    const columnsHint = () => {
      if (!dosed) return t("device.program_defaults_hint_undosed");
      if (kwh && litres) return t("device.program_defaults_hint");
      if (kwh) return t("device.program_defaults_hint_unwatered");
      if (litres) return t("device.program_defaults_hint_unpowered");
      return t("device.program_defaults_hint_doses");
    };
    const hasPrograms = capabilities.includes("program");
    const rowsHint = t(
      hasPrograms
        ? "device.program_defaults_hint_rows"
        : "device.program_defaults_hint_default_row",
    );
    const programNames = hasPrograms
      ? [...new Set([...known_programs, ...Object.keys(programs)])]
      : [];
    return field(
      t("device.program_defaults"),
      html`${table({
        columns: [
          { label: t("device.program") },
          ...consumed.map((key) => ({ label: t(`device.${key}_column`), num: true })),
          ...doses.map(({ material_id }) => ({
            label: `${this.doseName(material_id, t)} (${unitOf(this.material(material_id))})`,
            num: true,
          })),
        ],
        rows: html`<tr>
            <td>${t("device.default_row")}</td>
            ${consumedCells(null)}
            ${amountCells(null, (dose) => t("device.default_amount", { dose }))}
          </tr>
          ${programNames.map(
            (program) =>
              html`<tr class="program-row ${programs[program] ? "" : "suggested"}">
                <td>
                  <span class="program-name">${program}</span>
                  ${
                    programs[program]
                      ? html`<ha-icon-button
                          class="remove"
                          .label=${t("device.remove_program", { program })}
                          .path=${mdiClose}
                          @click=${() =>
                            setPrograms(
                              Object.fromEntries(
                                Object.entries(programs).filter(([own]) => own !== program),
                              ),
                            )}
                        ></ha-icon-button>`
                      : html`<span class="muted small">${t("device.suggested")}</span>`
                  }
                </td>
                ${consumedCells(program)}
                ${amountCells(program, (dose) => t("device.program_amount", { dose, program }))}
              </tr>`,
          )}`,
      })}
      ${
        hasPrograms
          ? input({
              label: t("device.add_program"),
              placeholder: t("device.add_program"),
              onChange: (value, control) => {
                const program = value.trim();
                control.value = "";
                if (program && !programs[program]) setRow(program, { doses: {} });
              },
            })
          : nothing
      }`,
      {
        name: "program-defaults",
        group: true,
        hint: `${columnsHint()} ${rowsHint}`,
      },
    );
  }

  /** A native select over the mass and volume entities (ADR 0007), an optional attribute and its unit. */
  private renderStock(
    stock: Stock | undefined,
    dose: string,
    unit: string,
    change: (stock?: Stock) => void,
    t: Localize,
  ) {
    const states = this.hass.states;
    const entities = Object.keys(states)
      .filter(
        (id) =>
          id === stock?.entity_id ||
          STOCK_UNITS.has(states[id]?.attributes.unit_of_measurement ?? ""),
      )
      .sort((a, b) => entityName(this.hass, a).localeCompare(entityName(this.hass, b)));
    const attributes = Object.entries(states[stock?.entity_id ?? ""]?.attributes ?? {})
      .filter(([name, value]) => name === stock?.attribute || Number.isFinite(value))
      .map(([name]) => name);
    return html`<div class="stock field-row">
      ${select({
        label: t("device.stock_input", { dose }),
        value: stock?.entity_id,
        options: [
          ["", t("device.no_stock_input")],
          ...entities.map((id) => [id, entityName(this.hass, id)] as const),
        ],
        onChange: (entity_id) =>
          change(entity_id ? { entity_id, attribute: null, unit: null } : undefined),
      })}
      ${
        stock
          ? select({
              label: t("device.stock_attribute", { dose }),
              value: stock.attribute,
              options: [
                ["", t("device.stock_state")],
                ...attributes.map((name) => [name, name] as const),
              ],
              onChange: (name) => {
                const attribute = name || null;
                const fallback = unit === "ml" ? "mL" : unit;
                change({ ...stock, attribute, unit: attribute ? (stock.unit ?? fallback) : null });
              },
            })
          : nothing
      }
      ${
        stock?.attribute
          ? select({
              label: t("device.stock_unit", { dose }),
              value: stock.unit,
              options: ATTRIBUTE_UNITS.map((option) => [option, option]),
              onChange: (option) => change({ ...stock, unit: option }),
            })
          : nothing
      }
    </div>`;
  }

  private renderAutomatic(chosen: string[], change: (ids: string[]) => void, t: Localize) {
    const picked = chosen.flatMap((id) => this.templates.filter((template) => template.id === id));
    const addable = this.templates.filter((template) => !chosen.includes(template.id));
    return field(
      t("device.automatic_templates"),
      html`${
        picked.length
          ? html`<div class="row">
              ${picked.map(
                ({ id, label }) =>
                  html`<span class="template-chip"
                    ><span class="template-name">${label}</span
                    ><ha-icon-button
                      class="remove"
                      .label=${t("device.remove_template", { template: label })}
                      .path=${mdiClose}
                      @click=${() => change(chosen.filter((own) => own !== id))}
                    ></ha-icon-button
                  ></span>`,
              )}
            </div>`
          : nothing
      }
      ${
        addable.length
          ? select({
              label: t("device.add_template"),
              options: [
                ["", t("device.add_template")],
                ...addable.map(({ id, label }) => [id, label] as const),
              ],
              onChange: (picked, control) => {
                if (picked) change([...chosen, picked]);
                control.value = "";
              },
            })
          : nothing
      }
      ${
        this.templates.length
          ? nothing
          : html`<p class="no-templates">
              ${t("device.no_templates")}
              <a href="${this.basePath}/templates" @click=${followLink}
                >${t("device.to_templates")}</a
              >
            </p>`
      }`,
      { name: "automatic-templates", group: true, hint: t("device.templates_hint") },
    );
  }

  /** Sends only what changed: re-sending an archived default Material would be refused. */
  private async save(device: Device, draft: Device["settings"]) {
    const before = this.settingsOf(device);
    const changes = Object.fromEntries(
      Object.entries(draft).filter(
        ([key, value]) =>
          JSON.stringify(value) !== JSON.stringify(before[key as keyof typeof before]),
      ),
    );
    if (!Object.keys(changes).length) return this.close();
    this.saving = true;
    this.failed = false;
    try {
      const settings = await updateDeviceSettings(this.hass, device.id, changes);
      this.saved = new Map(this.saved).set(device.id, settings);
      this.close();
    } catch {
      this.failed = true;
    } finally {
      this.saving = false;
    }
  }

  private async edit(device: Device, settings: Settings) {
    this.failed = false;
    this.editing = { device, draft: settings };
    this.suggestions = undefined;
    if (!device.capabilities.includes("program_consumption")) return;
    try {
      const rows = await getMeasuredSuggestions(this.hass, device.id);
      if (this.editing?.device.id === device.id) this.suggestions = { deviceId: device.id, rows };
    } catch {
      // Without suggestions the table is still complete.
    }
  }

  private close() {
    this.editing = undefined;
  }

  static override styles = [
    shared,
    tableStyles,
    css`
      .device-type + .device-type {
        margin-top: 24px;
      }
      .device-type h2 {
        margin-bottom: 12px;
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
        gap: 16px;
      }
      :host([narrow]) .cards {
        grid-template-columns: 1fr;
      }
      .device {
        display: flex;
        flex-direction: column;
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
      /* One label column for both lists, so their values line up. */
      dl {
        display: grid;
        grid-template-columns: minmax(0, 140px) minmax(0, 1fr);
        gap: 6px 12px;
        margin: 12px 0;
      }
      dt {
        color: var(--secondary-text-color);
        overflow-wrap: break-word;
        hyphens: auto;
      }
      dd {
        margin: 0;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .slots ol {
        display: flex;
        flex-wrap: wrap;
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .slots li:not(:last-child)::after {
        content: ",\\00a0";
      }
      .settings {
        margin: auto 0 0;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .settings dd {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
      }
      .reconfigure {
        align-self: flex-start;
        margin-bottom: 12px;
      }
      coinop-dialog.wide {
        --coinop-dialog-width: 800px;
      }
      .settings .doses ul,
      .dose-list {
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .settings .doses ul {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .settings .doses .amount {
        white-space: nowrap;
      }
      .dose-list li {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
        padding: 4px 0;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .doses > select {
        margin-top: 12px;
      }
      .dose-list .stock {
        flex-basis: 100%;
        gap: 6px;
        margin-bottom: 6px;
      }
      .program-defaults .table {
        margin-bottom: 6px;
      }
      .dose-list .dose-name {
        flex: 1;
      }
      .dose-list ha-icon-button {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 18px;
      }
      .program-defaults th {
        white-space: normal;
        vertical-align: bottom;
      }
      .program-defaults td input {
        width: 6em;
        text-align: right;
      }
      /* ha-button wraps its label whatever white-space says, so it gets the label's width. */
      .program-defaults .suggestion {
        display: block;
        width: max-content;
        margin-inline-start: auto;
      }
      .program-row td:first-child {
        white-space: nowrap;
      }
      .program-row .remove {
        --ha-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        vertical-align: middle;
      }
      .program-row.suggested .program-name {
        color: var(--secondary-text-color);
      }
      .template-chip {
        display: inline-flex;
        align-items: center;
        font-size: 12px;
        padding: 1px 8px;
        border-radius: 10px;
        background: color-mix(in srgb, var(--coinop-other) 14%, transparent);
      }
      .template-chip .remove {
        --ha-icon-button-size: 24px;
        --mdc-icon-size: 16px;
        margin-inline-end: -6px;
      }
      .ha-settings {
        margin: 4px 0 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-devices-page": DevicesPage;
  }
}
