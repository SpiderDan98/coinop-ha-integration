// The Devices tab: a section per Device Type with a card per Device. A card shows the
// HA-side settings, which only the Device's reconfigure flow in HA changes, and a summary
// of Coin-op's own settings, edited in a dialog. Devices are added in HA too.
import { mdiClose, mdiPencil, mdiPlus } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { updateDeviceSettings, type Device, type LineItemTemplate, type Material } from "./api";
import "./dialog";
import { formatter, type Format } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";
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
        ${this.renderOptionalInputs(ha, t)}
        <dt>${t("device.consumption")}</dt>
        <dd class="consumption">
          <div>${t(`consumption.${ha.consumption.source}`)}</div>
          ${consumptionDetails(this.hass, ha, t, format)}
        </dd>
        <dt>${t("device.price")}</dt>
        <dd class="price">
          ${
            ha.price.source === "fixed"
              ? t("price.fixed", { price: format.unitPrice(ha.price.value) })
              : entity(this.hass, ha.price.entity_id, [ha.price.attribute], (name) =>
                  t("price.entity", { entity: name }),
                )
          }
        </dd>
      </dl>
      <a class="reconfigure small" href=${RECONFIGURE} @click=${followLink}
        >${t("device.reconfigure")}</a
      >
      <div class="settings">
        <dl>
          <dt>${t("device.default_material")}</dt>
          <dd class="default-material">
            ${
              this.materialName(settings.default_material) ??
              html`<span class="muted">${t("device.no_default_material")}</span>`
            }
          </dd>
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
          @click=${() => {
            this.failed = false;
            this.editing = { device, draft: settings };
          }}
        ></ha-icon-button>
      </div>
    </div>`;
  }

  /** The Device Inputs it has, then the ones it doesn't use in one line. */
  private renderOptionalInputs({ job, images }: Device["ha_settings"], t: Localize) {
    const hass = this.hass;
    const rows = [
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
    const unused = rows.filter(([, , shown]) => !shown).map(([, label]) => label);
    return html`${rows.map(([name, label, shown]) =>
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
    // The Device's archived default stays pickable; other archived Materials don't.
    const original = this.settingsOf(device).default_material;
    const pickable = this.materials.filter(
      (material) => !material.archived || material.id === original,
    );
    return html`<coinop-dialog
      class="settings-dialog dialog"
      .label=${t("device.settings_title", { device: device.name })}
      .closeLabel=${t("dialog.close")}
      @cancel=${this.close}
    >
      <div class="field default-material">
        <span class="label">${t("device.default_material")}</span>
        ${
          pickable.length
            ? html`<select
                aria-label=${t("device.default_material")}
                autofocus
                @change=${(event: Event) =>
                  change({ default_material: (event.target as HTMLSelectElement).value || null })}
              >
                <option value="" ?selected=${draft.default_material === null}>
                  ${t("device.no_default_material")}
                </option>
                ${pickable.map(
                  (material) =>
                    html`<option
                      value=${material.id}
                      ?selected=${material.id === draft.default_material}
                    >
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
      </div>
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

  private close() {
    this.editing = undefined;
  }

  static override styles = [
    shared,
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
