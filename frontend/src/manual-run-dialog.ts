// "Manual Run": a Run made by hand for a print Coin-op did not see. Pre-fills the
// Device's Tags for new Runs, opens the new Run's page once created and fires `close`.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { OUTCOMES, createRun, type Device, type Outcome } from "./api";
import { formatter } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { RECONFIGURE } from "./devices-page";
import "./dialog";
import { shared } from "./styles";
import "./tag-input";

@customElement("coinop-manual-run-dialog")
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

  override connectedCallback() {
    super.connectedCallback();
    this.ended ||= formatter(this.hass).toInput(new Date().toISOString());
  }

  /** The times entered, or why they are no Run's times yet. */
  private get times() {
    const format = formatter(this.hass);
    const [started, ended] = [format.fromInput(this.started), format.fromInput(this.ended)];
    if (!started || !ended) return { problem: undefined };
    const now = Date.now();
    if (Date.parse(started) > now || Date.parse(ended) > now) return { problem: "future" as const };
    if (Date.parse(ended) <= Date.parse(started)) return { problem: "order" as const };
    return { started, ended };
  }

  override render() {
    const t = localize(this.hass);
    if (!this.devices.length) return this.renderNoDevices(t);
    const device = this.device;
    const times = this.times;
    const now = formatter(this.hass).toInput(new Date().toISOString());
    const tags = this.runTags ?? device?.settings.tags_for_new_runs ?? [];
    const input = (event: Event) => (event.target as HTMLInputElement).value;
    return html`<coinop-dialog
      class="manual-dialog dialog"
      .label=${t("manual.title")}
      .closeLabel=${t("dialog.close")}
      @cancel=${this.close}
    >
      <p class="muted small">${t("manual.hint")}</p>
      ${
        this.devices.length > 1
          ? html`<label
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
            >`
          : nothing
      }
      <label
        >${t("run.name")}<input
          name="name"
          autofocus
          .value=${this.name}
          placeholder=${t("run.untitled")}
          @input=${(event: Event) => (this.name = input(event))}
      /></label>
      <div class="row times">
        <label
          >${t("run.started")}<input
            type="datetime-local"
            name="started"
            max=${now}
            .value=${this.started}
            @input=${(event: Event) => (this.started = input(event))}
        /></label>
        <label
          >${t("run.ended")}<input
            type="datetime-local"
            name="ended"
            max=${now}
            aria-invalid=${times.problem ? "true" : "false"}
            .value=${this.ended}
            @input=${(event: Event) => (this.ended = input(event))}
        /></label>
      </div>
      ${
        times.problem
          ? html`<p class="error small times-problem">${t(`manual.${times.problem}`)}</p>`
          : nothing
      }
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
        <coinop-tag-input
          .hass=${this.hass}
          .tags=${tags}
          .catalog=${this.tags}
          .label=${t("run.tags")}
          @tags-change=${(event: CustomEvent<string[]>) => (this.runTags = event.detail)}
        ></coinop-tag-input>
      </div>
      ${this.failed ? html`<p class="error small">${t("manual.failed")}</p>` : nothing}
      <div slot="footer" class="row end">
        <ha-button class="cancel" appearance="plain" @click=${this.close}>
          ${t("manual.cancel")}
        </ha-button>
        <ha-button
          class="create"
          ?disabled=${!device || !times.started || this.saving}
          .loading=${this.saving}
          @click=${() => this.create(tags)}
        >
          ${t("manual.create")}
        </ha-button>
      </div>
    </coinop-dialog>`;
  }

  private renderNoDevices(t: Localize) {
    return html`<coinop-dialog
      class="manual-dialog dialog"
      .label=${t("manual.title")}
      .closeLabel=${t("dialog.close")}
      @cancel=${this.close}
    >
      <p class="no-devices">${t("devices.empty")}</p>
      <a
        href=${RECONFIGURE}
        @click=${(event: MouseEvent) => {
          followLink(event);
          this.close();
        }}
        >${t("manual.add_device")}</a
      >
      <div slot="footer" class="row end">
        <ha-button class="cancel" appearance="plain" autofocus @click=${this.close}>
          ${t("manual.close")}
        </ha-button>
      </div>
    </coinop-dialog>`;
  }

  private async create(tags: string[]) {
    const device = this.device;
    const { started, ended } = this.times;
    if (!device || !started || !ended) return;
    this.saving = true;
    this.failed = false;
    try {
      const run = await createRun(this.hass, {
        device_id: device.id,
        name: this.name.trim() || null,
        started,
        ended,
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
      .times > label {
        flex: 1 1 180px;
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
        min-width: 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-manual-run-dialog": ManualRunDialog;
  }
}
