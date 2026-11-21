# Coin-op

A Home Assistant custom integration that records what each Run of your household devices costs, such as each print of a 3D printer or each program of a washing machine or dishwasher: electricity, water, material, detergent and anything else you add, kept as an editable history of Runs.

Coin-op is in early development. Releases before 1.0 are pre-releases for testing.

Requires Home Assistant 2026.5 or newer. Licensed under the [MIT licence](LICENSE).

Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does

- Each 3D printer you add becomes a **Device**. Coin-op reads its status (and, if available, job name, material used, loaded slots, thumbnail and camera) from the entities its printer integration already provides. The thumbnail can be an image entity or a camera that shows the print's preview, as Moonraker and PrusaLink offer it; a camera is asked for its picture while the print runs, never after it ended. It never talks to the printer itself, so any printer whose integration exposes a print status works. For the [printer integrations Coin-op has a profile for](#3d-printer-integration-profiles), the entities are filled in automatically.
- Each print becomes a **Run**, opened and closed by that status. While it runs you see a live cost; when it ends, its costs are frozen into **Line Items**: electricity (from an energy meter, a power sensor or an estimate from average power, priced correctly across every price change), material, and anything you add by hand or from templates, such as nozzle wear per running hour.
- A sidebar panel shows your Runs as a gallery and lets you correct every value of a Run afterwards.
- Each Device gets sensors for cost totals, material used, energy, Run count and running time, sensors for the current and last Run's cost, a Flagged Runs counter and a Run event entity for automations.
- Coin-op ships further Device Types besides the 3D printer: each load of a washing machine or dishwasher is a Run with electricity, water and the detergent and other products dosed into it. A Device none of them fits, such as garden irrigation, a CNC router or a bread maker, is added as **Other**: you name its kind and pick what it has. See [Device Types](#device-types).

## Device Types

The Device Type is chosen when a Device is added and can't be changed afterwards. It decides which setup steps the Device has and what its Runs record. Every Device has a Status that opens and closes its Runs and an electricity source with its price, and every Run takes Line Items you add by hand or from templates. The electricity source of every Device Type can also be [None](#electricity-source-none), for a Device whose electricity you don't follow.

| Device Type | A Run records | Pre-filled for |
|---|---|---|
| 3D printer | Electricity (energy meter, power sensor or an estimate from average power), the material used (per Slot with a multi-material unit), Part Count, Thumbnail and Snapshot | [Anycubic 3D Printer - Local Control, Anycubic Cloud & LAN, Bambu Lab, PrusaLink, OctoPrint, Creality, Elegoo, Moonraker](#3d-printer-integration-profiles) |
| Washing machine | Its Program, electricity and water (measured or per Program) and the Doses of detergent and other products | [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, LG ThinQ, SmartThings](#washing-machine-integration-profiles) |
| Dishwasher | Its Program, electricity and water (measured or per Program) and the Doses of tabs, salt and other products | [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, LG ThinQ, SmartThings](#washing-machine-integration-profiles) |
| Tumble dryer | Its Program, electricity (measured or per Program) and, if you list any, the Doses of dryer sheets or fragrance | [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, LG ThinQ, SmartThings](#washing-machine-integration-profiles) |
| Coffee machine | The drink as its Program, electricity and water (per Program or measured) and the Doses of beans, milk and other ingredients | [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt](#washing-machine-integration-profiles) |
| Oven | Its Program and electricity (measured or per Program) | [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, LG ThinQ, SmartThings](#washing-machine-integration-profiles) |
| EV charger | The electricity of a charging Run, from a session or lifetime energy sensor or a power sensor. See [EV chargers](#ev-chargers) | [Tesla Wall Connector, evcc, OCPP, Easee, Zaptec, go-e Charger MQTT, go-e Charger API v2, Wallbox](#ev-charger-integration-profiles) |
| Robotic mower | The electricity of a mowing Run, the recharge after it included. See [Robotic mowers](#robotic-mowers) | no integration: set up manually |
| Other | Its electricity and whatever you pick for it: a Program, Doses, water, a job with its Material, images, a Part Count. See [Other Devices](#other-devices) | no integration: set up manually |

**Other** is for a Device none of the shipped Device Types fits. You give it a Type Name and pick what it has yourself, and unlike the Device Type, both can be changed later.

"Pre-filled for" names the integrations Coin-op has an Integration Profile for: their devices are offered by [Quick Start](#quick-start), which adds each as the Device Type its integration says it is, and manual setup comes pre-filled for them whenever you pick a Device Type the integration is named for. A device of any other integration is set up manually, by picking its entities yourself.

A dishwasher has the same setup steps, Program Defaults, Doses, Flags, entities and manual Runs as a washing machine: everything under [Washing machines](#washing-machines) applies to it too.

So does a coffee machine. Each drink is a Run named after its Program, such as "Cappuccino", and beans and milk are Doses with an amount per drink in the Program Defaults, so a cappuccino costs more than an espresso. A Program's litres take amounts down to the millilitre: enter an espresso's 40 ml as 0.04.

Very short Runs, such as a coffee, are better priced "per Program" than from a meter. A metering plug counts in steps and reports at intervals that are coarse against a Run of under a minute, so what it measures for one drink is mostly chance. Choose "per Program" as the electricity source and give each drink its kWh in the Program Defaults.

A tumble dryer and an oven are set up like a washing machine without the water source and the water price. They have no water sensors, and their Run event's `ended` carries the Program but no litres. What [Washing machines](#washing-machines) says about the Program, the Program Defaults, Flags and manual Runs applies to both, with these differences:

- **Tumble dryer**: the Dose list is optional (dryer sheets, fragrance); an empty one adds nothing to a Run. Its Program Defaults have the kWh and a column per Dose, never litres.
- **Oven**: it has no Dose list. Its Program Defaults are just the kWh per Program, with rows suggested from the Program input and past Runs and the measured kWh suggested per Program, as for a washing machine.

## Installation

Coin-op is installed through HACS (Home Assistant 2026.10 and older) or the built-in Marketplace (Home Assistant 2026.11 and newer). Until it is in the default catalog, add it as a custom repository:

[![Open your Home Assistant instance and open this repository in HACS or the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SpiderDan98&repository=coinop-ha-integration&category=integration)

1. Select the badge above, or add `https://github.com/SpiderDan98/coinop-ha-integration` as a custom repository of type **Integration**. On the Marketplace this needs a GitHub connection.
2. Releases before 1.0 are pre-releases: turn on pre-releases for the repository to be offered them.
3. Download Coin-op. With HACS, restart Home Assistant afterwards; the Marketplace needs no restart for a first install. Updates always need a restart.
4. Go to **Settings > Devices & services > Add integration**, pick **Coin-op** and add your first Device.

## Quick Start

If the device you want to add already belongs to an integration Coin-op has an Integration Profile for ([3D printers](#3d-printer-integration-profiles), [WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, LG ThinQ and SmartThings](#washing-machine-integration-profiles), [EV chargers](#ev-charger-integration-profiles)), Add Device starts with **Quick Start**: it lists those devices, and picking one sets the Device up in two forms.

1. Pick the device. Its Device Type, its name and every Device Input the profile finds are taken over without further questions. Where the integration doesn't say what kind of device it is, Coin-op asks you for the Device Type instead of guessing, among those the integration is named for in the [Device Types](#device-types) table.
2. Check the Device Type the Device will be added as and the list of entities Coin-op found, then fill in what no profile knows:
   - the **energy meter or power sensor**, such as a metering plug's (its unit tells Coin-op which of the two it is). A washing machine, dishwasher, tumble dryer, coffee machine or oven may leave it empty and takes its kWh per Program from the Program Defaults; a printer without one is set up manually, where electricity can be estimated. A Miele washing machine, washer-dryer, dishwasher or tumble dryer and an EV charger with an energy counter bring their own meter and aren't asked, and neither is a SmartThings appliance that reports its energy.
   - the **electricity price**, fixed per kWh or from a price entity, pre-filled from the Device you added last.
   - for a Device Type with water (washing machine, dishwasher, coffee machine), optionally the **water price** per m³. With it, water comes from the Device's own meter or per Program from the Program Defaults; without it, no water is recorded.

The Device Type can't be changed once the Device is added. If the second form names the wrong one, close it and set the Device up manually: there you choose the Device Type yourself, and the steps still come pre-filled.

Which Device Type a device becomes:

- **WashData** knows the device type you picked when you set the device up there (or changed it to later): a washing machine or a washer-dryer becomes a Washing machine, a dryer a Tumble dryer, a dishwasher a Dishwasher. For its generic types ("Other (Advanced)" and "Threshold Device"), such as a plug on a coffee machine or an oven, Coin-op asks: Washing machine, Dishwasher, Tumble dryer, Coffee machine or Oven. A pump is no Device Type and isn't offered.
- **Miele** reports what each appliance is: a washing machine or a washer-dryer becomes a Washing machine, a tumble dryer a Tumble dryer, a dishwasher a Dishwasher, a coffee system a Coffee machine, and an oven, steam oven, combination oven, dialog oven or microwave an Oven. Its other appliances (fridges, freezers, hobs, hoods, wine cabinets, warming drawers, robot vacuums) are no Device Type and aren't offered.
- **Home Connect** doesn't say what kind an appliance is, so Coin-op tells it from the sensors Home Connect creates for each kind (they needn't be enabled): a washer or a washer-dryer becomes a Washing machine, a dryer a Tumble dryer, a dishwasher a Dishwasher, a coffee machine a Coffee machine, an oven or a microwave an Oven. Fridges, freezers, hobs, hoods and other appliances that are no Device Type aren't offered. For an appliance whose kind those sensors don't tell, Coin-op asks: Washing machine, Dishwasher, Tumble dryer, Coffee machine or Oven.
- For **Home Connect Local** and **Home Connect Alt**, Coin-op doesn't tell what kind an appliance is and asks for each of their appliances: Washing machine, Dishwasher, Tumble dryer, Coffee machine or Oven. An appliance that is none of them, such as a hood, is offered too; set it up manually instead, as another Device Type, or leave it.
- **LG ThinQ** writes the appliance's type into its model: a washer, a WashCombo or a WashTower's washer becomes a Washing machine, a dryer or a WashTower's dryer a Tumble dryer, a dishwasher a Dishwasher, an oven or a microwave an Oven. A Styler, air conditioners, fridges, purifiers, vacuums and its other appliances are no Device Type and aren't offered.
- **SmartThings** is told by the machine state SmartThings reports: a washer's becomes a Washing machine, a dryer's a Tumble dryer, a dishwasher's a Dishwasher, and an oven's an Oven, ranges and microwaves included. Its other devices (TVs, fridges, vacuums, an AirDresser and the rest) are no Device Type and aren't offered.

Everything Quick Start filled in can be checked and changed afterwards in the Device's reconfigure menu; the Doses and Program Defaults of a Device that has them are set on its card in the panel's Devices tab.

Choose **Set up manually** to walk every step yourself, for a device of any other integration or to map different entities. Devices Coin-op already follows aren't offered again.

## Estimating electricity without a meter

Without an energy meter or power sensor, CoinOp estimates electricity from the Device's average power while it runs. A desktop FDM printer with a heated bed typically averages 80–150 W over a whole print. Don't enter the rated power from the label or power supply: it is far higher than what the printer really draws on average. If you can, measure one print with a power-measuring plug and use that.

## Electricity source "None"

The electricity source menu of every Device ends with **None**, after the energy meter, the power sensor and, depending on the Device Type, the estimate from average power or "per Program". Pick it for a Device whose electricity you don't follow: one that only costs water, a Material or a flat amount per Run, or one you have no meter and no honest number for.

- **Runs**: new Runs get no Electricity Line Item and no Flag about electricity, and a Run doesn't wait for an electricity meter when it ends. Water, Doses, Material, Tags and automatic Line Item Templates work as for every Device, so a flat cost per Run is an automatic template. A manual Run gets no Electricity Line Item either.
- **Setup**: Add Device skips the electricity price, and the reconfigure menu offers the electricity source without the price. A Device with nothing else that is computed is a valid Device: its Runs cost nothing until Line Items are added by hand or by automatic templates.
- **Switching**: change the source to or from None in the reconfigure menu at any time. The change applies from the next Run; the open Run keeps the source it started with, and ended Runs never change. Picking a source again asks for the electricity price if the Device has none. A price you entered before is kept while the source is None and used again afterwards; the other settings of the old source (average powers, the meter and its conversion factor) are entered anew.
- **Program Defaults**: the kWh column and the measured kWh suggestions are hidden while the source is None. The kWh you entered are kept and shown again once the Device has a source. The litres and Dose columns stay as they are.
- **Electricity by hand**: on a Run without an Electricity Line Item, the Run page offers **Add electricity**, also while the Run is open. It adds one in kWh with the quantity and unit price you enter, marked as entered by hand. A Run takes one Electricity Line Item, so the button is gone once it has one; an entered one can be edited and deleted.
- **Panel, sensors and statements**: the Device's card shows "None" as its consumption source and no electricity price, and such a Run shows no Electricity card. The Device keeps its Electricity cost and Energy in Runs sensors, which count the electricity its Runs have, the Run event's `ended` reports an `energy_kwh` of 0, and a Cost Statement lists the Run without an electricity row.
- [Quick Start](#quick-start) never picks None: choose it in manual setup, or afterwards in the reconfigure menu.

None or an estimate? Estimate (or enter the kWh per Program) when electricity is a real part of what a Run costs and you know roughly how much, as for a printer without a meter. Pick None when it isn't a cost you want to see, as for a battery-driven or hand-operated Device or a negligible draw, or when any number would be made up. An average power of 0 W or a kWh default of 0 leaves a "0.00" Electricity Line Item on every Run; None leaves none.

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

## 3D printer Integration Profiles

[Quick Start](#quick-start) offers the printers of these integrations. When you set a Device up manually and pick a printer's Home Assistant device from one of them, every setup step comes pre-filled. Check each step and change what you like; Coin-op stores the entities themselves, not a link to the integration. Every profile also fills in the job name and the mapping of its Status.

| Integration | Status | Material used | Thumbnail | Camera | Slots |
|---|---|---|---|---|---|
| [Anycubic 3D Printer - Local Control](https://github.com/chrisfore/anycubic_ha_local) (`anycubic`) | Print event | Filament used, its `length_mm` attribute (mm) | Object top view (or Object thumbnail) | Camera, with Snapshot | ACE Slot 1–4, colour attribute `color`, Loaded slot |
| [Anycubic Cloud & LAN](https://github.com/Nino6689/hass-anycubic) (`anycubic_cloud`, 3.0 and 2.x) | Job state | Job filament used (mm) | Job preview (cloud mode only) | The local camera, with Snapshot | ACE Slot 1–4, colour attribute `color_hex`, ACE loaded slot |
| [Bambu Lab](https://github.com/greghesp/ha-bambulab) (`bambu_lab`) | Print status | Print weight (g) | Cover image | Camera, with Snapshot, where the printer has one | none |
| [PrusaLink](https://www.home-assistant.io/integrations/prusalink/) (`prusalink`) | Printer state | none | Job preview (a camera) | none | none |
| [OctoPrint](https://www.home-assistant.io/integrations/octoprint/) (`octoprint`) | Current state | none | none | OctoPrint camera, with Snapshot, where the webcam is enabled | none |
| [Creality](https://github.com/3dg1luk43/ha_creality_ws) (`ha_creality_ws`) | Print status; the job name is its `file` attribute | Used material length (cm) | Current print preview | Camera, with Snapshot | none |
| [Elegoo](https://github.com/danielcherubini/elegoo-homeassistant) (`elegoo_printer`) | Print status | Current extrusion (mm), where the printer has it | Cover image, where the printer has it | Chamber camera, with Snapshot | none |
| [Moonraker](https://github.com/marcolivierarsenault/moonraker-home-assistant) (`moonraker`) | Print state | Filament used (m) | Thumbnail (a camera) | The first webcam, with Snapshot | none |

- **Anycubic Cloud & LAN** 2.x in LAN mode goes from printing straight to idle, so its Runs end with Outcome Unknown.
- **Bambu Lab**: the preparation (heating, levelling) is part of the Run, a print stopped on the printer or one that failed ends as Cancelled, and the printer going offline during a print doesn't end the Run. The print weight is the slicer's planned figure for the whole print, not a measurement: a cancelled print is charged its full planned weight until you correct the Run's Material. Coin-op only takes a weight reported during the Run; with the integration connected through the cloud only, a print that is sliced in the cloud before it starts may report its weight before that, and its Run then asks you for the quantity. The AMS isn't read, so the weight is one Material Line Item of the Device's Default Material, and the AMS isn't offered as a Device of its own. Without the camera entity (the integration's camera turned off, or its chamber picture shown as an image) the Device has no camera and no Snapshot.
- **PrusaLink**: a printer that asks for attention during a print (a filament runout, for example) pauses the Run, which continues once the print does, and a stopped print ends as Cancelled. The integration reports no Material used, so add a Run's Material by hand or let an automatic Line Item Template add it. The job preview is fetched as the Thumbnail while the print runs; the integration has no webcam, so the Device has no camera and no Snapshot.
- **OctoPrint** has no state for a finished print: it goes from printing back to operational, so a finished print usually ends with Outcome Unknown and you set it to Completed yourself. Home Assistant asks OctoPrint every 30 seconds, and only when that catches OctoPrint's few seconds of finishing does the Run end as Completed. A cancelled print ends as Cancelled when the cancelling is caught the same way, otherwise with Outcome Unknown too. Sending a file to the SD card opens no Run. OctoPrint reports no Material used: add the Material to the Run by hand or with a Line Item Template.
- **Creality**: a print stopped on the printer ends as Cancelled; `processing`, the start of a print and the state a cancelled print stays in, and the self-test are left out of the Run. An error the printer reports holds the Run as paused with a fault Flag, and some printers never clear an error code, so a Run may not open until the error is cleared on the printer. The job name is the file's full path; the Run is named after the file alone. The used material length drops to 0 while the printer is unreachable or switched off, so a printer switched off within minutes of a print's end can leave its Run with 0 cm; correct the Run's Material then. The integration's current release needs Home Assistant 2026.7 or later. The integration registers a camera entity also on models that may have no camera; turn the Snapshot off there. Its unique ids contain the printer's address: the integration moves them to a new address itself, so Devices keep working, and Detect again repairs a Device if they ever don't match.
- **Elegoo**: resin and filament printers are both covered, with every state of the filament printers (they may stay on a step like "preheating completed" for a whole print, which is still part of the Run), a stopped print ends as Cancelled and a failed filament unload pauses the Run. Only filament printers with OpenCentauri firmware or the CC2 protocol report the extrusion, and printers connected over MQTT have no cover image. The chamber camera entity exists also for printers without a camera; turn the Snapshot off there.
- **Moonraker**: the Status is the print's state, not the printer's. The filament used is Klipper's measured extrusion of the print, not the lifetime total. The job name is the file's path in Klipper's folders; the Run is named after the file alone. The preview camera only shows a picture while the print runs, so Coin-op takes the Thumbnail then. A print that ends in `error` gets the Fault Flag and is paused; once Klipper is reset to standby (also at the start of the next print), the Run ends with Outcome Unknown. The integration adds a webcam camera even where the printer has none; disable that entity, or turn off the Snapshot, if the printer has no webcam.
- **Creality** and **Elegoo** preview pictures only get a state once something fetches them. Coin-op therefore asks for the picture itself when a Run starts and the picture has no state yet, and again each minute until it gets one, never after the Run ended.

If an update of the integration renames or replaces its entities, open the Device's reconfigure menu and choose **Detect again**. It walks the status, job and image steps pre-filled from the integration again and leaves the consumption source and price as they are.

## Using it with hass-anycubic

The hass-anycubic integration has cost sensors of its own (such as job energy, job electricity cost and last job total cost). Coin-op ignores them and computes every cost itself. Turn off one of the two cost features, for example by disabling hass-anycubic's cost entities, so your dashboards don't count the same print twice.

## Washing machines

Choose **Washing machine** as the Device Type when you add a Device. Like a printer, a washing machine is followed through entities its integration already provides: a Status opens and closes each load's Run, and its costs are frozen into Line Items when it ends. Coin-op doesn't detect wash cycles or programs itself.

A washing machine's Runs get these Line Items:

- **Electricity**, from an energy meter or a power sensor exactly as for printers, or "per Program" from the kWh in the Program Defaults. With the electricity source ["None"](#electricity-source-none) there is no Electricity Line Item, but you can add one by hand on a Run.
- **Water**, from a water meter or a flow sensor (any of Home Assistant's volume and flow units), or "per Program" from the litres in the Program Defaults. It is priced per m³ from a fixed value or a price entity (per m³ or per litre, sub-units such as ct/L included). Include the wastewater charge in the price. With the water source "None" there is no Water Line Item, but you can add one by hand on a Run.
- **Doses**: one Material Line Item for each detergent, fabric softener or other product the load uses.

The setup asks for the Status, its mapping, an optional Program input, the electricity source and price, and the water source and price. Part Count, Slots, Material used, Thumbnail and Camera don't apply to washing machines and aren't shown.

### Only a smart plug?

Install [WashData](https://github.com/3dg1luk43/ha_washdata) (`ha_washdata`). It detects cycles and programs from the power curve of a plug that measures power, and Coin-op takes the Status and the Program from it. Pick the plug's energy meter as the electricity source, and choose "per Program" for water: each load then gets the litres you set for its Program.

### Program

The optional Program input is the entity (or one of its attributes) that reports which program runs. Each Run records its Program and is named after it until you rename it. While the Run is open the Program follows the input, so a recognition that arrives late or gets corrected is picked up, and a change of Program never splits a load into two Runs. Values the input reports while it knows no program (a placeholder such as `detecting...`) can be listed as values to ignore: they count as no Program.

You can correct the Program of a Run on its page, also after it ended. The new Program's defaults then replace every Line Item that came from defaults and that you haven't changed: the kWh, the litres and the Doses (a Dose the new Program doesn't use disappears, one it uses appears). Measured, from-history and entered values, Doses measured by a stock input (also when it measured nothing used) and Doses you gave another Material stay as they are, a Flag you marked as checked stays checked, and saving the same Program again changes nothing.

### Program Defaults and Doses

Each washing machine's card in the panel's Devices tab has a Dose list and a Program Defaults table.

- **Materials**: detergents, fabric softeners and laundry additives are Materials in the Materials tab, like filament. Built-in types (liquid and powder detergent, pods, fabric softener, whitener, stain remover, colour catcher sheets) pre-fill a typical density. Pods and sheets are priced per piece: 40 pods for €12 cost €0.30 each. Dishwasher products and beverage ingredients are Material forms of their own, with built-in types for dishwasher tabs (priced per piece), dishwasher powder, dishwasher salt, rinse aid, coffee beans, ground coffee and milk; Materials of these two forms are never linked to Spoolman. Whatever fits none of these goes under the form **Other**: you name its type yourself, pick g, ml or pieces as the pack unit and enter its density unless it is bought by the piece. It has no built-in types and is never linked to Spoolman either.
- **Doses**: one entry per product that goes into the machine, each pointing to a Material. Each Dose a Run uses becomes its own Material Line Item.
- **Program Defaults**: one row per Program, with kWh, litres and an amount per Dose in the Material's unit (g, ml or pieces). A Run uses its Program's row, and the **Default** row when it has no Program or its Program has no row. An empty cell means "not set" (kWh, litres) or "not dosed" (Doses), so the whitener only shows up on the programs you use it with. kWh and litres only count when nothing measures them. Every amount is stored as entered; water of under a litre reads to the millilitre everywhere (0.04 L), larger amounts to a tenth of a litre as before.
- Rows are suggested from the values the Program input offers and from Programs seen on past Runs; a suggested row is stored once you enter a value.
- With a meter, a row suggests the average measured kWh and litres of that Program's completed Runs, with the number of Runs. One click applies it; it is never applied automatically.

Changes to the Program Defaults apply to the open Run at once and to future Runs, never to ended ones (only correcting a Run's Program re-applies them). Every amount stays editable on each Run, and each Dose shows where its amount came from: the Program's row, the Default row, a stock input or entered by hand.

### Measuring detergent with a stock input

A Dose can have a stock input: an entity that reports how much of the product is left, in a mass or volume unit, such as a scale under the bottle. The Dose's amount is then the decrease from the Run's start to its end; a refill during the load counts nothing. Coin-op waits up to 5 minutes after the end for a final report, and converts between g and ml through the Material's density. When the stock input reports nothing usable, the Program's amount is charged and the Run gets a Flag.

Some machines only report a fill level in %, such as Miele's TwinDos. Turn it into ml with the tank's size in a template sensor (replace the entity and the 1400 ml tank size with yours), then pick that sensor as the stock input:

```yaml
template:
  - sensor:
      - name: Detergent tank
        unique_id: detergent_tank_ml
        unit_of_measurement: mL
        device_class: volume_storage
        state_class: measurement
        availability: "{{ is_number(states('sensor.my_washer_detergent_level')) }}"
        state: "{{ (states('sensor.my_washer_detergent_level') | float * 1400 / 100) | round(0) }}"
```

A level in whole percent changes in steps of 1 % of the tank (14 ml here), so a single load's usage is only as exact as that.

### Flags on washing machine Runs

- **Ended early with defaults**: a Cancelled or Failed Run was charged water or Dose defaults meant for a whole Run. Lower them if it stopped early.
- **Default missing**: neither a measurement nor a Program Default gave a quantity; enter it on the Run.
- **Stock input unavailable**: a Dose's stock input reported nothing usable, so its default was charged.
- A meter that reported nothing during a load (and has no recorder history for it) falls back to the Program's kWh or litres and marks the Run with a consumption gap.

### Manual Runs, entities and statements

- A manual Run of a washing machine asks for its Program (a known one or free text). Electricity and water come from recorder history when a meter covers the period, else from the Program Defaults; Doses come from the Program Defaults. With a source "None" the manual Run has no Line Item of that kind.
- A washing machine's sensors are those of a printer, with **Water in Runs** (litres) and **Water cost** instead of Material used. Its Run event's `ended` carries the Program and the litres; Last Run cost carries the Program. Neither has a Part Count.
- The Overview and Analysis show Water as a cost kind, and the Analysis compares Programs by Run count and cost per Run. The Runs tab filters by Program.
- A Cost Statement shows each load's Program, Water and Doses, without Part Count.

### Washing machine Integration Profiles

[Quick Start](#quick-start) offers the washing machines, dishwashers, tumble dryers, coffee machines and ovens of these integrations, each as the Device Type it is. When you set one up manually, as the Device Type you choose, and pick its Home Assistant device from one of them, the Status, its mapping and the Program are pre-filled. Check each step and change what you like.

| Integration | Status | Program | Electricity | Water |
|---|---|---|---|---|
| [WashData](https://github.com/3dg1luk43/ha_washdata) (`ha_washdata`) | State sensor | Program sensor | your plug's energy meter, chosen by you | chosen by you |
| [Miele](https://www.home-assistant.io/integrations/miele/) (`miele`) | Status sensor | Program sensor | Energy consumption sensor of the current cycle, where the appliance has one | Water consumption sensor of the current cycle, where the appliance has one |
| [Home Connect](https://www.home-assistant.io/integrations/home_connect/) (`home_connect`) | Operation state sensor | Active program select | chosen by you | chosen by you |
| [Home Connect Local](https://github.com/chris-mc1/homeconnect_local_hass) (`homeconnect_ws`) | Operation state sensor | Active program sensor | chosen by you | chosen by you |
| [Home Connect Alt](https://github.com/ekutner/home-connect-hass) (`home_connect_alt`) | Operation state sensor | Active program sensor | chosen by you | chosen by you |
| [LG ThinQ](https://www.home-assistant.io/integrations/lg_thinq/) (`lg_thinq`) | Current status sensor | Current cycle sensor, on a dishwasher | chosen by you | chosen by you |
| [SmartThings](https://www.home-assistant.io/integrations/smartthings/) (`smartthings`) | Machine state sensor | none | Energy sensor, where the appliance reports one | chosen by you |

- WashData's profile also serves dishwashers, tumble dryers, coffee machines and ovens: its State and Program sensors are the same for every device it follows, so the Status, its mapping and the Program are pre-filled for each of these Device Types, in [Quick Start](#quick-start) and in manual setup.
- WashData's anti-wrinkle phase ends the Run as Completed, so a load ends when the washing is done, not when you open the door. WashData's own energy and cost sensors are ignored. Before it recognises the program, its program sensor reports placeholders such as `detecting...`; the profile fills them in as values to ignore (Program step), so they never become a Run's Program or a suggested Program row.
- Miele's profile also serves dishwashers, tumble dryers, coffee systems (as Coffee machines) and ovens, steam, combination and dialog ovens and microwaves included: the Status, its mapping and the Program are pre-filled for each of these Device Types, in [Quick Start](#quick-start) and in manual setup. The consumption sensors are pre-filled wherever the appliance has them: energy and water on a washing machine, washer-dryer and dishwasher, energy alone on a tumble dryer. A coffee system and an oven have neither, so pick a plug's meter or take the kWh per Program. A Miele microwave or dialog oven has a Program sensor that never reports a program, so its Runs have no Program unless you enter one.
- Miele's consumption sensors count the current cycle: they keep its total once the program has ended, have no value or read 0 while the appliance is off, and start the next cycle from 0. Coin-op keeps the reading at the Run's end, so that drop is neither lost nor counted twice, and it is never taken for a meter reset, whatever the Device Type. A counter that still has no value as the Run starts and then begins at 0 is no consumption gap either: nothing was counted before that 0. A counter whose first value is above 0, or one that loses its value during the Run, still marks the Run with a consumption gap.
- Home Connect's profile also serves dishwashers, tumble dryers, coffee machines and ovens: each of them has the same Operation state sensor and Active program select, so the Status, its mapping and the Program are pre-filled for each of these Device Types, in [Quick Start](#quick-start) and in manual setup.
- Home Connect Local's and Home Connect Alt's profiles serve the same five Device Types, with the same mapping as Home Connect's in the states each integration reports. Coin-op doesn't tell their appliances' kind, so [Quick Start](#quick-start) asks for the Device Type.
- Home Connect Alt reports the states in the mapping only with its translation mode "local", its default. With "server", it reports the state names translated into your language, which the pre-filled mapping doesn't match, so no Run opens: map the Status's states by hand in the Device's reconfigure menu. Its active program sensor appears only once the appliance has run a program while the integration was loaded; until then the Program is left empty, and **Detect again** fills it in later.
- LG ThinQ's profile serves washing machines, tumble dryers, dishwashers and ovens, not coffee machines. Every phase of a cycle (detecting, rinsing, spinning, drying, preheating and so on) keeps the Run running, so a cycle is one Run; `end` completes it, `cancel` cancels it and an error gives it its Flag. A dryer's wrinkle care completes the Run, like WashData's anti-wrinkle phase. Only a dishwasher reports what it runs, so the Program is pre-filled for a dishwasher alone. LG's energy sensors count per day and month, not per cycle, so they are no meter: pick a plug's meter or take the kWh per Program.
- An LG WashTower is two Home Assistant devices, one per half, and Quick Start offers each: the washer as a Washing machine, the dryer as a Tumble dryer. A TWINWash with its mini washer and a double oven report two Statuses on one Home Assistant device, and one Device follows one Status: Quick Start and manual setup read the main washer or the upper cavity; set the mini washer or the lower cavity up manually as a Device of its own.
- SmartThings' profile serves washing machines, tumble dryers, dishwashers and ovens, not coffee machines: the Status, its mapping and the energy sensor, where the appliance reports its energy, are pre-filled for each of them, in [Quick Start](#quick-start) and in manual setup. On a washer with a second, upper washer, or an oven with a second cavity, only the main one is read; set the other one up manually as a Device of its own. Known limits: every Run ends as Completed, since the machine state reads `stop` (an oven's `ready`) whether a cycle finished, was stopped or the appliance is idle; and there is no Program, so its Runs have none unless you enter one.
- **Detect again** in the reconfigure menu re-applies the Status, the mapping and the Program, and leaves electricity, water and prices as they are.

## EV chargers

Choose **EV charger** as the Device Type when you add a Device. A charging session is a Run: the charger's status opens and closes it, and its electricity is priced when it ends. The setup asks for the Status, its mapping, the electricity source and the electricity price, and nothing else: an EV charger has no Program, Doses or water. For the integrations [below](#ev-charger-integration-profiles) every step is pre-filled; for any other charger, pick its entities yourself.

- **Status**: the charger's status sensor. Map charging to Running, a car that is plugged in without charging (waiting, paused by load management or a solar surplus control, fully charged) to Paused, and the unplugged charger to Finished. The Run then lasts from the first charging until the car is unplugged, a break in charging doesn't split it, and its running time is the time the car really charged. To end the Run as soon as the car is full instead, map that value to Finished too.
- **Electricity source**: choose **Energy meter** and pick either the charger's session energy sensor (the energy of the current session, starting from 0 each time) or its lifetime energy sensor; both give the same kWh. Coin-op knows that an EV charger's meter may start every Run from 0, so the session sensor dropping back to 0 between two Runs is not taken for a meter reset, and one that has no value until the session starts and then begins at 0 is no consumption gap. A meter that has no value as the Run starts and comes back at any other reading, as a lifetime sensor does, gets the consumption gap Flag, and the Run counts from that reading on. A sensor that only drops once the next Run is already charging still counts that Run correctly, but the Run gets the meter reset Flag; the lifetime sensor avoids that. A **Power sensor** works too. There is no estimate and no "per Program" for an EV charger; [None](#electricity-source-none) follows its Runs without their electricity.
- **Electricity price**: a fixed price per kWh or a price entity. With a dynamic tariff, pick its price entity: each kWh is priced at what it cost when it was charged, so a Run over the cheap hours of the night costs what you really paid.

To tell cars apart, tag the Runs: set the usual car as the **Tags for new Runs** on the charger's card in the Devices tab and change the Tag on the Runs of another car. Automatic Line Item Templates work as for every Device. Filter the Runs tab by a Tag and select its Runs for a [Cost Statement](#cost-statement) of that car's Runs; it lists them without a Part Count.

An EV charger's sensors are those of a printer without Material used, and its Run event's `ended` carries neither Program, litres nor Part Count. A manual Run asks for its times and Outcome; its kWh come from recorder history when the meter covers the period, else you enter them.

### EV charger Integration Profiles

[Quick Start](#quick-start) offers the chargers of these integrations as EV chargers and asks for nothing but the electricity price. When you set one up manually as an EV charger and pick its Home Assistant device, the Status, its mapping and the electricity source are pre-filled. Check each step and change what you like.

| Integration | Status | Electricity |
|---|---|---|
| [Tesla Wall Connector](https://www.home-assistant.io/integrations/tesla_wall_connector/) (`tesla_wall_connector`) | Status sensor | Energy sensor (lifetime), else Session energy sensor |
| [evcc](https://github.com/marq24/ha-evcc) (`evcc_intg`), each loadpoint | Charging binary sensor | Charged energy (session), else Charge total import (the charger's meter) |
| [OCPP](https://github.com/lbbrhzn/ocpp) (`ocpp`), each connector | Status.Connector sensor | Energy.Active.Import.Register (the charger's meter), else Energy.Session |
| [Easee](https://github.com/nordicopen/easee_hass) (`easee`) | Status sensor | Lifetime energy sensor, else Session energy sensor |
| [Zaptec](https://github.com/custom-components/zaptec) (`zaptec`) | Charger operation mode sensor | Session total charge sensor, else Energy meter sensor (lifetime, only on chargers that report it) |
| [go-e Charger MQTT](https://github.com/syssi/homeassistant-goecharger-mqtt) (`goecharger_mqtt`) | Car state sensor | Total energy sensor (lifetime), else Charged energy sensor |
| [go-e Charger API v2](https://github.com/marq24/ha-goecharger-api2) (`goecharger_api2`) | Car state sensor (the text, not the code) | Energy total sensor (lifetime), else Energy since car connected sensor |
| [Wallbox](https://www.home-assistant.io/integrations/wallbox/) (`wallbox`) | Status description sensor | Added energy sensor (session; Wallbox has no lifetime counter) |

- The mapping follows the advice above: charging (also at reduced current) is Running; a car that is plugged in without charging (connected, ready, negotiating, waiting for the car, charging finished) is Paused; the unplugged charger is Finished, and an error is a Fault, which gives the Run its Flag. Booting is ignored.
- OCPP's mapping uses the connector statuses as OCPP spells them, for OCPP 1.6 and 2.0.1 charge points alike: `Charging` is Running; `Preparing`, `SuspendedEV`, `SuspendedEVSE` and `Finishing` are Paused; `Available` is Finished and `Faulted` a Fault. `Unavailable` and `Reserved` are ignored. A charge point with several connectors is offered once per connector, each with its own Status and meter; with one connector, the charge point itself is offered.
- evcc's Charging sensor is only on or off: on is Running and off is Finished. evcc doesn't say whether a car is still plugged in there, so **a session that evcc interrupts** (for want of solar surplus, by a plan or by the car) **is recorded as several Runs**. To keep such a session one Run, pick a Status of your own that tells charging, plugged in and unplugged apart, such as a template sensor over the loadpoint's Charging and Connected sensors, and map it as above. Each loadpoint is offered as its own EV charger.
- The electricity source is the charger's lifetime energy counter where the integration registers one and you haven't disabled it, else its session energy counter; with neither, Quick Start asks for a meter. The lifetime counter is preferred because it avoids the meter reset Flag a session counter can get. Two integrations are the exception and take the session counter first, the lifetime one only where you disabled it:
  - evcc registers the charger's meter for every loadpoint, also where the charger has none and it never reports.
  - Zaptec updates its Energy meter sensor only about once an hour, so a Run measured on it would miss the energy charged since the last update.
- Only a Zaptec charger is offered, not the installation it belongs to.
- Easee's further states follow the same advice: waiting for load balancing, a smart or scheduled start, authentication or the equalizer, and starting or stopping a charge are Paused; its specific errors (erratic EV, temperature too high, overcurrent and the like) are Faults; offline and searching for its master are ignored.
- go-e: waiting for the car and complete are Paused, idle is Finished, and an error, the unknown one included, is a Fault. go-e Charger API v2 reports the car state as a text in Home Assistant's language, German or else English; the mapping holds both.
- Wallbox: discharging to the home (V2G), paused, scheduled, every kind of waiting (for the car, in the Power Sharing, Power Boost or Eco-Smart queue, after a MID check) and locked with a car connected are Paused; ready and locked without a car are Finished. Disconnected is ignored, because Wallbox reports it both for an unplugged car and for a charger that lost its connection, and a dropout must not end the session; the unplugged charger reports ready next.
- The charger integration's own cost or price sensors are ignored: Coin-op computes every cost itself.
- **Detect again** in the reconfigure menu re-applies the Status and the mapping, and leaves the electricity source and the price as they are.

## Robotic mowers

Choose **Robotic mower** as the Device Type when you add a Device. A Run is one mowing trip together with the recharge it causes. The mower runs on its battery, so its electricity is what the charging station draws: put a metering plug in front of the charging station and pick its energy meter (or its power sensor) as the electricity source. The setup asks for the Status, its mapping, the electricity source and the electricity price, and nothing else. No integration is pre-filled, so pick the entities yourself.

Map the mower's Status like this:

| The mower is | Status mapping |
|---|---|
| mowing, returning to the charging station | Running |
| charging | Paused |
| parked (in the station, charged) | Ended |

- The Run stays open while the mower charges, so the electricity the charging station draws after mowing lands in the Run that caused it. Pauses don't count as running time, so the Run's running time is the mowing time without the charging.
- While the mower charges, its open Run is paused: its running time stands still and its electricity keeps counting.
- A mower that leaves again right after charging continues the same Run, so a day of mowing in several trips can be one Run. The Run ends once the mower is parked.
- Map a stop by hand to Paused and an error to Fault, as for a printer. Ended gives the Run the Outcome Unknown; map parked to Finished instead if you want these Runs to end as Completed.

This needs a Status that tells charging from parked. Many integrations report one value for both, such as `docked`: the Run would then end the moment the mower docks, without the electricity of its recharge. Give Coin-op a Status of your own in that case, in one of two ways:

- A **template helper** that combines the mower's state with what tells you it is charging, such as its battery level or a charging sensor: `charging` while it is docked and not full, `parked` once it is.
- **Following the charging station's plug**: the station draws clearly more power while it charges than while the mower is parked. The template sensor below reports `charging` while the mower is docked and the plug draws more than 5 W (set the threshold above your station's standby power). The first five minutes after docking count as charging too, so the Run doesn't end before the plug has reported the higher power:

```yaml
template:
  - sensor:
      - name: Mower status
        state: >
          {% if is_state('lawn_mower.my_mower', 'docked') %}
            {% set just_docked = now() - states.lawn_mower.my_mower.last_changed < timedelta(minutes=5) %}
            {{ 'charging' if just_docked or states('sensor.mower_station_power') | float(0) > 5 else 'parked' }}
          {% else %}
            {{ states('lawn_mower.my_mower') }}
          {% endif %}
```

Pick that sensor as the Device's Status. Line Item Templates per running hour, such as blade wear, then count the mowing time only, and Tags for new Runs work as for every Device. A robotic mower's sensors are those of a printer without Material used, and its Run event's `ended` carries neither Program, litres nor Part Count.

## Other Devices

Choose **Other**, the last entry of Add Device's Device Type step, for a Device Coin-op ships no Device Type for: garden irrigation, a CNC router or laser cutter, a bread maker, a kiln, a pool pump, a soda maker. Anything that has a Status to open and close its Runs can be followed this way.

An Other Device is put together from what the shipped Device Types are made of: a Program, Doses, water, a job with its Material, images, a Part Count. Add Device asks two things a shipped Device Type answers by itself: a **Type Name**, and **what the Device has**. After that it is a Device like every other: Add Device asks only for the steps your choices bring, its Runs get the Line Items they bring, and its card, its Runs' pages, its sensors and its Run event show exactly those.

When a shipped Device Type fits your Device, pick that one: only those are offered by [Quick Start](#quick-start) and come pre-filled for the integrations Coin-op knows. Pick Other when none fits, or when the one whose Runs record the right things would list the Device as something it isn't, such as an irrigation valve under "Washing machines".

No integration pre-fills an Other Device, and Quick Start never adds one. Where Add Device opens with Quick Start, choose **Set up manually** to get to the Device Type step. In every step you pick the entities yourself: any entity works, optionally one of its attributes, and so does a helper or a template sensor of your own. The reconfigure menu of an Other Device has no **Detect again**.

### Type Name

The Type Name is your own name for the kind of Device, such as "Irrigation" or "CNC router". The panel's Devices tab lists an Other Device under its Type Name as the heading, where a washing machine stands under "Washing machines". Other Devices with exactly the same Type Name share a heading, and every other Type Name gets a heading of its own. Add Device offers the Type Names you already gave, so a second Device of the same kind gets the same one without retyping it.

A Type Name is a heading and nothing more. Two Devices that share one may have different things switched on, and a Type Name that reads like a shipped Device Type's heading is still a group of its own.

### What the Device has

The step offers seven things to switch on. With nothing switched on, a Run records its running time and its electricity. Every combination works [but one](#what-cant-be-combined).

| Switch on | Add Device then asks for | A Run gets | Entities and Run event |
|---|---|---|---|
| **Program** | The Program step: the entity that reports which program runs, and its values to ignore | Its Program, and its name from it. Electricity that nothing measures comes from the Program's kWh in the Program Defaults | No entity of its own. The Run event's `ended` and Last Run cost carry the Program |
| **Doses** | Nothing. You list the Doses on the Device's card in the panel's Devices tab | One Material Line Item per Dose it uses, with the amount from the Program Defaults or a stock input | None |
| **Water** | The water source and the water price | A Water Line Item | The sensors **Water in Runs** (litres) and **Water cost**. `ended` carries the litres |
| **Job and Material** | The Job & Material step: the job name, Material used, Slot and Loaded slot entities, each optional | Its name from the job, and a Material Line Item: measured by the Device, or left for you to fill in | The sensor **Material used** (grams). `ended` carries the grams |
| **Images** | The Images step: a Thumbnail image or camera entity, a camera, and whether to take a Snapshot | The Thumbnail while it is open (an image entity is copied whenever it changes, a camera, or an image entity without a state yet, is asked for its picture at the start and a few times more while the Run runs, the latest kept) and a Snapshot from the camera when it ends | None |
| **Part Count** | Nothing | A Part Count, 1 until you change it on the Run, and with it a cost per part | No entity of its own. `ended` and Last Run cost carry the Part Count and the cost per part |
| **Meters count each Run from 0** | Nothing | No meter reset Flag when a meter is back at 0 after its end, and no consumption gap Flag when a meter without a value starts it at 0. See [below](#meters-count-each-run-from-0) | None |

Next to these, every Other Device has what every Device has: the Status and its mapping, an electricity source with its price, the sensors for cost totals, energy, Run count and running time, the current and last Run's cost, the Flagged Runs counter and the Run event.

Each choice works as it does on the shipped Device Type that has it:

- **Program**, **Doses** and **Water** are a washing machine's. What [Washing machines](#washing-machines) says about the Program, the Program Defaults, Doses, stock inputs and their Flags applies. The Program Defaults table on the Device's card has the columns the Device has: kWh with a Program, litres with a Program and Water, and one per Dose. With Doses and no Program the table is the Default row alone, which every Run uses.
- **Job and Material**, **Images** and **Part Count** are a 3D printer's, and Images and Part Count don't need a job: a kiln can have both. The Material used entity reports a length or a mass. Without one, each Run gets a Material Line Item with an empty quantity, in grams or, for a Material bought by the piece, in pieces, and a Flag until you enter it. The Line Item's Material is the **Default Material** you set on the Device's card, or the one in a Slot.
- Tags for new Runs and automatic Line Item Templates work as for every Device. A manual Run asks for the Program if the Device has one, and the Flags of a Run follow what the Device has: a Device without Job and Material is never asked for a Run's material.
- A Material that fits none of the other Material forms goes under the form **Other** in the Materials tab, with g, ml or pieces as its pack unit.

### Electricity and water sources

The electricity source menu of an Other Device depends on whether it has a Program:

| | Without a Program | With a Program |
|---|---|---|
| Measured | Energy meter, Power sensor | Energy meter, Power sensor |
| Not measured | **Estimate from average power** | **Per Program (kWh in the Program Defaults)** |
| Not followed | [None](#electricity-source-none) | [None](#electricity-source-none) |

- **Estimate from average power** multiplies the running time by the average power you enter. Enter what the Device draws on average over a whole Run, not the rated power on its label. See [Estimating electricity without a meter](#estimating-electricity-without-a-meter).
- **Per Program** takes the kWh of the Run's Program from the Program Defaults, and the Default row's for a Run without a Program or without a row of its own.
- The two are never offered together. A Device with a Program takes electricity that nothing measured from the Program's kWh, so there is exactly one way to get electricity without a meter.
- **None** is for a Device whose electricity you don't follow, such as a battery-driven valve. Its Runs get no Electricity Line Item, and Add Device skips the electricity price.

With **Water**, the water source is a water meter, a flow sensor or None, and with a Program also **Per Program (litres in the Program Defaults)**. Without a Program there is no default for water: it is measured, or you add it by hand on a Run. Water is priced per m³, from a fixed price or a price entity.

### Meters count each Run from 0

Switch this on when the energy or water meter you pick counts the current Run only: a session or per-cycle sensor that starts each Run at 0 and drops back to 0 once the Run is over.

Coin-op takes a meter that reads less than before for a meter reset. Such a Run is still counted correctly, but when the drop arrives in the minutes after the Run's end, while Coin-op waits for the meter's last report, the Run gets the meter reset Flag. With this switched on, a drop after the end of a Run is expected and raises no Flag.

Such a sensor often has no value at all between two Runs, and still has none at the moment the Status starts the next one. Coin-op takes a meter without a value at a Run's start for a consumption gap, since a meter that only counts up and comes back later may have counted in between. With this switched on, a meter that has no value as the Run starts and then begins at 0 raises no Flag: it counted nothing before that 0. A meter whose first value is above 0, one that loses its value during the Run or never has one, and a power or flow sensor without a value get the consumption gap Flag either way.

Leave it off for a meter that only counts up, such as a metering plug's total energy or a water meter on the supply: there a drop is a real reset, a meter that comes back at 0 after having no value lost what it counted, and the Flags are right. A counter that only drops once the next Run is already running gets that Run the Flag either way.

### What can't be combined

**Job and Material** can't be switched on together with **Program** or with **Doses**. The form refuses it and says why: the job and the Program would both name the Run, and a Dose's Material Line Item would take the place of the Run's own Material Line Item and of its Flags. Every other combination works, including none at all.

What to do instead:

- **A Material now and then**: leave Job and Material off. On any Run, whatever its Device has, **Add Material Line Item** on the Run's page adds one by hand: pick the Material and enter the quantity.
- **A product every Run uses**: that is a Dose. Switch on Doses and give it its amount, per Program if the Device has one.
- **A flat cost per Run**, such as wear or a blank that always costs the same: create a Line Item Template and add it to the **Automatic templates** on the Device's card. It is then added to every Run that starts there.
- **A job name and a Program**: switch on Program. A Run is named after its Program until you rename it, so you can still give it the job's name on its page.

### Worked examples

The amounts below assume an electricity price of €0.30 per kWh and a water price of €4.00 per m³.

#### Irrigation

A battery-driven valve on the garden tap. A Run is one watering and costs only its water.

1. Device Type **Other**, Type Name "Irrigation", switch on **Water**.
2. **Status**: the valve's entity, such as `switch.garden_valve`. Map `on` to Running and `off` to Finished.
3. **Electricity consumption**: **None**. The electricity price isn't asked for.
4. **Water consumption**: **Water meter**, with the meter on the garden line, then the water price per m³.

A watering of half an hour that takes 360 L is then a Run with one Line Item: Water, 360 L, €1.44. It has no Electricity Line Item, its `ended` event carries 360 litres and an `energy_kwh` of 0, and the Device has the Water in Runs and Water cost sensors. The Run is untitled until you name it.

- **No meter**: if you know what the valve lets through, a template sensor can report it as a flow. Pick it as the **Flow sensor** instead of a water meter; half an hour at 12 L/min is the same 360 L.

  ```yaml
  template:
    - sensor:
        - name: Garden valve flow
          unit_of_measurement: L/min
          state: "{{ 12 if is_state('switch.garden_valve', 'on') else 0 }}"
  ```

- **A meter that reports rarely**: Coin-op spreads what a meter counted between two reports evenly over that time. A meter that reports every litre or two is exact; one that reports every few minutes gives a short watering only a rough figure.
- **Several valves**: add one Device per valve, each with the valve's own entity as its Status, and give them the same Type Name. They share the heading "Irrigation", and they can share one water meter as long as they don't water at the same time.
- **A pump or a mains-powered valve**: pick a meter or the estimate from average power instead of None, and the Run gets an Electricity Line Item too.

#### A CNC router or laser cutter

A Run is one job: its name, the stock it used up, a Snapshot of what it made and the number of parts.

1. Device Type **Other**, Type Name "CNC router", switch on **Job and Material**, **Images** and **Part Count**.
2. **Status**: the controller's state entity. Map the value it reports while it cuts to Running, a feed hold to Paused and the value it returns to afterwards, such as `idle`, to Finished.
3. **Job & Material**: the entity that reports the name of the current job, if the controller has one. Leave Material used, the Slots and Loaded slot empty unless the Device reports them.
4. **Images**: a camera that looks at the bed as the Camera. Taking a Snapshot stays switched on.
5. **Electricity consumption**: the energy meter of a metering plug, or **Estimate from average power**, here with 300 W.
6. In the panel's Materials tab, add the stock as a Material of the form Other, such as "Plywood sheet", bought as 10 pieces for €40. On the Device's card in the Devices tab, set it as the Default Material.

A job "Shelf sides" of one hour is then a Run named "Shelf sides" with a Snapshot, a Part Count of 1 and two Line Items: Electricity, 0.3 kWh estimated, €0.09, and a Material Line Item for the plywood sheet with an empty quantity. The Run carries the Flag "No material usage was reported: enter the quantity". Enter 2 sheets and the Line Item costs €8.00, the Flag is gone and the Run costs €8.09. Set the Part Count to 4, the number of parts cut from the two sheets, and the Run shows €2.02 per part.

- A Device that reports what a job used up, as a length or a mass, takes that entity as Material used. The Material Line Item is then measured and needs no entering.
- Without a job name entity the Runs are untitled until you name them.
- The Material used sensor counts grams. Sheets entered by the piece count towards the Material cost sensor, not towards Material used.
- A laser cutter is set up the same way under its own Type Name.

#### A bread maker

A Run is one loaf: its Program, the electricity the Program takes and the ingredients that went in.

1. Device Type **Other**, Type Name "Bread maker", switch on **Program** and **Doses**.
2. **Status**: an entity that tells whether it bakes. Map that value to Running and the one after to Finished. A bread maker rarely has an integration, so this is usually a helper you set, a template on its plug's power, or the State sensor of [WashData](https://github.com/3dg1luk43/ha_washdata) on its plug.
3. **Program**: the entity that reports the program, such as a dropdown helper or WashData's Program sensor. List what it reports while it knows no program, such as `unknown` or `detecting...`, as values to ignore.
4. **Electricity consumption**: **Per Program**, or the plug's energy meter. Then the electricity price.
5. In the Materials tab, add the ingredients as Materials of the form Other: "Wheat flour" and "Wholemeal flour" by the gram, here 1000 g for €1.20 and for €1.60, and "Dry yeast" by the piece, 10 sachets for €2.00.
6. On the Device's card, add the three as Doses and fill in the Program Defaults:

   | Program | Electricity (kWh) | Wheat flour | Wholemeal flour | Dry yeast |
   |---|---|---|---|---|
   | Default | 0.3 | 500 | | 1 |
   | Whole wheat | 0.4 | | 500 | 1 |

A loaf on "Whole wheat" is then a Run named "Whole wheat" with three Line Items: Electricity, 0.4 kWh, €0.12, wholemeal flour, 500 g, €0.80, and dry yeast, 1 piece, €0.20, in all €1.12. A loaf on a Program without a row of its own, or without a Program, takes the Default row: 0.3 kWh, 500 g of wheat flour and one sachet, €0.89. An empty cell is not dosed, so the whole wheat loaf has no Line Item for wheat flour.

With the plug's energy meter as the electricity source, the measured kWh replace the Program's, and the Program Defaults suggest each Program's average once Runs have completed.

#### Further mixes

| Device | Switch on | Electricity source |
|---|---|---|
| Kiln | Part Count, and Images with a camera | Estimate from average power, or a meter |
| Pool pump | Nothing, or "Meters count each Run from 0" with a per-cycle energy sensor | Energy meter |
| Soda maker | Doses, for the CO₂ and the syrup, each with its amount in the Default row | None |

### Changing an Other Device later

The reconfigure menu of an Other Device starts with **Type Name & what it has**. It opens the step from Add Device, filled with what the Device has now. As for every section, nothing is saved until you choose Save, and closing the dialog halfway changes nothing.

The Device Type itself stays fixed: an Other Device never becomes a shipped Device Type and a shipped one never becomes Other. The reconfigure menu of a shipped Device Type has no such entry, and what it has can't be changed.

- **Only without an open Run.** The entry is refused while the Device has a Run that is still open, or one that has just ended and waits for the last reports of its meters, which takes five minutes at most. The dialog then closes with an explanation and nothing is saved, changes to other sections made in the same dialog included, so that no Run changes what it records halfway. Try again a few minutes after the Run has ended. That also holds while Coin-op isn't loaded, for a Run that was open when it stopped: the Run goes on when Coin-op is loaded again, so load it and let the Run end first.
- **The Type Name** can be changed alone, to fix a typo or to move the Device under another heading.
- **What you switch on** is asked for right away: Coin-op walks the steps the new choice brings, such as the water source and the water price, and then returns to the menu.
- **What you switch off** disappears from the menu, and the Device loses that choice's Device Inputs, its source and its price. Switching it on again later asks for them anew.
- **A source the Device can no longer use** is asked for again: the estimate from average power once the Device has a Program, and "per Program", for electricity or for water, once it has none. The prices stay. A source that is still offered is kept, so a Device on a meter stays on it; a power sensor loses the average running power that filled its gaps once the Device has a Program.
- **What is kept**: the Dose list, the Program Defaults and the Default Material stay stored while what they belong to is switched off. They are ignored meanwhile and apply again once it is switched back on. Tags for new Runs, automatic templates, the Device's name and every other section are untouched.
- **Runs**: ended Runs never change. Their Line Items, Program and Part Count stay as they were recorded, also where the panel no longer shows a field the Device has lost, such as the Program. Runs that start after the change follow what the Device has then.
- **Entities** follow the change: Water in Runs and Water cost appear with Water and are removed without it, and Material used likewise with Job and Material, so no dead entities are left behind. A sensor that comes back counts the Runs recorded before as well, because the totals are computed from the stored Runs.
- The combination that [can't be had](#what-cant-be-combined) is refused here as in Add Device.

## Spoolman

You can set a Spoolman URL in Coin-op's integration options. Materials can then be linked to a Spoolman Filament, so their price per gram comes from Spoolman, or be created from your Spoolman Filaments. When Spoolman can't be reached, the last price read is used and the Run gets a Flag.

## Cost Statement

Select ended Runs in the panel and download a Cost Statement: a PDF in English or German, detailed (every Line Item and the Cover Image per Run) or compact (one row per Run), optionally with a Markup on top. It opens with the total and how it splits into electricity, water, material and other costs. It is explicitly not an invoice. A default Markup can be set in the integration options. With exactly one Tag filtered, the title defaults to "Cost Statement – <Tag>". The browser remembers the last export options except title and note. The download works the way Home Assistant's own backup download does, so it also works from the Companion app.

## Currency

Cost sensors use the currency configured in Home Assistant. If you change that currency later, amounts are not converted: old and new amounts continue in the same sensors, and Home Assistant raises its own repair issue about the changed statistics unit.

## Your data

Coin-op keeps everything inside Home Assistant: its data files in `.storage/coinop.*` and its images in the `coinop` folder of the configuration directory. Both are part of Home Assistant backups, and restoring a backup brings all of Coin-op back to that moment. Sensor totals are rebuilt from the stored Runs at every start.

If the recorder database and Coin-op's data are restored from different points in time, the total sensors jump once in long-term statistics. Coin-op does not correct this.

If a data file can't be read (for example a corrupt file after a crash), Coin-op does not start, so it can't overwrite your history; a repair issue lets you restore a backup or deliberately start fresh.

Removing the Coin-op integration deletes all of its data: every data file, the `.bak` copies kept from before upgrades, and the `coinop` folder. Make a backup first if you may want it back.
