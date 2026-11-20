// The panel's one table: a native <table> in a card that scrolls sideways when too wide
// (ADR 0007). Pages render their own <tr>s; cells with class "num" hold figures.
import { css, html, nothing } from "lit";

export function table({
  name = "",
  header,
  columns,
  rows,
  foot,
  empty,
}: {
  /** Classes of the card, e.g. to place it; "stacked" turns rows into cards on phones. */
  name?: string;
  /** Shown in the card above the table. */
  header?: unknown;
  columns: { label?: unknown; num?: boolean; class?: string }[];
  /** The <tr>s, as a list or `repeat()`ed. */
  rows: unknown;
  /** The <tr>s of a total row. */
  foot?: unknown;
  /** Shown as the only row when there are no rows. */
  empty?: string;
}) {
  return html`<div class="table ${name}">
    ${header ?? nothing}
    <table>
      <thead>
        <tr>
          ${columns.map(
            (column) =>
              html`<th class="${column.num ? "num" : ""} ${column.class ?? ""}">
                ${column.label ?? ""}
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
  </div>`;
}

const divider = css`1px solid var(--divider-color, rgba(0, 0, 0, 0.12))`;

/** Every page with a table adds these to its styles. */
export const tableStyles = css`
  .table {
    box-sizing: border-box;
    max-width: 100%;
    overflow-x: auto;
    background: var(--card-background-color, #fff);
    border: ${divider};
    border-radius: 12px;
  }
  .table table {
    width: 100%;
    border-collapse: collapse;
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
