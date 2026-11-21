// Dev container only (the `coinop_dev` integration): switches Coin-op's data to a
// Scenario of test data, the Pieces picked. Loading replaces the hub entry, so the page
// loads afresh after.
import { mdiChevronDown } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { Device } from "./api";
import { formDialog } from "./dialog";
import { checkbox, field, select } from "./fields";
import type { HomeAssistant } from "./hass";
import { type Localize, localize } from "./localize";
import { shared } from "./styles";

export const DEV_INTEGRATION = "coinop_dev";

const SECTIONS = [
  ["device", "dev.devices_with_history"],
  ["quick_start", "dev.quick_start"],
] as const;

type Selection = { pieces: string[]; history: "none" | "short" | "long"; open_run: boolean };

const listScenarios = (hass: HomeAssistant) =>
  hass.callWS<{
    groups: {
      device_type: Device["type"];
      pieces: {
        name: string;
        title: string;
        description: string;
        section: (typeof SECTIONS)[number][0];
      }[];
    }[];
    options: { history: Selection["history"][] };
    presets: { name: string; title: string; description: string; selection: Selection }[];
    preset: string | null;
    selection: Selection | null;
  }>({ type: `${DEV_INTEGRATION}/scenarios` });

@customElement("coinop-dev-scenarios-dialog")
export class DevScenariosDialog extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) basePath = "";

  @state() private list?: Awaited<ReturnType<typeof listScenarios>>;
  @state() private picked = new Set<string>();
  @state() private history: Selection["history"] = "short";
  @state() private openRun = false;
  @state() private preset = "";
  @state() private loading = false;
  @state() private failed = false;
  // Fixed once listed, so that the groups open and close only when the user says so.
  private expanded = new Set<string>();

  override connectedCallback() {
    super.connectedCallback();
    listScenarios(this.hass).then(
      (list) => {
        this.pick(list.selection ?? { pieces: [] }, list.preset ?? "");
        this.expanded = new Set(
          list.groups
            .filter(({ pieces }) => pieces.some(({ name }) => this.picked.has(name)))
            .map(({ device_type }) => device_type),
        );
        this.list = list;
      },
      () => (this.failed = true),
    );
  }

  override render() {
    const t = localize(this.hass);
    return formDialog({
      t,
      title: t("dev.title"),
      content: html`<p class="muted small">${t("dev.hint")}</p>
        ${this.list ? this.renderPresets(this.list.presets, t) : nothing}
        <div class="row">
          <ha-button
            class="all small"
            appearance="plain"
            ?disabled=${this.loading}
            @click=${() => this.pick({ pieces: this.names() })}
            >${t("dev.all")}</ha-button
          >
          <ha-button
            class="none small"
            appearance="plain"
            ?disabled=${this.loading}
            @click=${() => this.pick({ pieces: [] })}
            >${t("dev.none")}</ha-button
          >
        </div>
        ${this.list ? this.renderOptionFields(this.list.options, t) : nothing}
        ${this.list?.groups.map((group) => this.renderGroup(group, t))}`,
      error: this.failed && t("dev.failed"),
      action: "load",
      submit: this.loading ? t("dev.loading") : t("dev.load"),
      busy: this.loading,
      disabled: !this.list,
      onCancel: () => !this.loading && this.dispatchEvent(new Event("close")),
      onSubmit: () => this.load(),
    });
  }

  private renderPresets(presets: NonNullable<typeof this.list>["presets"], t: Localize) {
    const picked = presets.find(({ name }) => name === this.preset);
    return html`<div class="presets">
      <span class="muted small">${t("dev.presets")}</span>
      <div class="row">
        ${presets.map(
          ({ name, title, selection }) =>
            html`<ha-button
              class="preset small"
              appearance=${name === this.preset ? "filled" : "plain"}
              ?disabled=${this.loading}
              @click=${() => this.pick(selection, name)}
              >${title}</ha-button
            >`,
        )}
      </div>
      <span class="muted small">${picked ? picked.description : t("dev.own_selection")}</span>
    </div>`;
  }

  private renderOptionFields({ history }: NonNullable<typeof this.list>["options"], t: Localize) {
    return html`<div class="options">
      ${field(
        t("dev.history"),
        select({
          name: "history",
          value: this.history,
          options: history.map((value) => [value, t(`dev.history_${value}`)] as const),
          disabled: this.loading,
          onChange: (value) => this.pick({ history: value as Selection["history"] }),
        }),
      )}
      ${checkbox({
        name: "open_run",
        label: t("dev.open_run"),
        checked: this.openRun,
        disabled: this.loading,
        onChange: (open_run) => this.pick({ open_run }),
      })}
    </div>`;
  }

  /** Picks `selection`, keeping what it leaves out, as the Preset `preset` does or as the
   * user's own selection. */
  private pick(
    {
      pieces = this.picked,
      history = this.history,
      open_run = this.openRun,
    }: Partial<Omit<Selection, "pieces">> & { pieces?: Iterable<string> },
    preset = "",
  ) {
    this.picked = new Set(pieces);
    this.history = history;
    this.openRun = open_run;
    this.preset = preset;
  }

  /** Every Piece's name, in group, then Piece order. */
  private names() {
    return this.list?.groups.flatMap(({ pieces }) => pieces.map(({ name }) => name)) ?? [];
  }

  private async load() {
    const pieces = this.names().filter((name) => this.picked.has(name));
    this.loading = true;
    this.failed = false;
    try {
      await this.hass.callWS({
        type: "call_service",
        domain: DEV_INTEGRATION,
        service: "load",
        // By name, a Preset is stored as loaded.
        service_data: this.preset
          ? { preset: this.preset }
          : ({ pieces, history: this.history, open_run: this.openRun } satisfies Selection),
      });
    } catch {
      this.loading = false;
      this.failed = true;
      return;
    }
    location.assign(this.basePath);
  }

  private renderGroup(
    { device_type, pieces }: NonNullable<typeof this.list>["groups"][number],
    t: Localize,
  ) {
    const names = pieces.map(({ name }) => name);
    const count = names.filter((name) => this.picked.has(name)).length;
    const all = count === names.length;
    return html`<details class="group" ?open=${this.expanded.has(device_type)}>
      <summary>
        ${checkbox({
          label: html`<span class="strong">${t(`device_type.${device_type}`)}</span>`,
          checked: all,
          indeterminate: count > 0 && !all,
          disabled: this.loading,
          onChange: () => this.toggle(names, !all),
        })}
        <span class="muted small">${t("dev.count", { count, total: names.length })}</span>
        <ha-svg-icon class="chevron" .path=${mdiChevronDown}></ha-svg-icon>
      </summary>
      ${SECTIONS.map(([section, heading]) => {
        const inSection = pieces.filter((piece) => piece.section === section);
        return inSection.length
          ? html`<h3 class="muted small">${t(heading)}</h3>
              ${inSection.map(
                ({ name, title, description }) =>
                  html`<div class="piece">
                    ${checkbox({
                      label: html`<span
                        ><strong>${title}</strong
                        ><span class="muted small">${description}</span></span
                      >`,
                      checked: this.picked.has(name),
                      disabled: this.loading,
                      onChange: (pick) => this.toggle([name], pick),
                    })}
                  </div>`,
              )}`
          : nothing;
      })}
    </details>`;
  }

  private toggle(names: string[], pick: boolean) {
    const picked = new Set(this.picked);
    for (const name of names) {
      if (pick) picked.add(name);
      else picked.delete(name);
    }
    this.pick({ pieces: picked });
  }

  static override styles = [
    shared,
    css`
      .presets,
      .options {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .group {
        border-top: 1px solid var(--divider-color);
        padding-top: 8px;
      }
      /* The checkbox's label selects the group; the rest of the heading folds it. */
      summary {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        list-style: none;
      }
      summary::-webkit-details-marker {
        display: none;
      }
      summary > .muted {
        margin-inline-start: auto;
      }
      .chevron {
        color: var(--secondary-text-color);
        transition: transform 0.2s;
      }
      .group[open] .chevron {
        transform: rotate(180deg);
      }
      h3 {
        margin: 8px 0 4px;
        font-weight: 500;
      }
      .piece .check {
        align-items: flex-start;
        padding: 4px 0;
      }
      .piece .check > span {
        display: flex;
        flex-direction: column;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-dev-scenarios-dialog": DevScenariosDialog;
  }
}
