// Pieces of a Run shown on both the gallery and the Run page.
import { html } from "lit";
import type { Device, Group, RunSummary, Totals } from "./api";
import { confirmDialog } from "./dialog";
import type { Format } from "./format";
import { isKey, type Localize } from "./localize";

export const runName = (run: RunSummary, t: Localize) => run.name ?? t("run.untitled");

export const runCount = (count: number, t: Localize) =>
  count === 1 ? t("overview.run_one") : t("overview.runs", { count });

export const flagLabel = (flag: string, t: Localize) => {
  const key = `flag.${flag}`;
  return isKey(key) ? t(key) : flag;
};

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
    ...(drop.water_litres
      ? [[t("sensor.water_in_runs"), format.quantity(drop.water_litres, "L")]]
      : []),
    [t("runs.title"), String(drop.runs)],
    [t("sensor.flagged_runs"), String(drop.flagged_runs)],
  ];
  return confirmDialog({
    t,
    title,
    content: html`<p>${t("delete.drop")}</p>
      <dl>
        ${rows.map(
          ([label, value]) =>
            html`<dt>${label}</dt>
              <dd class="num">${value}</dd>`,
        )}
      </dl>
      <p class="muted small">${t("delete.warning")}</p>`,
    onCancel: cancel,
    onConfirm: confirm,
  });
};
