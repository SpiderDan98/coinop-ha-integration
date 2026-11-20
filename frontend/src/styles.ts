// Shared look (prototype variant D), built on HA's theme variables.
import { css } from "lit";

export const shared = css`
  :host {
    --coinop-electricity: #f9a825;
    --coinop-water: #1e88e5;
    --coinop-material: #26a69a;
    --coinop-other: #7e57c2;
    --coinop-manual: #7e57c2;
    color: var(--primary-text-color);
    font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
    font-size: 14px;
  }
  h1 {
    font-size: 22px;
    font-weight: 500;
    margin: 0 0 6px;
  }
  h2 {
    font-size: 18px;
    font-weight: 500;
    margin: 0;
  }
  h3 {
    font-size: 15px;
    font-weight: 500;
    margin: 0;
  }
  a {
    color: var(--primary-color);
    text-decoration: none;
  }
  .muted {
    color: var(--secondary-text-color);
  }
  .small {
    font-size: 12px;
  }
  .strong {
    font-weight: 500;
  }
  .ellipsis {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .between {
    justify-content: space-between;
  }
  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .card {
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
    border-radius: 12px;
    padding: 16px;
  }
  /* HA's filled text field (ha-input is 56px); :where() lets every page's own field rules win. */
  :where(input:not([type="checkbox"], [type="radio"], [type="file"]), select, textarea) {
    box-sizing: border-box;
    min-height: 56px;
    padding: 8px 16px;
    font: inherit;
    font-size: 14px;
    color: var(--primary-text-color);
    background: var(--ha-color-form-background, var(--secondary-background-color, #ededed));
    border: 0;
    border-bottom: 1px solid var(--input-idle-line-color, rgba(0, 0, 0, 0.42));
    border-radius: 4px 4px 0 0;
    outline: none;
  }
  :where(input:not([type="checkbox"], [type="radio"], [type="file"]), select, textarea):hover {
    border-bottom-color: var(--input-hover-line-color, rgba(0, 0, 0, 0.87));
  }
  :where(
    input:not([type="checkbox"], [type="radio"], [type="file"]),
    select,
    textarea
  ):focus-visible {
    border-bottom-color: var(--primary-color);
    box-shadow: inset 0 -1px 0 var(--primary-color);
  }
  :where(input, select, textarea)[aria-invalid="true"] {
    border-bottom-color: var(--error-color, #db4437);
    box-shadow: inset 0 -1px 0 var(--error-color, #db4437);
  }
  :where(textarea) {
    resize: vertical;
  }
  input[type="checkbox"],
  input[type="radio"] {
    accent-color: var(--primary-color);
  }
  /* As HA's floating action button, built from ha-button since ha-fab may not be loaded. */
  ha-button.fab {
    position: fixed;
    z-index: 3;
    inset-inline-end: calc(16px + var(--safe-area-inset-right, 0px));
    bottom: calc(16px + var(--safe-area-inset-bottom, 0px));
    --ha-button-height: 48px;
    border-radius: 9999px;
    box-shadow:
      0 6px 12px -3px rgba(0, 0, 0, 0.4),
      0 16px 32px -6px rgba(0, 0, 0, 0.55);
  }
  /* HA's size="small" became size="s" in 2026.11, so the height is set directly. */
  ha-button.small {
    --ha-button-height: 32px;
  }
  .dialog p {
    margin: 0;
  }
  .dialog dl {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px 16px;
    margin: 0;
  }
  .dialog dd {
    margin: 0;
  }
  .end {
    justify-content: flex-end;
  }
  .no-image {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 4 / 3;
    color: var(--secondary-text-color);
    background: var(--secondary-background-color, #ededed);
    font-size: 12px;
  }
  .tag-chip {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    font-size: 12px;
    padding: 1px 8px;
    border-radius: 10px;
    white-space: nowrap;
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 12%, transparent);
  }
  .tag-chip .tag-name {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .outcome {
    display: inline-block;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 10px;
    white-space: nowrap;
    background: var(--secondary-background-color, #ededed);
    color: var(--secondary-text-color);
  }
  .outcome.completed {
    background: color-mix(in srgb, var(--success-color, #43a047) 16%, transparent);
    color: var(--success-color, #43a047);
  }
  .outcome.failed {
    background: color-mix(in srgb, var(--error-color, #db4437) 16%, transparent);
    color: var(--error-color, #db4437);
  }
  .outcome.unknown {
    background: color-mix(in srgb, var(--warning-color, #ffa600) 18%, transparent);
    color: var(--warning-color, #ffa600);
  }
  .outcome.open {
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 16%, transparent);
    color: var(--primary-color, #03a9f4);
  }
`;
