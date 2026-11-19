// "+ Manual Run": a Run made by hand for a print WattBill did not see. Pre-fills the
// Device's Tags for new Runs, opens the new Run's page once created and fires `close`.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { OUTCOMES, createRun, type Device, type Outcome } from "./api";
import { formatter } from "./format";
import { navigate, type HomeAssistant } from "./hass";
import { localize } from "./localize";
import { shared } from "./styles";
import "./tag-input";

@customElement("wattbill-manual-run-dialog")
export class ManualRunDialog extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) devices: Device[] = [];
  /** Every Tag there is, for suggestions. */
  @property({ attribute: false }) tags: string[] = [];
  @property({ attribute: false }) basePath = "";

  @state() private deviceId?: string;
  @state() private name = "";
  @state() private started = "";
  @state() private ended = "";
  @state() private outcome: Outcome = "completed";
  /** Undefined until the user changes them: the Device's Tags for new Runs. */
  @state() private runTags?: string[];
  @state() private saving = false;
  @state() private failed = false;

  private get device() {
    return this.devices.find((device) => device.id === this.deviceId) ?? this.devices[0];
  }

  private get times() {
    const format = formatter(this.hass);
    const [started, ended] = [format.fromInput(this.started), format.fromInput(this.ended)];
    return started && ended && Date.parse(ended) > Date.parse(started)
      ? { started, ended }
      : undefined;
  }

  override render() {
    const t = localize(this.hass);
    const device = this.device;
    const tags = this.runTags ?? device?.settings.tags_for_new_runs ?? [];
    const input = (event: Event) => (event.target as HTMLInputElement).value;
    return html`<div class="scrim">
      <div class="manual-dialog card" role="dialog" aria-modal="true">
        <h2>${t("manual.title")}</h2>
        <p class="muted small">${t("manual.hint")}</p>
        <label
          >${t("run.device")}<select
            name="device"
            @change=${(event: Event) => {
              this.deviceId = input(event);
              this.runTags = undefined;
            }}
          >
            ${this.devices.map(
              ({ id, name }) =>
                html`<option value=${id} ?selected=${id === device?.id}>${name}</option>`,
            )}
          </select></label
        >
        <label
          >${t("run.name")}<input
            name="name"
            .value=${this.name}
            placeholder=${t("run.untitled")}
            @input=${(event: Event) => (this.name = input(event))}
        /></label>
        <div class="row times">
          <label
            >${t("run.started")}<input
              type="datetime-local"
              name="started"
              .value=${this.started}
              @input=${(event: Event) => (this.started = input(event))}
          /></label>
          <label
            >${t("run.ended")}<input
              type="datetime-local"
              name="ended"
              .value=${this.ended}
              @input=${(event: Event) => (this.ended = input(event))}
          /></label>
        </div>
        <label
          >${t("run.outcome")}<select
            name="outcome"
            @change=${(event: Event) => (this.outcome = input(event) as Outcome)}
          >
            ${OUTCOMES.map(
              (outcome) =>
                html`<option value=${outcome} ?selected=${outcome === this.outcome}>
                  ${t(`outcome.${outcome}`)}
                </option>`,
            )}
          </select></label
        >
        <div class="label">
          ${t("run.tags")}
          <wattbill-tag-input
            .hass=${this.hass}
            .tags=${tags}
            .catalog=${this.tags}
            .label=${t("run.tags")}
            @tags-change=${(event: CustomEvent<string[]>) => (this.runTags = event.detail)}
          ></wattbill-tag-input>
        </div>
        ${this.failed ? html`<p class="error small">${t("manual.failed")}</p>` : nothing}
        <div class="row end">
          <button class="btn cancel" @click=${this.close}>${t("manual.cancel")}</button>
          <button
            class="btn create"
            ?disabled=${!device || !this.times || this.saving}
            @click=${() => this.create(tags)}
          >
            ${t("manual.create")}
          </button>
        </div>
      </div>
    </div>`;
  }

  private async create(tags: string[]) {
    const device = this.device;
    const times = this.times;
    if (!device || !times) return;
    this.saving = true;
    this.failed = false;
    try {
      const run = await createRun(this.hass, {
        device_id: device.id,
        name: this.name.trim() || null,
        ...times,
        outcome: this.outcome,
        tags,
      });
      navigate(`${this.basePath}/run/${encodeURIComponent(run.id)}`);
      this.close();
    } catch {
      this.failed = true;
    } finally {
      this.saving = false;
    }
  }

  private close() {
    this.dispatchEvent(new Event("close"));
  }

  static override styles = [
    shared,
    css`
      .scrim {
        position: fixed;
        inset: 0;
        z-index: 5;
        display: grid;
        place-items: center;
        padding: 16px;
        background: rgba(0, 0, 0, 0.4);
      }
      .manual-dialog {
        width: min(480px, 100%);
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .manual-dialog p {
        margin: 0;
      }
      .times > label {
        flex: 1 1 180px;
      }
      .end {
        justify-content: flex-end;
      }
      .error {
        color: var(--error-color, #db4437);
      }
      label,
      .label {
        display: flex;
        flex-direction: column;
        gap: 3px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      input,
      select {
        font: inherit;
        font-size: 14px;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 6px 8px;
        min-width: 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-manual-run-dialog": ManualRunDialog;
  }
}
