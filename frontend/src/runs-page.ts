// The Runs tab: the list with its filters, and a basket of selected final Runs. The filter
// lives in the URL; the panel keeps this page (lit `cache`) so the selection survives a
// visit to a Run page.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { deleteRuns, previewDelete, type Device, type RunSummary, type Totals } from "./api";
import { formatter, type Format } from "./format";
import { navigate, type HomeAssistant } from "./hass";
import { localize, type Localize } from "./localize";
import {
  DEFAULT_SORT,
  NO_FILTER,
  runsPath,
  selectable,
  type Filter,
  type Sort,
} from "./runs-query";
import "./run-list";
import { deleteDialog, runCount, runName } from "./run-parts";
import { RunsTotal } from "./runs-total";
import "./statement-dialog";
import { shared } from "./styles";

@customElement("coinop-runs-page")
export class RunsPage extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** Replaced, not changed, whenever a Run changes. */
  @property({ attribute: false }) runs: ReadonlyMap<string, RunSummary> = new Map();
  @property({ attribute: false }) devices?: Device[];
  @property({ attribute: false }) tags: string[] = [];
  @property({ attribute: false }) basePath = "";
  @property({ type: Boolean, reflect: true }) narrow = false;
  /** As the URL has it. */
  @property({ attribute: false }) filter = NO_FILTER;
  @property({ attribute: false }) sort = DEFAULT_SORT;

  @state() private selected: ReadonlySet<string> = new Set();
  /** Set while the delete confirmation is open. */
  @state() private drop?: Totals;
  @state() private deleteFailed = false;
  @state() private exporting = false;
  private readonly basketTotal = new RunsTotal(this);

  protected override willUpdate() {
    this.basketTotal.load(this.hass, this.selectedRuns());
  }

  /** The selected Runs that are still there and final, by start. */
  selectedRuns() {
    return [...this.runs.values()]
      .filter((run) => this.selected.has(run.id) && selectable(run))
      .sort((a, b) => a.started.localeCompare(b.started));
  }

  /** Each filter change is a step back; typing on in the name field is not. */
  private setFilter(filter: Filter) {
    const typing =
      !!this.filter.name &&
      !!filter.name &&
      JSON.stringify({ ...this.filter, name: "" }) === JSON.stringify({ ...filter, name: "" });
    navigate(runsPath(this.basePath, filter, this.sort), { replace: typing });
  }

  private async confirmDelete() {
    this.deleteFailed = false;
    try {
      this.drop = await previewDelete(
        this.hass,
        this.selectedRuns().map((run) => run.id),
      );
    } catch {
      this.deleteFailed = true;
    }
  }

  private async delete() {
    try {
      await deleteRuns(
        this.hass,
        this.selectedRuns().map((run) => run.id),
      );
      this.selected = new Set();
    } catch {
      this.deleteFailed = true;
    }
    this.drop = undefined;
  }

  override render() {
    const t = localize(this.hass);
    const format = formatter(this.hass);
    const selected = this.selectedRuns();
    return html`
      <coinop-run-list
        .hass=${this.hass}
        .runs=${[...this.runs.values()]}
        .devices=${this.devices}
        .tags=${this.tags}
        .basePath=${this.basePath}
        .filter=${this.filter}
        .sort=${this.sort}
        .selected=${new Set(selected.map((run) => run.id))}
        ?narrow=${this.narrow}
        @filter-changed=${(event: CustomEvent<Filter>) => this.setFilter(event.detail)}
        @sort-changed=${(event: CustomEvent<Sort>) =>
          navigate(runsPath(this.basePath, this.filter, event.detail))}
        @selection-changed=${(event: CustomEvent<Set<string>>) => (this.selected = event.detail)}
      ></coinop-run-list>
      ${selected.length ? this.renderBasket(selected, t, format) : nothing}
      ${
        this.exporting && selected.length
          ? html`<coinop-statement-dialog
              .hass=${this.hass}
              .runIds=${selected.map((run) => run.id)}
              .tag=${this.filter.tags.length === 1 && !this.filter.untagged ? this.filter.tags[0] : undefined}
              @close=${() => (this.exporting = false)}
            ></coinop-statement-dialog>`
          : nothing
      }
      ${
        this.drop
          ? deleteDialog(t("delete.title_many", { count: selected.length }), this.drop, t, format, {
              cancel: () => (this.drop = undefined),
              confirm: () => void this.delete(),
            })
          : nothing
      }
    `;
  }

  private renderBasket(runs: RunSummary[], t: Localize, format: Format) {
    return html`<aside class="basket card" aria-label=${t("basket.title")}>
      <div class="summary">
        <b>${runCount(runs.length, t)}</b>
        <b class="num"
          >${this.basketTotal.cost === undefined ? nothing : format.money(this.basketTotal.cost)}</b
        >
      </div>
      <div class="muted small names">${runs.map((run) => runName(run, t)).join(", ")}</div>
      <div class="row actions">
        <ha-button class="small statement" @click=${() => (this.exporting = true)}>
          ${t("basket.statement")}
        </ha-button>
        <ha-button
          class="small clear"
          appearance="plain"
          @click=${() => (this.selected = new Set())}
        >
          ${t("basket.clear")}
        </ha-button>
        <ha-button
          class="small delete end"
          appearance="plain"
          variant="danger"
          @click=${this.confirmDelete}
        >
          ${t("basket.delete")}
        </ha-button>
      </div>
      ${this.deleteFailed ? html`<p class="error small">${t("basket.delete_failed")}</p>` : nothing}
    </aside>`;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      /* Sticks to the bottom while the list scrolls and rests below its last row. */
      .basket {
        position: sticky;
        bottom: 16px;
        z-index: 4;
        margin-top: 16px;
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        gap: 4px 16px;
        border: 2px solid var(--primary-color);
        box-shadow: 0 6px 22px rgba(0, 0, 0, 0.2);
      }
      :host([narrow]) .basket {
        grid-template-columns: minmax(0, 1fr);
      }
      .summary {
        display: flex;
        gap: 8px;
      }
      .names {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .basket .actions {
        flex-wrap: nowrap;
      }
      .basket .end {
        margin-inline-start: auto;
      }
      .basket .error {
        grid-column: 1 / -1;
      }
      .error {
        color: var(--error-color, #db4437);
        margin: 0;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-runs-page": RunsPage;
  }
}
