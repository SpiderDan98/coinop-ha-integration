import {
  mdiChartBar,
  mdiDevices,
  mdiFlaskOutline,
  mdiMenu,
  mdiPackageVariantClosed,
  mdiPlus,
  mdiTagMultiple,
  mdiTextBoxMultiple,
  mdiViewDashboard,
} from "@mdi/js";
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
import "./analysis-page";
import { DEV_INTEGRATION } from "./dev-scenarios-dialog";
import "./devices-page";
import "./manual-run-dialog";
import "./materials-page";
import "./overview";
import "./run-page";
import "./tags-page";
import "./templates-page";
import { runName } from "./run-parts";
import { shared } from "./styles";

const TABS = ["analysis", "materials", "templates", "tags", "devices"] as const;

const ICONS = {
  overview: mdiViewDashboard,
  analysis: mdiChartBar,
  materials: mdiPackageVariantClosed,
  templates: mdiTextBoxMultiple,
  tags: mdiTagMultiple,
  devices: mdiDevices,
} satisfies Record<(typeof TABS)[number] | "overview", string>;

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

  @state() private runs?: Map<string, RunSummary>;
  @state() private failed = false;
  @state() private catalog?: Catalog;
  @state() private catalogFailed = false;
  /** Undefined until loaded, null if loading failed. */
  @state() private devices?: Device[] | null;
  @state() private manualRun = false;
  @state() private devScenarios = false;
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
      old.config.time_zone !== this.hass.config.time_zone ||
      old.dockedSidebar !== this.hass.dockedSidebar
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
          // When HA's own ha-menu-button shows itself.
          this.narrow || this.hass.dockedSidebar === "always_hidden"
            ? html`<ha-icon-button
                class="menu"
                .label=${t("menu")}
                .path=${mdiMenu}
                @click=${this.toggleMenu}
              ></ha-icon-button>`
            : nothing
        }
        <nav class="title">${this.renderTitle(current, run)}</nav>
        <nav class="tabs">
          ${
            this.narrow
              ? TABS.map(
                  (tab) =>
                    html`<a
                      class="tab ${current.name === tab ? "on" : ""}"
                      href="${this.route.prefix}/${tab}"
                      @click=${followLink}
                      >${t(`tab.${tab}`)}</a
                    >`,
                )
              : // Icons only, as HA's dashboards show their views; the title names the open one.
                (["overview", ...TABS] as const).map(
                  (tab) =>
                    html`<a
                      class="tab icon ${
                        current.name === tab || (tab === "overview" && current.name === "run")
                          ? "on"
                          : ""
                      }"
                      href=${tab === "overview" ? this.route.prefix : `${this.route.prefix}/${tab}`}
                      title=${tab === "overview" ? t("runs.title") : t(`tab.${tab}`)}
                      @click=${followLink}
                      ><ha-svg-icon .path=${ICONS[tab]}></ha-svg-icon
                    ></a>`,
                )
          }
        </nav>
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
              html`<div>
                ${
                  // As HA's view headings; on phones the tab row names the page.
                  current.name !== "run" && current.name !== "overview" && !this.narrow
                    ? html`<h1 class="page-title">${t(`tab.${current.name}`)}</h1>`
                    : nothing
                }
                ${this.renderPage(current, run)}
              </div>`,
        )}
      </main>
      ${
        this.hass.config.components.includes(DEV_INTEGRATION)
          ? html`<ha-icon-button
              class="dev"
              .label=${t("dev.title")}
              .path=${mdiFlaskOutline}
              @click=${() => (this.devScenarios = true)}
            ></ha-icon-button>`
          : nothing
      }
      ${
        current.name === "overview"
          ? html`<ha-button
              class="manual-run fab"
              ?disabled=${!this.devices}
              @click=${() => (this.manualRun = true)}
            >
              <ha-svg-icon slot="start" .path=${mdiPlus}></ha-svg-icon>
              ${t("manual.open")}
            </ha-button>`
          : nothing
      }
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
      ${
        this.devScenarios
          ? html`<wattbill-dev-scenarios-dialog
              .hass=${this.hass}
              .basePath=${this.route.prefix}
              @close=${() => (this.devScenarios = false)}
            ></wattbill-dev-scenarios-dialog>`
          : nothing
      }
    `;
  }

  private renderTitle(current: ReturnType<typeof page>, run: RunSummary | undefined) {
    const t = localize(this.hass);
    if (current.name === "overview" || (current.name !== "run" && !this.narrow)) return "WattBill";
    const home = html`<a href=${this.route.prefix} @click=${followLink}>WattBill</a>`;
    if (current.name !== "run") return home;
    return html`${home}<span class="muted"> › </span
      ><span class="ellipsis">${run ? runName(run, t) : ""}</span>`;
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
        .basePath=${this.route.prefix}
        ?narrow=${this.narrow}
      ></wattbill-devices-page>`;
    }
    if (this.failed) return html`<p class="muted">${t("runs.error")}</p>`;
    if (!this.runs) return html`<p class="muted">${t("runs.loading")}</p>`;
    if (current.name === "analysis") {
      return html`<wattbill-analysis-page
        .hass=${this.hass}
        .runs=${this.runs}
        .devices=${this.devices ?? undefined}
        ?narrow=${this.narrow}
      ></wattbill-analysis-page>`;
    }
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
      /* As in HA's hass-subpage. */
      .toolbar {
        position: sticky;
        top: 0;
        z-index: 2;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        padding-top: calc(8px + var(--safe-area-inset-top, 0px));
        height: calc(var(--header-height, 56px) + var(--safe-area-inset-top, 0px));
        font-size: var(--ha-font-size-xl, 20px);
        font-weight: var(--ha-font-weight-normal, 400);
        border-bottom: var(--app-header-border-bottom, none);
        background: var(--app-header-background-color);
        color: var(--app-header-text-color, white);
      }
      .tabs {
        display: flex;
        align-self: stretch;
        margin-left: auto;
        overflow-x: auto;
      }
      .tab {
        display: flex;
        font-size: var(--ha-font-size-m, 14px);
        align-items: center;
        padding: 0 14px;
        white-space: nowrap;
        color: var(--secondary-text-color);
        border-bottom: 2px solid transparent;
      }
      .tab.on {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }
      .tab.icon {
        padding: 0 12px;
      }
      .title a {
        color: inherit;
      }
      .title {
        display: flex;
        gap: 6px;
        min-width: 0;
        margin-inline-start: var(--ha-space-6, 24px);
        white-space: nowrap;
      }
      :host([narrow]) .title {
        flex: 1;
        overflow: hidden;
        margin-inline-start: var(--ha-space-2, 8px);
      }
      /* The tabs get their own scrolling row, so they never squeeze the title. */
      :host([narrow]) .toolbar {
        flex-wrap: wrap;
        row-gap: 0;
        height: auto;
        padding-bottom: 0;
      }
      :host([narrow]) .tabs {
        order: 1;
        flex: 1 0 100%;
        height: 40px;
        margin: 0 -12px;
        padding: 0 4px;
      }
      /* The bottom padding keeps the last row clear of the floating button. */
      main {
        padding: 24px 32px 88px;
        max-width: 1400px;
      }
      /* Matches the heading card of HA's sections view. */
      .page-title {
        margin: 0 0 24px;
        padding: 2px 4px;
        font-size: var(--ha-font-size-xl, 20px);
        font-weight: var(--ha-font-weight-bold, 700);
        line-height: normal;
      }
      /* The create buttons' counterpart; HA's docked sidebar is --ha-sidebar-width wide. */
      ha-icon-button.dev {
        position: fixed;
        z-index: 3;
        bottom: calc(16px + var(--safe-area-inset-bottom, 0px));
        inset-inline-start: calc(16px + var(--ha-sidebar-width, var(--safe-area-inset-left, 0px)));
        --mdc-icon-button-size: 48px;
        border-radius: 50%;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        box-shadow:
          0 6px 12px -3px rgba(0, 0, 0, 0.4),
          0 16px 32px -6px rgba(0, 0, 0, 0.55);
      }
      :host([narrow]) main {
        padding: 12px 16px 88px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-panel": WattbillPanel;
  }
}
