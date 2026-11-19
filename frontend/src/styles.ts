// Shared look (prototype variant D), built on HA's theme variables.
import { css } from "lit";

export const shared = css`
  :host {
    --wattbill-electricity: #f9a825;
    --wattbill-material: #26a69a;
    --wattbill-other: #7e57c2;
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
  .no-image {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 4 / 3;
    color: var(--secondary-text-color);
    background: var(--secondary-background-color, #ededed);
    font-size: 12px;
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
