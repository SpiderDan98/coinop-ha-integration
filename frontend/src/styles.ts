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
  /* HA's filled text field at ha-input's 56px; :where() lets the view controls' own
     rules win. */
  :where(input:not([type="checkbox"], [type="radio"], [type="file"]), select, textarea) {
    box-sizing: border-box;
    min-height: 56px;
    padding: 6px 16px;
    font: inherit;
    font-size: 14px;
    color: var(--primary-text-color);
    background-color: var(--ha-color-form-background, var(--secondary-background-color, #ededed));
    border: 0;
    border-bottom: 1px solid var(--input-idle-line-color, rgba(0, 0, 0, 0.42));
    border-radius: 4px 4px 0 0;
    outline: none;
  }
  /* The native arrow sits on the field's edge, so the select draws its own. */
  :where(select) {
    appearance: none;
    padding-inline-end: 38px;
    background-image:
      linear-gradient(45deg, transparent 50%, var(--secondary-text-color, #727272) 50%),
      linear-gradient(135deg, var(--secondary-text-color, #727272) 50%, transparent 50%);
    background-position:
      right 21px center,
      right 16px center;
    background-size: 5px 5px;
    background-repeat: no-repeat;
    text-overflow: ellipsis;
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
  .with-unit {
    display: flex;
    align-items: center;
    box-sizing: border-box;
    min-width: 0;
    min-height: 56px;
    background-color: var(--ha-color-form-background, var(--secondary-background-color, #ededed));
    border-bottom: 1px solid var(--input-idle-line-color, rgba(0, 0, 0, 0.42));
    border-radius: 4px 4px 0 0;
  }
  .with-unit:hover {
    border-bottom-color: var(--input-hover-line-color, rgba(0, 0, 0, 0.87));
  }
  .with-unit:focus-within {
    border-bottom-color: var(--primary-color);
    box-shadow: inset 0 -1px 0 var(--primary-color);
  }
  .with-unit:has(> [aria-invalid="true"]) {
    border-bottom-color: var(--error-color, #db4437);
    box-shadow: inset 0 -1px 0 var(--error-color, #db4437);
  }
  .with-unit > input {
    flex: 1;
    align-self: stretch;
    width: 100%;
    min-width: 0;
    min-height: 0;
    padding-inline-end: 4px;
    background: none;
    border: 0;
    box-shadow: none;
  }
  .with-unit > .unit {
    flex: none;
    padding-inline-end: 16px;
    font-size: 12px;
    color: var(--secondary-text-color);
    white-space: nowrap;
  }
  .with-unit:has(> :disabled) > .unit {
    opacity: 0.6;
  }
  input[type="checkbox"],
  input[type="radio"] {
    accent-color: var(--primary-color);
  }
  /* A data field (src/fields.ts) is as wide as its dialog; the fields of a .field-row
     share the width evenly. */
  .field,
  .field > label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .field .label,
  .field > .hint {
    font-size: 12px;
    color: var(--secondary-text-color);
  }
  .field
    :where(
      input:not([type="checkbox"], [type="radio"], [type="color"]),
      select,
      textarea,
      .with-unit,
      coinop-tag-input
    ) {
    width: 100%;
    min-width: 0;
  }
  .field-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 12px;
  }
  .field-row > * {
    flex: 1 1 160px;
    min-width: 0;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .error {
    color: var(--error-color, #db4437);
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
