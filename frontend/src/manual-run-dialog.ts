// "Manual Run": a Run made by hand for a Run Coin-op did not see. Pre-fills the
// Device's Tags for new Runs, opens the new Run's page once created and fires `close`.
import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { OUTCOMES, createRun, type Device, type Outcome } from "./api";
import { formatter } from "./format";
import { followLink, navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import { RECONFIGURE } from "./devices-page";
import { formDialog } from "./dialog";
import { field, input, select } from "./fields";
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
  @state() private program = "";
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
    const program = this.programOf(device);
    return formDialog({
      t,
      title: t("manual.title"),
      name: "manual-dialog",
      action: "create",
      submit: t("manual.create"),
      busy: this.saving,
      disabled: !device || !times.started,
      error: this.failed && t("manual.failed"),
      onCancel: () => this.close(),
      onSubmit: () => this.create(tags),
      content: html`<p class="muted small">${t("manual.hint")}</p>
        ${
          this.devices.length > 1
            ? field(
                t("run.device"),
                select({
                  name: "device",
                  value: device?.id,
                  options: this.devices.map(({ id, name }) => [id, name]),
                  onChange: (id) => {
                    this.deviceId = id;
                    this.runTags = undefined;
                  },
                }),
              )
            : nothing
        }
        ${field(
          t("run.name"),
          input({
            name: "name",
            autofocus: true,
            value: this.name,
            placeholder: program ?? t("run.untitled"),
            onInput: (name) => (this.name = name),
          }),
        )}
        ${
          device?.capabilities.includes("program")
            ? field(
                t("run.program"),
                input({
                  name: "program",
                  list: device.known_programs,
                  value: this.program,
                  onInput: (entered) => (this.program = entered),
                }),
              )
            : nothing
        }
        <div class="field-row">
          ${field(
            t("run.started"),
            input({
              type: "datetime-local",
              name: "started",
              max: now,
              value: this.started,
              onInput: (started) => (this.started = started),
            }),
          )}
          ${field(
            t("run.ended"),
            input({
              type: "datetime-local",
              name: "ended",
              max: now,
              invalid: !!times.problem,
              value: this.ended,
              onInput: (ended) => (this.ended = ended),
            }),
          )}
        </div>
        ${
          times.problem
            ? html`<p class="error small times-problem">${t(`manual.${times.problem}`)}</p>`
            : nothing
        }
        ${field(
          t("run.outcome"),
          select({
            name: "outcome",
            value: this.outcome,
            options: OUTCOMES.map((outcome) => [outcome, t(`outcome.${outcome}`)]),
            onChange: (outcome) => (this.outcome = outcome as Outcome),
          }),
        )}
        ${field(
          t("run.tags"),
          html`<coinop-tag-input
            .hass=${this.hass}
            .tags=${tags}
            .catalog=${this.tags}
            .label=${t("run.tags")}
            @tags-change=${(event: CustomEvent<string[]>) => (this.runTags = event.detail)}
          ></coinop-tag-input>`,
          { group: true },
        )}`,
    });
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

  /** The Program entered, null for none; undefined for a Device without Programs. */
  private programOf(device: Device | undefined) {
    if (!device?.capabilities.includes("program")) return undefined;
    return this.program.trim() || null;
  }

  private async create(tags: string[]) {
    const device = this.device;
    const { started, ended } = this.times;
    if (!device || !started || !ended) return;
    const program = this.programOf(device);
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
        ...(program === undefined ? {} : { program }),
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

  static override styles = shared;
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-manual-run-dialog": ManualRunDialog;
  }
}
