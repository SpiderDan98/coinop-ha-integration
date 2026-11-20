// Pages for a list too long to show at once: the items of the current page and the
// controls under them. The page size is kept per browser.
import { mdiChevronLeft, mdiChevronRight, mdiPageFirst, mdiPageLast } from "@mdi/js";
import { css, html, nothing, type ReactiveController, type ReactiveControllerHost } from "lit";
import type { Localize } from "./localize";

const SIZES = [25, 50, 100];
const SMALLEST = 25;
const SIZE_KEY = "coinop-page-size";

/** The page size this browser last chose; the smallest without one. */
function storedSize() {
  try {
    const stored = Number(localStorage.getItem(SIZE_KEY));
    return SIZES.includes(stored) ? stored : SMALLEST;
  } catch {
    return SMALLEST;
  }
}

export class Pagination implements ReactiveController {
  private page = 0;
  private size = storedSize();

  constructor(private readonly host: ReactiveControllerHost) {
    host.addController(this);
  }

  hostConnected() {}

  /** Back to the first page, e.g. when the filter changed. */
  reset() {
    this.page = 0;
  }

  /** The current page, which is the last one once the list got shorter. */
  private current(count: number) {
    this.page = Math.min(this.page, Math.max(Math.ceil(count / this.size) - 1, 0));
    return this.page;
  }

  /** The items on the current page. */
  of<Item>(items: readonly Item[]) {
    const start = this.current(items.length) * this.size;
    return items.slice(start, start + this.size);
  }

  /** The controls for a list of `count` items; none while it fits the smallest page. */
  controls(count: number, t: Localize) {
    if (count <= SMALLEST) return nothing;
    const page = this.current(count);
    const last = Math.ceil(count / this.size) - 1;
    const start = page * this.size;
    const button = (name: "first" | "previous" | "next" | "last", path: string, to: number) =>
      html`<ha-icon-button
        class=${name}
        .label=${t(`pager.${name}`)}
        .path=${path}
        ?disabled=${to === page}
        @click=${(event: Event) => this.show(to, event)}
      ></ha-icon-button>`;
    return html`<nav class="pager">
      <label
        >${t("pager.per_page")}<select
          @change=${(event: Event) => {
            this.size = Number((event.target as HTMLSelectElement).value);
            try {
              localStorage.setItem(SIZE_KEY, String(this.size));
            } catch {
              // Private mode or storage switched off: the choice lasts until the page is left.
            }
            // The first item shown stays on the page.
            this.show(Math.floor(start / this.size), event);
          }}
        >
          ${SIZES.map(
            (size) => html`<option value=${size} ?selected=${size === this.size}>${size}</option>`,
          )}
        </select></label
      >
      <span class="range"
        >${t("pager.range", {
          from: start + 1,
          to: Math.min(start + this.size, count),
          count,
        })}</span
      >
      <span class="buttons">
        ${button("first", mdiPageFirst, 0)}
        ${button("previous", mdiChevronLeft, Math.max(page - 1, 0))}
        ${button("next", mdiChevronRight, Math.min(page + 1, last))}
        ${button("last", mdiPageLast, last)}
      </span>
    </nav>`;
  }

  /** Shows `page` from its top: the controls sit under the list. */
  private show(page: number, event: Event) {
    this.page = page;
    this.host.requestUpdate();
    const pager = (event.currentTarget as Element).closest(".pager");
    const list = pager?.closest(".table") ?? pager?.previousElementSibling;
    void this.host.updateComplete.then(() => {
      if (list && list.getBoundingClientRect().top < 0) list.scrollIntoView();
    });
  }
}

/** Every page with a paged list adds these to its styles. */
export const pagerStyles = css`
  .pager {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 0 16px;
    padding: 4px 4px 4px 12px;
    font-size: 12px;
    color: var(--secondary-text-color);
  }
  .pager label {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .pager select {
    min-height: 32px;
    padding-block: 2px;
    font-size: 12px;
  }
  .pager .range {
    font-variant-numeric: tabular-nums;
  }
  .pager .buttons {
    display: flex;
  }
  .pager ha-icon-button {
    --ha-icon-button-size: 36px;
    --mdc-icon-size: 20px;
  }
  /* Clear of the panel's sticky toolbar when a new page scrolls to its top. */
  .table,
  .gallery {
    scroll-margin-top: 120px;
  }
`;
