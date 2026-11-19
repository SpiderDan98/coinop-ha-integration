// The WattBill sidebar panel. HA sets `hass`, `narrow`, `route` and `panel`; the
// panel keeps the Runs and the catalogue subscription open while it is shown, loads
// the Devices, and routes by `route.path`.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { cache } from "lit/directives/cache.js";
import {
  listDevices,
  subscribeCatalog,
  subscribeRuns,
  type Catalog,
  type Device,
  type RunSummary,
  type RunsEvent,
} from "./api";
import { followLink, type HomeAssistant, type PanelInfo, type PanelRoute } from "./hass";
import { localize } from "./localize";
import "./devices-page";
import "./manual-run-dialog";
import "./materials-page";
import "./overview";
import "./run-page";
import "./tags-page";
import "./templates-page";
import { runName } from "./run-parts";
import { shared } from "./styles";

const MENU_ICON = "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";

const TABS = ["materials", "templates", "tags", "devices"] as const;

const page = (route: PanelRoute) => {
  const [, section, id] = route.path.split("/");
  if (section === "run" && id) return { name: "run" as const, runId: decodeURIComponent(id) };
  const tab = TABS.find((name) => name === section);
  return tab ? { name: tab } : { name: "overview" as const };
};

@customElement("wattbill-panel")
export class WattbillPanel extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) narrow = false;
  @property({ attribute: false }) route: PanelRoute = { prefix: "/wattbill", path: "" };
  @property({ attribute: false }) panel?: PanelInfo;

  /** Undefined until the first snapshot arrives. */
  @state() private runs?: Map<string, RunSummary>;
  @state() private failed = false;
  /** Undefined until the first catalogue event arrives. */
  @state() private catalog?: Catalog;
  @state() private catalogFailed = false;
  /** Undefined until loaded, null if loading failed. */
  @state() private devices?: Device[] | null;
  @state() private manualRun = false;
  private unsubscribe?: Promise<() => Promise<void>>[];
  private devicesRequest = 0;

  override connectedCallback() {
    super.connectedCallback();
    if (this.hass) this.subscribe();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    for (const unsubscribe of this.unsubscribe ?? []) void unsubscribe.then((stop) => stop());
    this.unsubscribe = undefined;
  }

  // HA hands over a new `hass` on every state change anywhere; only re-render for
  // what the panel shows.
  protected override shouldUpdate(changed: PropertyValues<this>) {
    const old = changed.get("hass");
    if (changed.size > 1 || !old) return true;
    return (
      old.language !== this.hass.language ||
      old.config.currency !== this.hass.config.currency ||
      old.config.time_zone !== this.hass.config.time_zone
    );
  }

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("hass") && !this.unsubscribe && this.isConnected) this.subscribe();
    // Devices change in HA's own settings, so the tabs showing them read them afresh.
    else if (changed.get("route") && ["devices", "templates"].includes(page(this.route).name))
      void this.loadDevices();
  }

  private subscribe() {
    this.failed = this.catalogFailed = false;
    this.unsubscribe = [
      subscribeRuns(this.hass, (event) => this.apply(event)).catch(() => {
        this.failed = true;
        return async () => {};
      }),
      subscribeCatalog(this.hass, (event) => {
        this.catalog = { ...this.catalog, ...event } as Catalog;
      }).catch(() => {
        this.catalogFailed = true;
        return async () => {};
      }),
    ];
    void this.loadDevices();
  }

  private async loadDevices() {
    const request = ++this.devicesRequest;
    const devices = await listDevices(this.hass).catch(() => null);
    if (request === this.devicesRequest) this.devices = devices;
  }

  private apply(event: RunsEvent) {
    if ("runs" in event) {
      this.runs = new Map(event.runs.map((run) => [run.id, run]));
      return;
    }
    const runs = new Map(this.runs);
    if (event.change === "deleted") runs.delete(event.run.id);
    else runs.set(event.run.id, event.run);
    this.runs = runs;
    // A Device added or removed since the Devices were loaded.
    if (this.devices && !this.devices.some((device) => device.id === event.run.device_id))
      void this.loadDevices();
  }

  override render() {
    const t = localize(this.hass);
    const current = page(this.route);
    const run = current.name === "run" ? this.runs?.get(current.runId) : undefined;
    return html`
      <header class="toolbar">
        ${
          this.narrow
            ? html`<button
                class="menu"
                title=${t("menu")}
                aria-label=${t("menu")}
                @click=${this.toggleMenu}
              >
                <svg viewBox="0 0 24 24"><path d=${MENU_ICON}></path></svg>
              </button>`
            : nothing
        }
        <nav class="title">
          ${
            current.name === "overview"
              ? "WattBill"
              : html`<a href=${this.route.prefix} @click=${followLink}>WattBill</a>${
                    current.name === "run"
                      ? html`<span class="muted"> › </span
                          ><span class="ellipsis">${run ? runName(run, t) : ""}</span>`
                      : nothing
                  }`
          }
        </nav>
        <nav class="tabs">
          ${TABS.map(
            (tab) =>
              html`<a
                class="tab ${current.name === tab ? "on" : ""}"
                href="${this.route.prefix}/${tab}"
                @click=${followLink}
                >${t(`tab.${tab}`)}</a
              >`,
          )}
        </nav>
        <button
          class="btn manual-run"
          ?disabled=${!this.devices?.length}
          @click=${() => (this.manualRun = true)}
        >
          ${t("manual.open")}
        </button>
      </header>
      <main>
        ${cache(
          current.name === "overview" && this.runs && !this.failed
            ? html`<wattbill-overview
                .hass=${this.hass}
                .runs=${this.runs}
                .devices=${this.devices ?? undefined}
                .tags=${this.catalog?.tags ?? []}
                .basePath=${this.route.prefix}
                ?narrow=${this.narrow}
              ></wattbill-overview>`
            : // One template for every other page, so only the Overview's filter and
              // selection are kept while the user looks elsewhere.
              html`<div>${this.renderPage(current, run)}</div>`,
        )}
      </main>
      ${
        this.manualRun && this.devices
          ? html`<wattbill-manual-run-dialog
              .hass=${this.hass}
              .devices=${this.devices}
              .tags=${this.catalog?.tags ?? []}
              .basePath=${this.route.prefix}
              @close=${() => (this.manualRun = false)}
            ></wattbill-manual-run-dialog>`
          : nothing
      }
    `;
  }

  private renderPage(current: ReturnType<typeof page>, run: RunSummary | undefined) {
    const t = localize(this.hass);
    if (current.name === "materials") {
      return this.catalogFailed
        ? html`<p class="muted">${t("catalog.error")}</p>`
        : html`<wattbill-materials-page
            .hass=${this.hass}
            .materials=${this.catalog?.materials}
            ?narrow=${this.narrow}
          ></wattbill-materials-page>`;
    }
    if (current.name === "templates") {
      return this.catalogFailed
        ? html`<p class="muted">${t("catalog.error")}</p>`
        : html`<wattbill-templates-page
            .hass=${this.hass}
            .templates=${this.catalog?.templates}
            .devices=${this.devices ?? undefined}
            ?narrow=${this.narrow}
          ></wattbill-templates-page>`;
    }
    if (current.name === "devices") {
      return html`<wattbill-devices-page
        .hass=${this.hass}
        .devices=${this.devices}
        .tags=${this.catalog?.tags ?? []}
        .materials=${this.catalog?.materials ?? []}
        .templates=${this.catalog?.templates ?? []}
        ?narrow=${this.narrow}
      ></wattbill-devices-page>`;
    }
    if (this.failed) return html`<p class="muted">${t("runs.error")}</p>`;
    if (!this.runs) return html`<p class="muted">${t("runs.loading")}</p>`;
    if (current.name === "tags") {
      return this.catalogFailed
        ? html`<p class="muted">${t("catalog.error")}</p>`
        : html`<wattbill-tags-page
            .hass=${this.hass}
            .tags=${this.catalog?.tags}
            .runs=${[...this.runs.values()]}
            ?narrow=${this.narrow}
          ></wattbill-tags-page>`;
    }
    return html`<wattbill-run-page
      .hass=${this.hass}
      .runId=${current.name === "run" ? current.runId : ""}
      .summary=${run}
      .devices=${this.devices ?? undefined}
      .tags=${this.catalog?.tags ?? []}
      .materials=${this.catalog?.materials ?? []}
      .templates=${this.catalog?.templates ?? []}
      .basePath=${this.route.prefix}
      ?narrow=${this.narrow}
    ></wattbill-run-page>`;
  }

  private toggleMenu() {
    this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
        min-height: 100%;
        background: var(--primary-background-color, #fafafa);
      }
      .toolbar {
        position: sticky;
        top: 0;
        z-index: 2;
        height: var(--header-height, 56px);
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 0 16px;
        border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        background: var(--app-header-background-color, var(--primary-background-color, #fafafa));
        color: var(--app-header-text-color, var(--primary-text-color));
      }
      .tabs {
        display: flex;
        align-self: stretch;
        margin-left: auto;
        overflow-x: auto;
      }
      .tab {
        display: flex;
        align-items: center;
        padding: 0 14px;
        white-space: nowrap;
        color: var(--secondary-text-color);
        border-bottom: 2px solid transparent;
      }
      .manual-run {
        flex: none;
      }
      .tab.on {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }
      .title {
        font-size: 20px;
        display: flex;
        gap: 6px;
        min-width: 0;
        white-space: nowrap;
      }
      .menu {
        border: 0;
        background: none;
        color: inherit;
        padding: 8px;
        margin-left: -8px;
        cursor: pointer;
        border-radius: 50%;
      }
      .menu svg {
        width: 24px;
        height: 24px;
        display: block;
        fill: currentColor;
      }
      main {
        padding: 16px 24px 48px;
        max-width: 1400px;
      }
      :host([narrow]) main {
        padding: 12px 16px 32px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-panel": WattbillPanel;
  }
}
