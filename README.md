# WattBill

A Home Assistant custom integration that records what each print of your 3D printers costs: electricity, material and anything else you add, kept as an editable history of Runs.

WattBill is in early development and not ready for use yet.

Requires Home Assistant 2026.5 or newer. Licensed under the [MIT licence](LICENSE).

Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Your data

WattBill keeps everything inside Home Assistant: its data files in `.storage/wattbill.*` and its images in the `wattbill` folder of the configuration directory. Both are part of Home Assistant backups, and restoring a backup brings all of WattBill back to that moment.

If a data file can't be read (for example a corrupt file after a crash), WattBill does not start, so it can't overwrite your history; a repair issue lets you restore a backup or deliberately start fresh.

Removing the WattBill integration deletes all of its data: every data file, the `.bak` copies kept from before upgrades, and the `wattbill` folder. Make a backup first if you may want it back.
