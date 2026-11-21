// A Device's settings dialog on the Devices tab, and the Program Defaults table in it.
import type { Device } from "../src/api";
import { click, iconButton, query, queryAll, text } from "./render";

export const openDialog = async (panel: Element, device: Pick<Device, "name">) => {
  await click(panel, iconButton(panel, `Edit settings of ${device.name}`));
  return query(panel, ".settings-dialog");
};
export const headers = (dialog: Element) => queryAll(dialog, ".program-defaults th").map(text);
export const rows = (dialog: Element) => queryAll(dialog, ".program-defaults tbody tr").map(text);
export const input = (root: Element, label: string) =>
  query(root, `input[aria-label="${label}"]`) as HTMLInputElement;
