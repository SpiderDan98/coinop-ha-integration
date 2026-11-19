// The Devices tab: a card per Device with its HA-side settings, which only the
// Device's reconfigure flow in HA changes.
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Device } from "./api";
import { formatter, type Format } from "./format";
import { followLink, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { shared } from "./styles";

const RECONFIGURE = "/config/integrations/integration/wattbill";

const input = (
  { entity_id, attribute }: { entity_id: string | null; attribute: string | null },
  t: Localize,
) => (entity_id ? [entity_id, attribute].filter(Boolean).join(" · ") : t("device.not_used"));

const watts = (power: number, format: Format) => format.quantity(power, "W");

@customElement("wattbill-devices-page")
export class DevicesPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Undefined while loading; null when loading failed. */
  @property({ attribute: false }) devices?: Device[] | null;
  @property({ type: Boolean, reflect: true }) narrow = false;

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

  private renderDevice({ name, ha_settings: ha }: Device, t: Localize) {
    const format = formatter(this.hass);
    const { consumption } = ha;
    return html`<div class="card device">
      <h3>${name}</h3>
      <dl>
        <dt>${t("device.status")}</dt>
        <dd>${input(ha.status, t)}</dd>
        <dt>${t("device.job")}</dt>
        <dd>${input(ha.job, t)}</dd>
        <dt>${t("device.consumption")}</dt>
        <dd>
          <div>${t(`consumption.${consumption.source}`)}</div>
          <div class="muted small">
            ${[
              t("consumption.running", { power: watts(consumption.running_power, format) }),
              consumption.paused_power !== null &&
                t("consumption.paused", { power: watts(consumption.paused_power, format) }),
            ]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </dd>
        <dt>${t("device.price")}</dt>
        <dd>${t(`price.${ha.price.source}`, { price: format.unitPrice(ha.price.value) })}</dd>
      </dl>
      <p class="muted small">${t("device.ha_settings")}</p>
      <a href=${RECONFIGURE} @click=${followLink}>${t("device.reconfigure")}</a>
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-devices-page": DevicesPage;
  }
}
