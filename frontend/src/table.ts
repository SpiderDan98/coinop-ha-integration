// The panel's one table: a native <table> in a card that scrolls sideways when too wide
// and, where a page limits its height, down under a head that stays (ADR 0007). Pages
// render their own <tr>s; cells with class "num" hold figures.
import { mdiArrowDown, mdiArrowUp } from "@mdi/js";
import { css, html, nothing } from "lit";

/** Columns with a `sort` key sort by it: a click sorts ascending, the next one reverses. */
export function table<Key extends string>({
  name = "",
  header,
  columns,
  rows,
  foot,
  pager,
  empty,
  sort,
  onSort,
}: {
  /** Classes of the card, e.g. to place it; "stacked" turns rows into cards on phones. */
  name?: string;
  /** Shown in the card above the table. */
  header?: unknown;
  columns: { label?: unknown; num?: boolean; class?: string; sort?: Key }[];
  /** The <tr>s, as a list or `repeat()`ed. */
  rows: unknown;
  /** The <tr>s of a total row. */
  foot?: unknown;
  /** A paged table's `Pagination` controls, shown in the card below the rows. */
  pager?: unknown;
  /** Shown as the only row when there are no rows. */
  empty?: string;
  sort?: { by: Key; descending: boolean };
  onSort?: (sort: { by: Key; descending: boolean }) => void;
}) {
  const heading = (column: (typeof columns)[number]) => {
    const key = column.sort;
    if (!key || !sort || !onSort) return column.label ?? "";
    const on = sort.by === key;
    return html`<button
      class="sort"
      @click=${() => onSort({ by: key, descending: on && !sort.descending })}
    >
      ${column.label}${
        on
          ? html`<ha-svg-icon .path=${sort.descending ? mdiArrowDown : mdiArrowUp}></ha-svg-icon>`
          : nothing
      }
    </button>`;
  };
  const ariaSort = (key?: Key) =>
    !key || !sort
      ? nothing
      : sort.by !== key
        ? "none"
        : sort.descending
          ? "descending"
          : "ascending";
  return html`<div class="table ${name}">
    ${header ?? nothing}
    <div class="rows">
      <table>
        <thead>
          <tr>
            ${columns.map(
              (column) =>
                html`<th
                  class="${column.num ? "num" : ""} ${column.class ?? ""}"
                  aria-sort=${ariaSort(column.sort)}
                >
                  ${heading(column)}
                </th>`,
            )}
          </tr>
        </thead>
        <tbody>
          ${
            !Array.isArray(rows) || rows.length || empty === undefined
              ? rows
              : html`<tr class="empty">
                  <td colspan=${columns.length} class="muted">${empty}</td>
                </tr>`
          }
        </tbody>
        ${
          foot
            ? html`<tfoot>
                ${foot}
              </tfoot>`
            : nothing
        }
      </table>
    </div>
    ${pager ?? nothing}
  </div>`;
}

const divider = css`1px solid var(--divider-color, rgba(0, 0, 0, 0.12))`;

/** Every page with a table adds these to its styles. */
export const tableStyles = css`
  .table {
    box-sizing: border-box;
    max-width: 100%;
    overflow: hidden;
    background: var(--card-background-color, #fff);
    border: ${divider};
    border-radius: 12px;
  }
  .table .rows {
    overflow: auto;
    max-height: var(--coinop-table-height, none);
  }
  /* Separate borders stay with the sticky cells. */
  .table table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
  }
  .table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--card-background-color, #fff);
  }
  .table tfoot td {
    position: sticky;
    bottom: 0;
    background: var(--card-background-color, #fff);
  }
  .table th,
  .table td {
    padding: 8px 12px;
    text-align: left;
    vertical-align: middle;
    border-bottom: ${divider};
  }
  .table th {
    font-weight: 500;
    font-size: 12px;
    color: var(--secondary-text-color);
    white-space: nowrap;
  }
  .table th .sort {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 0;
    font: inherit;
    color: inherit;
    background: none;
    border: 0;
    cursor: pointer;
    --mdc-icon-size: 14px;
  }
  .table th .sort:hover,
  .table th[aria-sort="ascending"],
  .table th[aria-sort="descending"] {
    color: var(--primary-text-color);
  }
  .table th .sort:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
    border-radius: 2px;
  }
  .table .pager {
    border-top: ${divider};
  }
  .table .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .table .center {
    text-align: center;
  }
  .table tbody tr:last-child td {
    border-bottom: 0;
  }
  .table tfoot td {
    font-weight: 500;
    border-top: ${divider};
    border-bottom: 0;
  }
  .table .actions {
    text-align: right;
    white-space: nowrap;
  }
  .table .actions ha-icon-button {
    --ha-icon-button-size: 36px;
    --mdc-icon-size: 20px;
    color: var(--secondary-text-color);
  }
  :host([narrow]) .table th,
  :host([narrow]) .table td {
    padding: 6px 10px;
  }
  :host([narrow]) .table .actions {
    white-space: normal;
  }
  :host([narrow]) .table.stacked .rows {
    max-height: none;
  }
  :host([narrow]) .table.stacked :is(table, thead, tbody, tr, td) {
    display: block;
  }
  :host([narrow]) .table.stacked thead {
    display: none;
  }
  :host([narrow]) .table.stacked tr {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    padding: 8px;
    border-bottom: ${divider};
  }
  :host([narrow]) .table.stacked tr:last-child {
    border-bottom: 0;
  }
  :host([narrow]) .table.stacked td {
    border: 0;
    padding: 0;
  }
  :host([narrow]) .table.stacked td:first-child {
    grid-column: 1 / -1;
  }
`;
