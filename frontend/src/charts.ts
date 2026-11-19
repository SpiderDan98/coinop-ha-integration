// Small charts drawn as inline SVG, so the panel needs neither HA's internal elements
// nor a chart library. Values below zero (refunds) draw as nothing.
import { css, html, svg } from "lit";

const STACK_HEIGHT = 120;
const STACK_WIDTH = 28;
const GAP = 2;
const RADIUS = 4;

/** A bar segment with rounded top corners, anchored to the baseline below. */
const roundedTop = (y: number, height: number, width: number) => {
  const r = Math.min(RADIUS, height, width / 2);
  return `M0,${y + height}V${y + r}Q0,${y} ${r},${y}H${width - r}Q${width},${y} ${width},${y + r}V${y + height}Z`;
};

type Segment = { amount: number; colour: string; title: string };

/** One clickable column per entry, its segments stacked bottom-up in the given order.
 * Only the highest and the picked column carry their value; every column has it as title. */
export function stackedColumns(
  columns: {
    key: string;
    label: string;
    title: string;
    value: string;
    on: boolean;
    segments: Segment[];
  }[],
  pick: (key: string) => void,
) {
  const height = (segments: Segment[]) =>
    segments.reduce((sum, segment) => sum + Math.max(segment.amount, 0), 0);
  const max = Math.max(...columns.map((column) => height(column.segments)), 0) || 1;
  return html`<div class="columns">
    ${columns.map((column) => {
      let top = STACK_HEIGHT;
      const shown = column.segments.filter((segment) => segment.amount > 0);
      const bars = shown.map((segment, index) => {
        const size = Math.max((segment.amount / max) * STACK_HEIGHT - (index ? GAP : 0), 1);
        top -= size + (index ? GAP : 0);
        const last = index === shown.length - 1;
        return last
          ? svg`<path d=${roundedTop(top, size, STACK_WIDTH)} style="fill:${segment.colour}"></path>`
          : svg`<rect y=${top} width=${STACK_WIDTH} height=${size} style="fill:${segment.colour}"></rect>`;
      });
      return html`<button
        class="column ${column.on ? "on" : ""}"
        aria-pressed=${column.on ? "true" : "false"}
        aria-label="${column.title}: ${column.value}"
        title=${[column.title, ...column.segments.map((segment) => segment.title)].join("\n")}
        @click=${() => pick(column.key)}
      >
        <span class="value"
          >${column.on || height(column.segments) === max ? column.value : ""}</span
        >
        <svg
          width=${STACK_WIDTH}
          height=${STACK_HEIGHT}
          viewBox="0 0 ${STACK_WIDTH} ${STACK_HEIGHT}"
          aria-hidden="true"
        >
          ${bars}
        </svg>
        <span class="label">${column.label}</span>
      </button>`;
    })}
  </div>`;
}

/** Horizontal bars, longest first as given, each with its label and value. */
export function barRows(rows: { label: string; value: string; amount: number; colour: string }[]) {
  const max = Math.max(...rows.map((row) => row.amount), 0) || 1;
  return html`<div class="bar-rows">
    ${rows.map(
      (row) =>
        html`<div class="bar-row" title="${row.label}: ${row.value}">
          <span class="ellipsis">${row.label}</span>
          <span class="num">${row.value}</span>
          <svg class="track" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">
            <rect
              width="100"
              height="8"
              style="fill:var(--secondary-background-color, #ededed)"
            ></rect>
            <rect
              width=${(Math.max(row.amount, 0) / max) * 100}
              height="8"
              style="fill:${row.colour}"
            ></rect>
          </svg>
        </div>`,
    )}
  </div>`;
}

export const legend = (entries: { label: string; colour: string }[]) =>
  html`<div class="legend">
    ${entries.map(
      (entry) => html`<span><i style="background:${entry.colour}"></i>${entry.label}</span>`,
    )}
  </div>`;

export const chartStyles = css`
  .columns {
    display: flex;
    gap: 4px;
    align-items: flex-end;
    overflow-x: auto;
    padding-top: 8px;
  }
  .column {
    flex: 1 0 36px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    font: inherit;
    color: inherit;
    background: none;
    border: 0;
    border-radius: 8px;
    padding: 4px 2px;
    cursor: pointer;
  }
  .column:hover,
  .column:focus-visible {
    background: var(--secondary-background-color, #ededed);
  }
  .column.on {
    outline: 2px solid var(--primary-color);
  }
  .column .value {
    min-height: 1.4em;
  }
  .column .value,
  .column .label {
    font-size: 11px;
    color: var(--secondary-text-color);
    white-space: nowrap;
  }
  .bar-rows {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 10px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px 8px;
  }
  .bar-row .track {
    grid-column: 1 / -1;
    width: 100%;
    height: 8px;
    border-radius: 4px;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: var(--secondary-text-color);
    margin-top: 6px;
  }
  .legend i {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 3px;
    margin-right: 4px;
    vertical-align: -1px;
  }
`;
