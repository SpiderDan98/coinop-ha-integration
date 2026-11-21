# Coin-op

A Home Assistant custom integration that records what each Run of your household devices costs, such as each print of a 3D printer or each program of a washing machine or dishwasher: electricity, water, material, detergent and anything else you add, kept as an editable history of Runs.

Coin-op is in early development. Releases before 1.0 are pre-releases for testing.

Requires Home Assistant 2026.5 or newer. Licensed under the [MIT licence](LICENSE).

Contributing: see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does

- Each 3D printer you add becomes a **Device**. Coin-op reads its status (and, if available, job name, material used, loaded slots, thumbnail and camera) from the entities its printer integration already provides. It never talks to the printer itself, so any printer whose integration exposes a print status works. For the two Anycubic integrations that support the Kobra S1, the entities are filled in automatically.
- Each print becomes a **Run**, opened and closed by that status. While it runs you see a live cost; when it ends, its costs are frozen into **Line Items**: electricity (from an energy meter, a power sensor or an estimate from average power, priced correctly across every price change), material, and anything you add by hand or from templates, such as nozzle wear per running hour.
- A sidebar panel shows your Runs as a gallery and lets you correct every value of a Run afterwards.
- Each Device gets sensors for cost totals, material used, energy, Run count and running time, sensors for the current and last Run's cost, a Flagged Runs counter and a Run event entity for automations.
- Other appliances are Device Types of their own: each load of a washing machine or dishwasher is a Run with electricity, water and the detergent and other products dosed into it. See [Device Types](#device-types).

## Device Types

The Device Type is chosen when a Device is added and can't be changed afterwards. It decides which setup steps the Device has and what its Runs record. Every Device has a Status that opens and closes its Runs and an electricity source and price, and every Run takes Line Items you add by hand or from templates.

| Device Type | A Run records | Pre-filled for |
|---|---|---|
| 3D printer | Electricity (energy meter, power sensor or an estimate from average power), the material used (per Slot with a multi-material unit), Part Count, Thumbnail and Snapshot | [Anycubic 3D Printer - Local Control, Anycubic Cloud & LAN](#anycubic-printers) |
| Washing machine | Its Program, electricity and water (measured or per Program) and the Doses of detergent and other products | [WashData, Miele, Home Connect](#washing-machine-integration-profiles) |
| Dishwasher | Its Program, electricity and water (measured or per Program) and the Doses of tabs, salt and other products | no integration yet: set up manually |
| Tumble dryer | Its Program, electricity (measured or per Program) and, if you list any, the Doses of dryer sheets or fragrance | no integration yet: set up manually |
| Coffee machine | The drink as its Program, electricity and water (per Program or measured) and the Doses of beans, milk and other ingredients | no integration yet: set up manually |
| Oven | Its Program and electricity (measured or per Program) | no integration yet: set up manually |
| EV charger | The electricity of a charging session, from a session or lifetime energy sensor or a power sensor. See [EV chargers](#ev-chargers) | no integration: set up manually |
| Robotic mower | The electricity of a mowing Run, the recharge after it included. See [Robotic mowers](#robotic-mowers) | no integration: set up manually |

"Pre-filled for" names the integrations Coin-op has an Integration Profile for: their devices are offered by [Quick Start](#quick-start), and manual setup comes pre-filled for them. A device of any other integration is set up manually, by picking its entities yourself.

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

If the device you want to add already belongs to an integration Coin-op has an Integration Profile for ([Anycubic printers](#anycubic-printers), [washing machines](#washing-machine-integration-profiles)), Add Device starts with **Quick Start**: it lists those devices, and picking one sets the Device up in two forms.

1. Pick the device. Its Device Type, its name and every Device Input the profile finds are taken over without further questions.
2. Check the list of entities Coin-op found, then fill in what no profile knows:
   - the **energy meter or power sensor**, such as a metering plug's (its unit tells Coin-op which of the two it is). A washing machine may leave it empty and takes its kWh per Program from the Program Defaults; a printer without one is set up manually, where electricity can be estimated. A Miele washing machine brings its own meters and isn't asked.
   - the **electricity price**, fixed per kWh or from a price entity, pre-filled from the Device you added last.
   - for a washing machine, optionally the **water price** per m³. With it, water comes from the machine's own meter or per Program from the Program Defaults; without it, no water is recorded.

Everything Quick Start filled in can be checked and changed afterwards in the Device's reconfigure menu; a washing machine's Doses and Program Defaults are set on its card in the panel's Devices tab. Miele and Home Connect also list their other appliances: pick only the ones you want to follow as a washing machine.

Choose **Set up manually** to walk every step yourself, for a device of any other integration or to map different entities. Devices Coin-op already follows aren't offered again.

## Estimating electricity without a meter

Without an energy meter or power sensor, CoinOp estimates electricity from the Device's average power while it runs. A desktop FDM printer with a heated bed typically averages 80–150 W over a whole print. Don't enter the rated power from the label or power supply: it is far higher than what the printer really draws on average. If you can, measure one print with a power-measuring plug and use that.

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

[Quick Start](#quick-start) offers the printers of these integrations. When you set a Device up manually and pick a printer's Home Assistant device from one of them, every setup step comes pre-filled. Check each step and change what you like; Coin-op stores the entities themselves, not a link to the integration.

| Integration | Status | Material used | Thumbnail | Slots |
|---|---|---|---|---|
| [Anycubic 3D Printer - Local Control](https://github.com/chrisfore/anycubic_ha_local) (`anycubic`) | Print event | Filament used, its `length_mm` attribute (mm) | Object top view (or Object thumbnail) | ACE Slot 1–4, colour attribute `color`, Loaded slot |
| [Anycubic Cloud & LAN](https://github.com/Nino6689/hass-anycubic) (`anycubic_cloud`, 3.0 and 2.x) | Job state | Job filament used (mm) | Job preview (cloud mode only) | ACE Slot 1–4, colour attribute `color_hex`, ACE loaded slot |

Both also fill in the job name and the printer's local camera. With Anycubic Cloud & LAN 2.x in LAN mode a finished print goes straight to idle, so its Runs end with Outcome Unknown.

If an update of the integration renames or replaces its entities, open the Device's reconfigure menu and choose **Detect again**. It walks the status, job and image steps pre-filled from the integration again and leaves the consumption source and price as they are.

## Using it with hass-anycubic

The hass-anycubic integration has cost sensors of its own (such as job energy, job electricity cost and last job total cost). Coin-op ignores them and computes every cost itself. Turn off one of the two cost features, for example by disabling hass-anycubic's cost entities, so your dashboards don't count the same print twice.

## Washing machines

Choose **Washing machine** as the Device Type when you add a Device. Like a printer, a washing machine is followed through entities its integration already provides: a Status opens and closes each load's Run, and its costs are frozen into Line Items when it ends. Coin-op doesn't detect wash cycles or programs itself.

A washing machine's Runs get these Line Items:

- **Electricity**, from an energy meter or a power sensor exactly as for printers, or "per Program" from the kWh in the Program Defaults.
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

- **Materials**: detergents, fabric softeners and laundry additives are Materials in the Materials tab, like filament. Built-in types (liquid and powder detergent, pods, fabric softener, whitener, stain remover, colour catcher sheets) pre-fill a typical density. Pods and sheets are priced per piece: 40 pods for €12 cost €0.30 each. Dishwasher products and beverage ingredients are Material forms of their own, with built-in types for dishwasher tabs (priced per piece), dishwasher powder, dishwasher salt, rinse aid, coffee beans, ground coffee and milk; Materials of these two forms are never linked to Spoolman.
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

- A manual Run of a washing machine asks for its Program (a known one or free text). Electricity and water come from recorder history when a meter covers the period, else from the Program Defaults; Doses come from the Program Defaults.
- A washing machine's sensors are those of a printer, with **Water in Runs** (litres) and **Water cost** instead of Material used. Its Run event's `ended` carries the Program and the litres; Last Run cost carries the Program. Neither has a Part Count.
- The Overview and Analysis show Water as a cost kind, and the Analysis compares Programs by Run count and cost per Run. The Runs tab filters by Program.
- A Cost Statement shows each load's Program, Water and Doses, without Part Count.

### Washing machine Integration Profiles

[Quick Start](#quick-start) offers the washing machines of these integrations. When you set one up manually and pick its Home Assistant device from one of them, the Status, its mapping and the Program are pre-filled. Check each step and change what you like.

| Integration | Status | Program | Electricity | Water |
|---|---|---|---|---|
| [WashData](https://github.com/3dg1luk43/ha_washdata) (`ha_washdata`) | State sensor | Program sensor | your plug's energy meter, chosen by you | chosen by you |
| [Miele](https://www.home-assistant.io/integrations/miele/) (`miele`) | Status sensor | Program sensor | Energy consumption sensor of the current cycle | Water consumption sensor of the current cycle |
| [Home Connect](https://www.home-assistant.io/integrations/home_connect/) (`home_connect`) | Operation state sensor | Active program select | chosen by you | chosen by you |

- WashData's anti-wrinkle phase ends the Run as Completed, so a load ends when the washing is done, not when you open the door. WashData's own energy and cost sensors are ignored. Before it recognises the program, its program sensor reports placeholders such as `detecting...`; the profile fills them in as values to ignore (Program step), so they never become a Run's Program or a suggested Program row.
- Miele's consumption sensors count the current cycle and drop to 0 afterwards. Coin-op keeps the reading at the load's end, so that drop is neither lost nor counted twice.
- **Detect again** in the reconfigure menu re-applies the Status, the mapping and the Program, and leaves electricity, water and prices as they are.

## EV chargers

Choose **EV charger** as the Device Type when you add a Device. A charging session is a Run: the charger's status opens and closes it, and its electricity is priced when it ends. The setup asks for the Status, its mapping, the electricity source and the electricity price, and nothing else: an EV charger has no Program, Doses or water. No integration is pre-filled, so pick your charger's entities yourself.

- **Status**: the charger's status sensor. Map charging to Running, a car that is plugged in without charging (waiting, paused by load management or a solar surplus control, fully charged) to Paused, and the unplugged charger to Finished. The Run then lasts from the first charging until the car is unplugged, a break in charging doesn't split it, and its running time is the time the car really charged. To end the Run as soon as the car is full instead, map that value to Finished too.
- **Electricity source**: choose **Energy meter** and pick either the charger's session energy sensor (the energy of the current session, starting from 0 each time) or its lifetime energy sensor; both give the same kWh. Coin-op knows that an EV charger's meter may start every Run from 0, so the session sensor dropping back to 0 between two sessions is not taken for a meter reset. A sensor that only drops once the next session is already charging still counts that session correctly, but its Run gets the meter reset Flag; the lifetime sensor avoids that. A **Power sensor** works too. There is no estimate and no "per Program" for an EV charger.
- **Electricity price**: a fixed price per kWh or a price entity. With a dynamic tariff, pick its price entity: each kWh is priced at what it cost when it was charged, so a session over the cheap hours of the night costs what you really paid.

To tell cars apart, tag the sessions: set the usual car as the **Tags for new Runs** on the charger's card in the Devices tab and change the Tag on the Runs of another car. Automatic Line Item Templates work as for every Device. Filter the Runs tab by a Tag and select its Runs for a [Cost Statement](#cost-statement) of that car's sessions; it lists them without a Part Count.

An EV charger's sensors are those of a printer without Material used, and its Run event's `ended` carries neither Program, litres nor Part Count. A manual Run asks for its times and Outcome; its kWh come from recorder history when the meter covers the period, else you enter them.

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

## Spoolman

You can set a Spoolman URL in Coin-op's integration options. Materials can then be linked to a Spoolman Filament, so their price per gram comes from Spoolman, or be created from your Spoolman Filaments. When Spoolman can't be reached, the last price read is used and the Run gets a Flag.

## Cost Statement

Select ended Runs in the panel and download a Cost Statement: a PDF in English or German, detailed (every Line Item and the Cover Image per Run) or compact (one row per Run), optionally with a Markup on top. It is explicitly not an invoice. A default Markup can be set in the integration options. With exactly one Tag filtered, the title defaults to "Cost Statement – <Tag>". The browser remembers the last export options except title and note. The download works the way Home Assistant's own backup download does, so it also works from the Companion app.

## Currency

Cost sensors use the currency configured in Home Assistant. If you change that currency later, amounts are not converted: old and new amounts continue in the same sensors, and Home Assistant raises its own repair issue about the changed statistics unit.

## Your data

Coin-op keeps everything inside Home Assistant: its data files in `.storage/coinop.*` and its images in the `coinop` folder of the configuration directory. Both are part of Home Assistant backups, and restoring a backup brings all of Coin-op back to that moment. Sensor totals are rebuilt from the stored Runs at every start.

If the recorder database and Coin-op's data are restored from different points in time, the total sensors jump once in long-term statistics. Coin-op does not correct this.

If a data file can't be read (for example a corrupt file after a crash), Coin-op does not start, so it can't overwrite your history; a repair issue lets you restore a backup or deliberately start fresh.

Removing the Coin-op integration deletes all of its data: every data file, the `.bak` copies kept from before upgrades, and the `coinop` folder. Make a backup first if you may want it back.
