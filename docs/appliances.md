# Washing machines and other appliances

## Washing machines

Choose **Washing machine** as the Device Type when you add a Device. Like a printer, a washing machine is followed through entities its integration already provides: a Status opens and closes each load's Run, and its costs are frozen into Line Items when it ends. Coin-op doesn't detect wash cycles or programs itself.

A washing machine's Runs get these Line Items:

- **Electricity**, from an energy meter or a power sensor exactly as for printers, or "per Program" from the kWh in the Program Defaults. With the electricity source ["None"](electricity.md#electricity-source-none) there is no Electricity Line Item, but you can add one by hand on a Run.
- **Water**, from a water meter or a flow sensor (any of Home Assistant's volume and flow units), or "per Program" from the litres in the Program Defaults. It is priced per m³ from a fixed value or a price entity (per m³ or per litre, sub-units such as ct/L included). Include the wastewater charge in the price. With the water source "None" there is no Water Line Item, but you can add one by hand on a Run.
- **Doses**: one Material Line Item for each detergent, fabric softener or other product the load uses.

The setup asks for the Status, its mapping, an optional Program input, the electricity source and price, and the water source and price. Part Count, Slots, Material used, Thumbnail and Camera don't apply to washing machines and aren't shown. For the [supported integrations](supported-integrations.md#washing-machines-and-other-appliances), the Status, its mapping and the Program are pre-filled.

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

## Dishwashers

A dishwasher has the same setup steps, Program Defaults, Doses, Flags, entities and manual Runs as a washing machine: everything under [Washing machines](#washing-machines) applies to it too.

## Coffee machines

A coffee machine has them too. Each drink is a Run named after its Program, such as "Cappuccino", and beans and milk are Doses with an amount per drink in the Program Defaults, so a cappuccino costs more than an espresso. A Program's litres take amounts down to the millilitre: enter an espresso's 40 ml as 0.04.

Very short Runs, such as a coffee, are better priced "per Program" than from a meter. A metering plug counts in steps and reports at intervals that are coarse against a Run of under a minute, so what it measures for one drink is mostly chance. Choose "per Program" as the electricity source and give each drink its kWh in the Program Defaults.

## Tumble dryers and ovens

A tumble dryer and an oven are set up like a washing machine without the water source and the water price. They have no water sensors, and their Run event's `ended` carries the Program but no litres. What [Washing machines](#washing-machines) says about the Program, the Program Defaults, Flags and manual Runs applies to both, with these differences:

- **Tumble dryer**: the Dose list is optional (dryer sheets, fragrance); an empty one adds nothing to a Run. Its Program Defaults have the kWh and a column per Dose, never litres.
- **Oven**: it has no Dose list. Its Program Defaults are just the kWh per Program, with rows suggested from the Program input and past Runs and the measured kWh suggested per Program, as for a washing machine.
