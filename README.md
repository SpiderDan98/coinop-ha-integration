# WattBill

A Home Assistant custom integration that records what each print of your 3D printers costs: electricity, material and anything else you add, kept as an editable history of Runs.

WattBill is in early development. Releases before 1.0 are pre-releases for testing.

Requires Home Assistant 2026.5 or newer. Licensed under the [MIT licence](LICENSE).

Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does

- Each 3D printer you add becomes a **Device**. WattBill reads its status (and, if available, job name, material used, loaded slots, thumbnail and camera) from the entities its printer integration already provides. It never talks to the printer itself, so any printer whose integration exposes a print status works. For the two Anycubic integrations that support the Kobra S1, the entities are filled in automatically.
- Each print becomes a **Run**, opened and closed by that status. While it runs you see a live cost; when it ends, its costs are frozen into **Line Items**: electricity (from an energy meter, a power sensor or an estimate from average power, priced correctly across every price change), material, and anything you add by hand or from templates, such as nozzle wear per running hour.
- A sidebar panel shows your Runs as a gallery and lets you correct every value of a Run afterwards.
- Each Device gets sensors for cost totals, material used, energy, Run count and running time, sensors for the current and last Run's cost, a Flagged Runs counter and a Run event entity for automations.

## Installation

WattBill is installed through HACS (Home Assistant 2026.10 and older) or the built-in Marketplace (Home Assistant 2026.11 and newer). Until it is in the default catalog, add it as a custom repository:

[![Open your Home Assistant instance and open this repository in HACS or the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SpiderDan98&repository=wattbill-ha-integration&category=integration)

1. Select the badge above, or add `https://github.com/SpiderDan98/wattbill-ha-integration` as a custom repository of type **Integration**. On the Marketplace this needs a GitHub connection.
2. Releases before 1.0 are pre-releases: turn on pre-releases for the repository to be offered them.
3. Download WattBill. With HACS, restart Home Assistant afterwards; the Marketplace needs no restart for a first install. Updates always need a restart.
4. Go to **Settings > Devices & services > Add integration**, pick **WattBill** and add your first Device.

## Estimating electricity without a meter

Without an energy meter or power sensor, WattBill estimates electricity from the Device's average power while it runs. A desktop FDM printer with a heated bed typically averages 80–150 W over a whole print. Don't enter the rated power from the label or power supply: it is far higher than what the printer really draws on average. If you can, measure one print with a power-measuring plug and use that.

## Monthly costs on a dashboard

The cost sensors are running totals that work with long-term statistics, so a statistic card can show what printing cost this month (replace the entity with your Device's Total cost sensor):

```yaml
type: statistic
entity: sensor.my_printer_total_cost
name: Printing this month
period:
  calendar:
    period: month
stat_type: change
```

For a bar per month, use a statistics graph card:

```yaml
type: statistics-graph
entities:
  - sensor.my_printer_total_cost
period: month
stat_types:
  - change
chart_type: bar
days_to_show: 365
```

Corrections and deleted Runs change the totals at the moment you make them, so they show up in that month rather than rewriting earlier ones.

## Anycubic printers

When you add a Device and pick a printer's Home Assistant device from one of these integrations, every setup step comes pre-filled. Check each step and change what you like; WattBill stores the entities themselves, not a link to the integration.

| Integration | Status | Material used | Thumbnail | Slots |
|---|---|---|---|---|
| [Anycubic 3D Printer - Local Control](https://github.com/chrisfore/anycubic_ha_local) (`anycubic`) | Print event | Filament used, its `length_mm` attribute (mm) | Object top view (or Object thumbnail) | ACE Slot 1–4, colour attribute `color`, Loaded slot |
| [Anycubic Cloud & LAN](https://github.com/Nino6689/hass-anycubic) (`anycubic_cloud`, 3.0 and 2.x) | Job state | Job filament used (mm) | Job preview (cloud mode only) | ACE Slot 1–4, colour attribute `color_hex`, ACE loaded slot |

Both also fill in the job name and the printer's local camera. With Anycubic Cloud & LAN 2.x in LAN mode a finished print goes straight to idle, so its Runs end with Outcome Unknown.

If an update of the integration renames or replaces its entities, open the Device's reconfigure menu and choose **Detect again**. It walks the status, job and image steps pre-filled from the integration again and leaves the consumption source and price as they are.

## Using it with hass-anycubic

The hass-anycubic integration has cost sensors of its own (such as job energy, job electricity cost and last job total cost). WattBill ignores them and computes every cost itself. Turn off one of the two cost features, for example by disabling hass-anycubic's cost entities, so your dashboards don't count the same print twice.

## Spoolman

You can set a Spoolman URL in WattBill's integration options. Materials can then be linked to a Spoolman Filament, so their price per gram comes from Spoolman, or be created from your Spoolman Filaments. When Spoolman can't be reached, the last price read is used and the Run gets a Flag.

## Cost Statement

Select ended Runs in the panel and download a Cost Statement: a PDF in English or German, detailed (every Line Item and the Cover Image per Run) or compact (one row per Run), optionally with a Markup on top. It is explicitly not an invoice. A default Markup can be set in the integration options. With exactly one Tag filtered, the title defaults to "Cost Statement – <Tag>". The browser remembers the last export options except title and note. The download works the way Home Assistant's own backup download does, so it also works from the Companion app.

## Currency

Cost sensors use the currency configured in Home Assistant. If you change that currency later, amounts are not converted: old and new amounts continue in the same sensors, and Home Assistant raises its own repair issue about the changed statistics unit.

## Your data

WattBill keeps everything inside Home Assistant: its data files in `.storage/wattbill.*` and its images in the `wattbill` folder of the configuration directory. Both are part of Home Assistant backups, and restoring a backup brings all of WattBill back to that moment. Sensor totals are rebuilt from the stored Runs at every start.

If the recorder database and WattBill's data are restored from different points in time, the total sensors jump once in long-term statistics. WattBill does not correct this.

If a data file can't be read (for example a corrupt file after a crash), WattBill does not start, so it can't overwrite your history; a repair issue lets you restore a backup or deliberately start fresh.

Removing the WattBill integration deletes all of its data: every data file, the `.bak` copies kept from before upgrades, and the `wattbill` folder. Make a backup first if you may want it back.
