// The Devices tab: a card per Device with its HA-side settings, which only the
// Device's reconfigure flow in HA changes, and WattBill's own settings, saved at once.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { updateDeviceSettings, type Device, type LineItemTemplate, type Material } from "./api";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";
import "./tag-input";

const RECONFIGURE = "/config/integrations/integration/wattbill";

const input = (
  { entity_id, attribute }: { entity_id: string | null; attribute: string | null },
  t: Localize,
) => (entity_id ? [entity_id, attribute].filter(Boolean).join(" · ") : t("device.not_used"));

const consumptionDetails = (
  { consumption }: Device["ha_settings"],
  t: Localize,
  format: Format,
) => {
  const running = (power: number | null) =>
    power !== null && t("consumption.running", { power: format.quantity(power, "W") });
  const details =
    consumption.source === "estimate"
      ? [
          running(consumption.running_power),
          consumption.paused_power !== null &&
            t("consumption.paused", { power: format.quantity(consumption.paused_power, "W") }),
        ]
      : [
          input(consumption, t),
          consumption.source === "power" && running(consumption.running_power),
        ];
  return details.filter(Boolean).join(" · ");
};

@customElement("wattbill-devices-page")
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
  @property({ type: Boolean, reflect: true }) narrow = false;

  /** Settings saved since the Devices were loaded, by Device id. */
  @state() private saved = new Map<string, Device["settings"]>();
  /** The Device whose last change could not be saved. */
  @state() private failed?: string;

  private async save(deviceId: string, changes: Partial<Device["settings"]>) {
    this.failed = undefined;
    try {
      const settings = await updateDeviceSettings(this.hass, deviceId, changes);
      this.saved = new Map(this.saved).set(deviceId, settings);
    } catch {
      this.failed = deviceId;
    }
  }

  override render() {
    const t = localize(this.hass);
    if (this.devices === null) return html`<p class="muted">${t("devices.error")}</p>`;
    if (!this.devices) return html`<p class="muted">${t("devices.loading")}</p>`;
    return html`
      <h2>${t("devices.title")}</h2>
      ${
        this.devices.length
          ? html`<div class="cards">
              ${this.devices.map((device) => this.renderDevice(device, t))}
            </div>`
          : html`<p class="muted">${t("devices.empty")}</p>`
      }
    `;
  }

  private renderDevice({ id, name, ha_settings: ha, settings }: Device, t: Localize) {
    const format = formatter(this.hass);
    const current = this.saved.get(id) ?? settings;
    // A default Material no longer in the catalogue counts as none, as in the backend.
    const defaults = this.materials.filter(
      (material) => !material.archived || material.id === current.default_material,
    );
    const defaultMaterial = defaults.some(({ id }) => id === current.default_material)
      ? current.default_material
      : null;
    return html`<div class="card device">
      <h3>${name}</h3>
      <dl>
        <dt>${t("device.status")}</dt>
        <dd>${input(ha.status, t)}</dd>
        <dt>${t("device.job")}</dt>
        <dd>${input(ha.job, t)}</dd>
        <dt>${t("device.material")}</dt>
        <dd class="material-used">
          ${
            ha.job.material
              ? [input(ha.job.material, t), ha.job.material.unit].filter(Boolean).join(" · ")
              : t("device.not_used")
          }
        </dd>
        <dt>${t("device.thumbnail")}</dt>
        <dd>${ha.images?.thumbnail ?? t("device.not_used")}</dd>
        <dt>${t("device.camera")}</dt>
        <dd>
          ${
            ha.images?.camera
              ? html`<div>${ha.images.camera}</div>
                  <div class="muted small">
                    ${t(ha.images.snapshot ? "device.snapshot_on" : "device.snapshot_off")}
                  </div>`
              : t("device.not_used")
          }
        </dd>
        <dt>${t("device.consumption")}</dt>
        <dd class="consumption">
          <div>${t(`consumption.${ha.consumption.source}`)}</div>
          <div class="muted small">${consumptionDetails(ha, t, format)}</div>
        </dd>
        <dt>${t("device.price")}</dt>
        <dd>
          ${
            ha.price.source === "fixed"
              ? t("price.fixed", { price: format.unitPrice(ha.price.value) })
              : t("price.entity", { entity: input(ha.price, t) })
          }
        </dd>
      </dl>
      <p class="muted small">${t("device.ha_settings")}</p>
      <a href=${RECONFIGURE} @click=${followLink}>${t("device.reconfigure")}</a>
      <div class="setting default-material">
        <h4>${t("device.default_material")}</h4>
        <select
          aria-label=${t("device.default_material")}
          @change=${(event: Event) =>
            this.save(id, {
              default_material: (event.target as HTMLSelectElement).value || null,
            })}
        >
          <option value="" ?selected=${defaultMaterial === null}>
            ${t("device.no_default_material")}
          </option>
          ${defaults.map(
            (material) =>
              html`<option value=${material.id} ?selected=${material.id === defaultMaterial}>
                ${
                  material.archived
                    ? t("materials.archived_name", { name: material.name })
                    : material.name
                }
              </option>`,
          )}
        </select>
        <p class="muted small">${t("device.default_material_hint")}</p>
      </div>
      <div class="setting new-run-tags">
        <h4>${t("device.tags_for_new_runs")}</h4>
        <wattbill-tag-input
          .hass=${this.hass}
          .tags=${current.tags_for_new_runs}
          .catalog=${this.tags}
          .label=${t("device.tags_for_new_runs")}
          @tags-change=${(event: CustomEvent<string[]>) =>
            this.save(id, { tags_for_new_runs: event.detail })}
        ></wattbill-tag-input>
        <p class="muted small">${t("device.tags_hint")}</p>
      </div>
      ${this.renderAutomatic(id, current.automatic_templates, t)}
      ${this.failed === id ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
    </div>`;
  }

  private renderAutomatic(deviceId: string, chosen: string[], t: Localize) {
    const picked = chosen.flatMap((id) => this.templates.filter((template) => template.id === id));
    const save = (ids: string[]) => this.save(deviceId, { automatic_templates: ids });
    return html`<div class="automatic-templates">
      <h4>${t("device.automatic_templates")}</h4>
      <div class="row">
        ${picked.map(
          ({ id, label }) =>
            html`<span class="template-chip"
              ><span class="template-name">${label}</span
              ><button
                class="remove"
                aria-label=${t("device.remove_template", { template: label })}
                title=${t("device.remove_template", { template: label })}
                @click=${() => save(chosen.filter((own) => own !== id))}
              >
                ×
              </button></span
            >`,
        )}
        <select
          aria-label=${t("device.add_template")}
          @change=${(event: Event) => {
            const select = event.target as HTMLSelectElement;
            if (select.value) void save([...chosen, select.value]);
            select.value = "";
          }}
        >
          <option value="">${t("device.add_template")}</option>
          ${this.templates
            .filter((template) => !chosen.includes(template.id))
            .map((template) => html`<option value=${template.id}>${template.label}</option>`)}
        </select>
      </div>
      <p class="muted small">${t("device.templates_hint")}</p>
    </div>`;
  }

  static override styles = [
    shared,
    css`
      h2 {
        margin: 8px 0 12px;
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 14px;
      }
      :host([narrow]) .cards {
        grid-template-columns: 1fr;
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
      p {
        margin: 0 0 8px;
      }
      .setting,
      .automatic-templates {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      h4 {
        margin: 0 0 6px;
        font-weight: 500;
      }
      .setting p,
      .automatic-templates p {
        margin: 6px 0 0;
      }
      .template-chip {
        display: inline-flex;
        align-items: center;
        font-size: 12px;
        padding: 1px 8px;
        border-radius: 10px;
        background: color-mix(in srgb, var(--wattbill-other) 14%, transparent);
      }
      .template-chip .remove {
        border: 0;
        background: none;
        color: inherit;
        padding: 0 0 0 4px;
        cursor: pointer;
        font: inherit;
      }
      select {
        font: inherit;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 3px 6px;
      }
      .default-material select {
        width: 100%;
        padding: 6px 8px;
        box-sizing: border-box;
      }
      .error {
        color: var(--error-color, #db4437);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-devices-page": DevicesPage;
  }
}
