// The WattBill sidebar panel. HA sets `hass`, `narrow`, `route` and `panel`; the
// panel keeps one Runs subscription open while it is shown and routes by `route.path`.
import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { subscribeRuns, type RunSummary, type RunsEvent } from "./api";
import { followLink, type HomeAssistant, type PanelInfo, type PanelRoute } from "./hass";
import { localize } from "./localize";
import "./run-gallery";
import "./run-page";
import { runName } from "./run-parts";
import { shared } from "./styles";

const MENU_ICON = "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";

const page = (route: PanelRoute) => {
  const [, section, id] = route.path.split("/");
  return section === "run" && id
    ? { name: "run" as const, runId: decodeURIComponent(id) }
    : { name: "overview" as const };
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
  private unsubscribe?: Promise<() => Promise<void>>;

  override connectedCallback() {
    super.connectedCallback();
    if (this.hass) this.subscribe();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    void this.unsubscribe?.then((unsubscribe) => unsubscribe());
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
  }

  private subscribe() {
    this.failed = false;
    this.unsubscribe = subscribeRuns(this.hass, (event) => this.apply(event)).catch(() => {
      this.failed = true;
      return async () => {};
    });
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
              : html`<a href=${this.route.prefix} @click=${followLink}>WattBill</a
                  ><span class="muted"> › </span
                  ><span class="ellipsis">${run ? runName(run, t) : ""}</span>`
          }
        </nav>
      </header>
      <main>
        ${
          this.failed
            ? html`<p class="muted">${t("runs.error")}</p>`
            : !this.runs
              ? html`<p class="muted">${t("runs.loading")}</p>`
              : current.name === "run"
                ? html`<wattbill-run-page
                    .hass=${this.hass}
                    .runId=${current.runId}
                    .summary=${run}
                    .basePath=${this.route.prefix}
                    ?narrow=${this.narrow}
                  ></wattbill-run-page>`
                : html`<wattbill-run-gallery
                    .hass=${this.hass}
                    .runs=${[...this.runs.values()]}
                    .basePath=${this.route.prefix}
                    ?narrow=${this.narrow}
                  ></wattbill-run-gallery>`
        }
      </main>
    `;
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
      .title {
        font-size: 20px;
        display: flex;
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
