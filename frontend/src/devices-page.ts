// The Devices tab: a card per Device with its HA-side settings, which only the
// Device's reconfigure flow in HA changes, and WattBill's own settings, saved at once.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { updateDeviceSettings, type Device } from "./api";
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
    return html`<div class="card device">
      <h3>${name}</h3>
      <dl>
        <dt>${t("device.status")}</dt>
        <dd>${input(ha.status, t)}</dd>
        <dt>${t("device.job")}</dt>
        <dd>${input(ha.job, t)}</dd>
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
      <div class="new-run-tags">
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
      ${this.failed === id ? html`<p class="error small">${t("run.save_failed")}</p>` : nothing}
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
      .new-run-tags {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      }
      h4 {
        margin: 0 0 6px;
        font-weight: 500;
      }
      .new-run-tags p {
        margin: 6px 0 0;
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
