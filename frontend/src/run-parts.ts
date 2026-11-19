// Pieces of a Run shown on both the gallery and the Run page.
import { html } from "lit";
import type { RunSummary } from "./api";
import type { Localize } from "./localize";

export const runName = (run: RunSummary, t: Localize) => run.name ?? t("run.untitled");

export const outcomeChip = (run: RunSummary, t: Localize) => {
  const outcome = run.ended === null ? "open" : (run.outcome ?? "unknown");
  return html`<span class="outcome ${outcome}">${t(`outcome.${outcome}`)}</span>`;
};
