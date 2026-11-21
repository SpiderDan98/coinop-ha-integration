// Dev container only (the `coinop_dev` integration): switches Coin-op's data to a
// Preset of test data. Loading replaces the hub entry, so the page loads afresh after.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "./hass";
import { localize } from "./localize";
import "./dialog";
import { shared } from "./styles";

export const DEV_INTEGRATION = "coinop_dev";

const listScenarios = (hass: HomeAssistant) =>
  hass.callWS<{
    presets: { name: string; title: string; description: string }[];
    preset: string | null;
  }>({ type: `${DEV_INTEGRATION}/scenarios` });

@customElement("coinop-dev-scenarios-dialog")
export class DevScenariosDialog extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) basePath = "";

  @state() private list?: Awaited<ReturnType<typeof listScenarios>>;
  @state() private loading?: string;
  @state() private failed = false;

  override connectedCallback() {
    super.connectedCallback();
    listScenarios(this.hass).then(
      (list) => (this.list = list),
      () => (this.failed = true),
    );
  }

  override render() {
    const t = localize(this.hass);
    return html`<coinop-dialog
      class="dialog"
      .label=${t("dev.title")}
      .closeLabel=${t("dialog.close")}
      @cancel=${() => !this.loading && this.dispatchEvent(new Event("close"))}
    >
      <p class="muted small">${t("dev.hint")}</p>
      ${this.failed ? html`<p class="error small">${t("dev.failed")}</p>` : nothing}
      <ul>
        ${this.list?.presets.map(
          ({ name, title, description }) =>
            html`<li>
              <div>
                <strong>${title}</strong>
                ${
                  name === this.list?.preset
                    ? html`<span class="muted small">· ${t("dev.current")}</span>`
                    : nothing
                }
                <div class="muted small">${description}</div>
              </div>
              <ha-button
                appearance=${name === this.list?.preset ? "plain" : "filled"}
                ?disabled=${!!this.loading}
                ?loading=${this.loading === name}
                @click=${() => this.load(name)}
                >${this.loading === name ? t("dev.loading") : t("dev.load")}</ha-button
              >
            </li>`,
        )}
      </ul>
    </coinop-dialog>`;
  }

  private async load(preset: string) {
    this.loading = preset;
    this.failed = false;
    try {
      await this.hass.callWS({
        type: "call_service",
        domain: DEV_INTEGRATION,
        service: "load",
        service_data: { preset },
      });
    } catch {
      this.loading = undefined;
      this.failed = true;
      return;
    }
    location.assign(this.basePath);
  }

  static override styles = [
    shared,
    css`
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      .error {
        color: var(--error-color, #db4437);
      }
      li {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 10px 0;
        border-top: 1px solid var(--divider-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-dev-scenarios-dialog": DevScenariosDialog;
  }
}
