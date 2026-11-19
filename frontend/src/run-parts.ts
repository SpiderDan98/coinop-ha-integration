// Pieces of a Run shown on both the gallery and the Run page.
import { html } from "lit";
import type { Device, Group, RunSummary, Totals } from "./api";
import type { Format } from "./format";
import type { Localize } from "./localize";

export const runName = (run: RunSummary, t: Localize) => run.name ?? t("run.untitled");

export const outcomeChip = (run: RunSummary, t: Localize) => {
  const outcome = run.ended === null ? "open" : (run.outcome ?? "unknown");
  return html`<span class="outcome ${outcome}">${t(`outcome.${outcome}`)}</span>`;
};

/** While the Devices are unknown, no Run (or group) counts as one of a removed Device. */
export const deviceName = (
  { device_id, device_name = "" }: Pick<Group, "device_id" | "device_name">,
  devices: Device[] | undefined,
  t: Localize,
) =>
  !devices || devices.some((device) => device.id === device_id)
    ? device_name
    : t("device.removed", { name: device_name });

/** Confirms deleting Runs, saying how much the sensor totals drop. */
export const deleteDialog = (
  title: string,
  drop: Totals,
  t: Localize,
  format: Format,
  { cancel, confirm }: { cancel: () => void; confirm: () => void },
) => {
  const rows = [
    [t("sensor.total_cost"), format.money(drop.cost)],
    [t("sensor.energy_in_runs"), format.quantity(drop.energy_kwh, "kWh")],
    [t("sensor.material_used"), format.quantity(drop.material_grams, "g")],
    [t("runs.title"), String(drop.runs)],
    [t("sensor.flagged_runs"), String(drop.flagged_runs)],
  ];
  return html`<div class="scrim">
    <div class="dialog card" role="alertdialog" aria-modal="true">
      <h2>${title}</h2>
      <p>${t("delete.drop")}</p>
      <dl>
        ${rows.map(
          ([label, value]) =>
            html`<dt>${label}</dt>
              <dd class="num">${value}</dd>`,
        )}
      </dl>
      <p class="muted small">${t("delete.warning")}</p>
      <div class="row end">
        <button class="btn cancel" @click=${cancel}>${t("delete.cancel")}</button>
        <button class="btn danger confirm" @click=${confirm}>${t("delete.confirm")}</button>
      </div>
    </div>
  </div>`;
};
