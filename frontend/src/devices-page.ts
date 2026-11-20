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
import "./dialog";
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
  if (consumption.source === "per_program") return nothing;
  if (consumption.source !== "estimate")
    return html`<div>
      ${entity(hass, consumption.entity_id, [
        consumption.attribute,
        consumption.source === "power" && running(consumption.running_power),
      ])}
    </div>`;
  const details = [
    running(consumption.running_power),
    consumption.paused_power !== null &&
      t("consumption.paused", { power: format.quantity(consumption.paused_power, "W") }),
  ];
  return html`<div class="muted small">${details.filter(Boolean).join(" · ")}</div>`;
};

/** A price section: fixed per `unit`, or the entity it follows. */
const priceOf = (
  hass: HomeAssistant,
  price: Device["ha_settings"]["price"],
  unit: string,
  t: Localize,
  format: Format,
) =>
  price.source === "fixed"
    ? t("price.fixed", { price: format.unitPrice(price.value), unit })
    : entity(hass, price.entity_id, [price.attribute], (name) =>
        t("price.entity", { entity: name }),
      );

/** The water source with its entity, and the water price unless there's no water. */
const waterOf = (
  hass: HomeAssistant,
  { water, water_price }: Device["ha_settings"],
  t: Localize,
  format: Format,
) =>
  water
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

type Settings = Device["settings"];

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
    const types = [...new Set(devices.map((device) => device.type))];
    return html`
      <ha-button class="new-device fab" @click=${() => navigate(RECONFIGURE)}>
        <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
        ${t("devices.add")}
      </ha-button>
      ${
        devices.length
          ? types.map(
              (type) =>
                html`<section class="device-type" data-type=${type}>
                  <h2>${t(`device_type.${type}`)}</h2>
                  <div class="cards">
                    ${devices
                      .filter((device) => device.type === type)
                      .map((device) => this.renderDevice(device, t))}
                  </div>
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
      <h3>${name}</h3>
      <dl>
        <dt>${t("device.status")}</dt>
        <dd>${entity(this.hass, ha.status.entity_id, [ha.status.attribute])}</dd>
        ${this.renderOptionalInputs(device, t)}
        <dt>${t("device.consumption")}</dt>
        <dd class="consumption">
          <div>${t(`consumption.${ha.consumption.source}`)}</div>
          ${consumptionDetails(this.hass, ha, t, format)}
        </dd>
        <dt>${t("device.price")}</dt>
        <dd class="price">${priceOf(this.hass, ha.price, "kWh", t, format)}</dd>
        ${waterOf(this.hass, ha, t, format)}
      </dl>
      <a class="reconfigure small" href=${RECONFIGURE} @click=${followLink}
        >${t("device.reconfigure")}</a
      >
      <div class="settings">
        <dl>
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
            device.capabilities.includes("doses") && device.capabilities.includes("program")
              ? html`<dt>${t("device.program_rows")}</dt>
                  <dd class="program-rows">
                    ${
                      Object.keys(settings.program_defaults.programs).join(", ") ||
                      html`<span class="muted">${t("device.none")}</span>`
                    }
                  </dd>`
              : nothing
          }
          <dt>${t("device.tags_for_new_runs")}</dt>
          <dd class="new-run-tags">
            ${chips(settings.tags_for_new_runs, "tag", t("device.none"))}
          </dd>
          <dt>${t("device.automatic_templates")}</dt>
          <dd class="automatic-templates">${chips(templates, "template", t("device.none"))}</dd>
        </dl>
        <ha-icon-button
          class="edit"
          .label=${t("device.edit", { device: name })}
          .path=${mdiPencil}
          @click=${() => this.edit(device, settings)}
        ></ha-icon-button>
      </div>
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
                    <span class="muted"
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
    return html`<coinop-dialog
      class="settings-dialog dialog"
      .label=${t("device.settings_title", { device: device.name })}
      .closeLabel=${t("dialog.close")}
      @cancel=${this.close}
    >
      ${
        device.capabilities.includes("material")
          ? this.renderDefaultMaterial(device, draft.default_material, change, t)
          : nothing
      }
      <div class="field new-run-tags">
        <span class="label">${t("device.tags_for_new_runs")}</span>
        <coinop-tag-input
          .hass=${this.hass}
          .tags=${draft.tags_for_new_runs}
          .catalog=${this.tags}
          .label=${t("device.tags_for_new_runs")}
          @tags-change=${(event: CustomEvent<string[]>) =>
            change({ tags_for_new_runs: event.detail })}
        ></coinop-tag-input>
        <p class="muted small">${t("device.tags_hint")}</p>
      </div>
      ${device.capabilities.includes("doses") ? this.renderDoses(device, draft, change, t) : nothing}
      ${this.renderAutomatic(draft.automatic_templates, (ids) => change({ automatic_templates: ids }), t)}
      <p class="muted small ha-settings">
        ${t("device.ha_settings")}
        <a href=${RECONFIGURE} @click=${followLink}>${t("device.reconfigure")}</a>
      </p>
      ${this.failed ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
      <div slot="footer" class="row end">
        <ha-button class="cancel" appearance="plain" @click=${this.close}>
          ${t("device.cancel")}
        </ha-button>
        <ha-button
          class="save"
          ?disabled=${this.saving}
          .loading=${this.saving}
          @click=${() => this.save(device, draft)}
        >
          ${t("device.save")}
        </ha-button>
      </div>
    </coinop-dialog>`;
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
    return html`<div class="field default-material">
      <span class="label">${t("device.default_material")}</span>
      ${
        pickable.length
          ? html`<select
              aria-label=${t("device.default_material")}
              autofocus
              @change=${(event: Event) =>
                change({ default_material: (event.target as HTMLSelectElement).value || null })}
            >
              <option value="" ?selected=${chosen === null}>
                ${t("device.no_default_material")}
              </option>
              ${pickable.map(
                (material) =>
                  html`<option value=${material.id} ?selected=${material.id === chosen}>
                    ${this.materialName(material.id)}
                  </option>`,
              )}
            </select>`
          : html`<p class="no-materials">
              ${t("device.no_materials")}
              <a href="${this.basePath}/materials" @click=${followLink}
                >${t("item.to_materials")}</a
              >
            </p>`
      }
      <p class="muted small">${t("device.default_material_hint")}</p>
    </div>`;
  }

  /** The Dose list and the Program Defaults: the Default row, then a row per Program, a
   * column per Dose. Known Programs without a row are suggested; a value stores their row. */
  private renderDoses(
    { id, capabilities, known_programs, ha_settings }: Device,
    { doses, program_defaults }: Settings,
    change: (changes: Partial<Settings>) => void,
    t: Localize,
  ) {
    const { programs } = program_defaults;
    const perProgram = capabilities.includes("program_consumption");
    const consumed = [
      ...(perProgram ? (["kwh"] as const) : []),
      ...(perProgram && ha_settings.water && ha_settings.water.source !== "none"
        ? (["litres"] as const)
        : []),
    ];
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
    const setAmount = (program: string | null, id: string, value: string) => {
      const row = rowOf(program);
      const others = Object.fromEntries(
        Object.entries(row?.doses ?? {}).filter(([own]) => own !== id),
      );
      const amount = Number(value);
      const valid = value.trim() !== "" && amount > 0;
      if (row || valid)
        setRow(program, { ...row, doses: valid ? { ...others, [id]: amount } : others });
    };
    const setConsumed = (program: string | null, key: (typeof consumed)[number], value: string) => {
      const { doses: amounts, kwh, litres } = rowOf(program) ?? { doses: {} };
      const amount = Number(value);
      const valid = value.trim() !== "" && amount >= 0;
      const next = { kwh, litres, [key]: valid ? amount : undefined };
      if (rowOf(program) || valid)
        setRow(program, {
          doses: amounts,
          ...(next.kwh !== undefined && { kwh: next.kwh }),
          ...(next.litres !== undefined && { litres: next.litres }),
        });
    };
    const suggestions = this.suggestions?.deviceId === id ? this.suggestions.rows : undefined;
    const format = formatter(this.hass);
    const suggestion = (program: string | null, key: (typeof consumed)[number]) => {
      const measured = (program === null ? suggestions?.default : suggestions?.programs[program])?.[
        key
      ];
      if (!measured) return nothing;
      const value = format.quantity(measured.mean, key === "kwh" ? "kWh" : "L");
      return html`<ha-button
        class="suggestion"
        appearance="plain"
        size="small"
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
            <input
              type="number"
              min="0"
              step="any"
              aria-label=${
                program === null
                  ? t(`device.default_${key}`)
                  : t(`device.program_${key}`, { program })
              }
              .value=${String(rowOf(program)?.[key] ?? "")}
              @change=${(event: Event) =>
                setConsumed(program, key, (event.target as HTMLInputElement).value)}
            />
            ${suggestion(program, key)}
          </td>`,
      );
    const amountCells = (program: string | null, label: (dose: string) => string) =>
      doses.map(
        ({ id, material_id }) =>
          html`<td class="num">
            <input
              type="number"
              min="0"
              step="any"
              aria-label=${label(this.doseName(material_id, t))}
              .value=${String(rowOf(program)?.doses[id] ?? "")}
              @change=${(event: Event) =>
                setAmount(program, id, (event.target as HTMLInputElement).value)}
            />
          </td>`,
      );
    const hasPrograms = capabilities.includes("program");
    const programNames = hasPrograms
      ? [...new Set([...known_programs, ...Object.keys(programs)])]
      : [];
    const addable = this.materials.filter((material) => !material.archived);
    return html`<div class="field doses">
        <span class="label">${t("device.doses")}</span>
        <ol class="dose-list">
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
            ? html`<select
                class="add-dose"
                aria-label=${t("device.add_dose")}
                @change=${(event: Event) => {
                  const select = event.target as HTMLSelectElement;
                  if (select.value)
                    setDoses([...doses, { id: newDoseId(), material_id: select.value }]);
                  select.value = "";
                }}
              >
                <option value="">${t("device.add_dose")}</option>
                ${addable.map(
                  (material) => html`<option value=${material.id}>${material.name}</option>`,
                )}
              </select>`
            : html`<p class="no-materials">
                ${t("device.no_materials")}
                <a href="${this.basePath}/materials" @click=${followLink}
                  >${t("item.to_materials")}</a
                >
              </p>`
        }
        <p class="muted small">${t("device.doses_hint")}</p>
      </div>
      ${
        doses.length || consumed.length
          ? html`<div class="field program-defaults">
              <span class="label">${t("device.program_defaults")}</span>
              ${table({
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
                  ? html`<input
                      class="add-program"
                      aria-label=${t("device.add_program")}
                      placeholder=${t("device.add_program")}
                      @change=${(event: Event) => {
                        const input = event.target as HTMLInputElement;
                        const program = input.value.trim();
                        input.value = "";
                        if (program && !programs[program]) setRow(program, { doses: {} });
                      }}
                    />`
                  : nothing
              }
              <p class="muted small">${t("device.program_defaults_hint")}</p>
            </div>`
          : nothing
      }`;
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
    return html`<div class="stock row">
      <select
        aria-label=${t("device.stock_input", { dose })}
        @change=${(event: Event) => {
          const entity_id = (event.target as HTMLSelectElement).value;
          change(entity_id ? { entity_id, attribute: null, unit: null } : undefined);
        }}
      >
        <option value="" ?selected=${!stock}>${t("device.no_stock_input")}</option>
        ${entities.map(
          (id) =>
            html`<option value=${id} ?selected=${id === stock?.entity_id}>
              ${entityName(this.hass, id)}
            </option>`,
        )}
      </select>
      ${
        stock
          ? html`<select
              aria-label=${t("device.stock_attribute", { dose })}
              @change=${(event: Event) => {
                const attribute = (event.target as HTMLSelectElement).value || null;
                const fallback = unit === "ml" ? "mL" : unit;
                change({ ...stock, attribute, unit: attribute ? (stock.unit ?? fallback) : null });
              }}
            >
              <option value="" ?selected=${!stock.attribute}>${t("device.stock_state")}</option>
              ${attributes.map(
                (name) =>
                  html`<option value=${name} ?selected=${name === stock.attribute}>
                    ${name}
                  </option>`,
              )}
            </select>`
          : nothing
      }
      ${
        stock?.attribute
          ? html`<select
              aria-label=${t("device.stock_unit", { dose })}
              @change=${(event: Event) =>
                change({ ...stock, unit: (event.target as HTMLSelectElement).value })}
            >
              ${ATTRIBUTE_UNITS.map(
                (option) =>
                  html`<option value=${option} ?selected=${option === stock.unit}>
                    ${option}
                  </option>`,
              )}
            </select>`
          : nothing
      }
    </div>`;
  }

  private renderAutomatic(chosen: string[], change: (ids: string[]) => void, t: Localize) {
    const picked = chosen.flatMap((id) => this.templates.filter((template) => template.id === id));
    const addable = this.templates.filter((template) => !chosen.includes(template.id));
    return html`<div class="field automatic-templates">
      <span class="label">${t("device.automatic_templates")}</span>
      <div class="row">
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
        ${
          addable.length
            ? html`<select
                aria-label=${t("device.add_template")}
                @change=${(event: Event) => {
                  const select = event.target as HTMLSelectElement;
                  if (select.value) change([...chosen, select.value]);
                  select.value = "";
                }}
              >
                <option value="">${t("device.add_template")}</option>
                ${addable.map(
                  (template) => html`<option value=${template.id}>${template.label}</option>`,
                )}
              </select>`
            : nothing
        }
      </div>
      ${
        this.templates.length
          ? nothing
          : html`<p class="no-templates">
              ${t("device.no_templates")}
              <a href="${this.basePath}/templates" @click=${followLink}
                >${t("device.to_templates")}</a
              >
            </p>`
      }
      <p class="muted small">${t("device.templates_hint")}</p>
    </div>`;
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
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 14px;
      }
      :host([narrow]) .cards {
        grid-template-columns: 1fr;
      }
      .device {
        display: flex;
        flex-direction: column;
      }
      dl {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 6px 12px;
        margin: 12px 0;
      }
      dt {
        color: var(--secondary-text-color);
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
        display: flex;
        align-items: flex-start;
        gap: 4px;
        margin-top: auto;
        padding-top: 4px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      .settings dl {
        flex: 1;
        min-width: 0;
      }
      .settings dd {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
      }
      .settings .edit {
        margin: 4px -8px 0 0;
      }
      .reconfigure {
        align-self: flex-start;
        margin-bottom: 12px;
      }
      .settings .doses ul,
      .dose-list {
        margin: 0;
        padding: 0;
        list-style: none;
      }
      .settings .doses ul {
        display: flex;
        flex-direction: column;
      }
      .dose-list li {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
      }
      .dose-list .stock {
        flex-basis: 100%;
        gap: 6px;
        margin-bottom: 6px;
      }
      .dose-list .stock select {
        min-width: 0;
      }
      .dose-list .dose-name {
        flex: 1;
      }
      .dose-list ha-icon-button {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 18px;
      }
      .program-defaults td input {
        width: 6em;
        text-align: right;
      }
      .program-defaults .suggestion {
        display: block;
        margin-inline-start: auto;
        white-space: nowrap;
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
      .add-program {
        align-self: flex-start;
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
      .field {
        display: flex;
        flex-direction: column;
        gap: 3px;
      }
      .field .label {
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      .field p {
        margin: 0;
      }
      .ha-settings {
        margin: 4px 0 0;
      }
      .error {
        color: var(--error-color, #db4437);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-devices-page": DevicesPage;
  }
}
