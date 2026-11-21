# Other Devices

Choose **Other**, the last entry of Add Device's Device Type step, for a Device Coin-op ships no Device Type for: garden irrigation, a CNC router or laser cutter, a bread maker, a kiln, a pool pump, a soda maker. Anything that has a Status to open and close its Runs can be followed this way.

An Other Device is put together from what the shipped Device Types are made of: a Program, Doses, water, a job with its Material, images, a Part Count. Add Device asks two things a shipped Device Type answers by itself: a **Type Name**, and **what the Device has**. After that it is a Device like every other: Add Device asks only for the steps your choices bring, its Runs get the Line Items they bring, and its card, its Runs' pages, its sensors and its Run event show exactly those.

When a shipped Device Type fits your Device, pick that one: only those are offered by [Quick Start](adding-a-device.md#quick-start) and come pre-filled for the integrations Coin-op knows. Pick Other when none fits, or when the one whose Runs record the right things would list the Device as something it isn't, such as an irrigation valve under "Washing machines".

No integration pre-fills an Other Device, and Quick Start never adds one. Where Add Device opens with Quick Start, choose **Set up manually** to get to the Device Type step. In every step you pick the entities yourself: any entity works, optionally one of its attributes, and so does a helper or a template sensor of your own. The reconfigure menu of an Other Device has no **Detect again**.

## Type Name

The Type Name is your own name for the kind of Device, such as "Irrigation" or "CNC router". The panel's Devices tab lists an Other Device under its Type Name as the heading, where a washing machine stands under "Washing machines". Other Devices with exactly the same Type Name share a heading, and every other Type Name gets a heading of its own. Add Device offers the Type Names you already gave, so a second Device of the same kind gets the same one without retyping it.

A Type Name is a heading and nothing more. Two Devices that share one may have different things switched on, and a Type Name that reads like a shipped Device Type's heading is still a group of its own.

## What the Device has

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

- **Program**, **Doses** and **Water** are a washing machine's. What [Washing machines](appliances.md#washing-machines) says about the Program, the Program Defaults, Doses, stock inputs and their Flags applies. The Program Defaults table on the Device's card has the columns the Device has: kWh with a Program, litres with a Program and Water, and one per Dose. With Doses and no Program the table is the Default row alone, which every Run uses.
- **Job and Material**, **Images** and **Part Count** are a 3D printer's, and Images and Part Count don't need a job: a kiln can have both. The Material used entity reports a length or a mass. Without one, each Run gets a Material Line Item with an empty quantity, in grams or, for a Material bought by the piece, in pieces, and a Flag until you enter it. The Line Item's Material is the **Default Material** you set on the Device's card, or the one in a Slot.
- Tags for new Runs and automatic Line Item Templates work as for every Device. A manual Run asks for the Program if the Device has one, and the Flags of a Run follow what the Device has: a Device without Job and Material is never asked for a Run's material.
- A Material that fits none of the other Material forms goes under the form **Other** in the Materials tab, with g, ml or pieces as its pack unit.

## Electricity and water sources

The electricity source menu of an Other Device depends on whether it has a Program:

| | Without a Program | With a Program |
|---|---|---|
| Measured | Energy meter, Power sensor | Energy meter, Power sensor |
| Not measured | **Estimate from average power** | **Per Program (kWh in the Program Defaults)** |
| Not followed | [None](electricity.md#electricity-source-none) | [None](electricity.md#electricity-source-none) |

- **Estimate from average power** multiplies the running time by the average power you enter. Enter what the Device draws on average over a whole Run, not the rated power on its label. See [Estimating electricity without a meter](electricity.md#estimating-electricity-without-a-meter).
- **Per Program** takes the kWh of the Run's Program from the Program Defaults, and the Default row's for a Run without a Program or without a row of its own.
- The two are never offered together. A Device with a Program takes electricity that nothing measured from the Program's kWh, so there is exactly one way to get electricity without a meter.
- **None** is for a Device whose electricity you don't follow, such as a battery-driven valve. Its Runs get no Electricity Line Item, and Add Device skips the electricity price.

With **Water**, the water source is a water meter, a flow sensor or None, and with a Program also **Per Program (litres in the Program Defaults)**. Without a Program there is no default for water: it is measured, or you add it by hand on a Run. Water is priced per m³, from a fixed price or a price entity.

## Meters count each Run from 0

Switch this on when the energy or water meter you pick counts the current Run only: a session or per-cycle sensor that starts each Run at 0 and drops back to 0 once the Run is over.

Coin-op takes a meter that reads less than before for a meter reset. Such a Run is still counted correctly, but when the drop arrives in the minutes after the Run's end, while Coin-op waits for the meter's last report, the Run gets the meter reset Flag. With this switched on, a drop after the end of a Run is expected and raises no Flag.

Such a sensor often has no value at all between two Runs, and still has none at the moment the Status starts the next one. Coin-op takes a meter without a value at a Run's start for a consumption gap, since a meter that only counts up and comes back later may have counted in between. With this switched on, a meter that has no value as the Run starts and then begins at 0 raises no Flag: it counted nothing before that 0. A meter whose first value is above 0, one that loses its value during the Run or never has one, and a power or flow sensor without a value get the consumption gap Flag either way.

Leave it off for a meter that only counts up, such as a metering plug's total energy or a water meter on the supply: there a drop is a real reset, a meter that comes back at 0 after having no value lost what it counted, and the Flags are right. A counter that only drops once the next Run is already running gets that Run the Flag either way.

## What can't be combined

**Job and Material** can't be switched on together with **Program** or with **Doses**. The form refuses it and says why: the job and the Program would both name the Run, and a Dose's Material Line Item would take the place of the Run's own Material Line Item and of its Flags. Every other combination works, including none at all.

What to do instead:

- **A Material now and then**: leave Job and Material off. On any Run, whatever its Device has, **Add Material Line Item** on the Run's page adds one by hand: pick the Material and enter the quantity.
- **A product every Run uses**: that is a Dose. Switch on Doses and give it its amount, per Program if the Device has one.
- **A flat cost per Run**, such as wear or a blank that always costs the same: create a Line Item Template and add it to the **Automatic templates** on the Device's card. It is then added to every Run that starts there.
- **A job name and a Program**: switch on Program. A Run is named after its Program until you rename it, so you can still give it the job's name on its page.

## Worked examples

The amounts below assume an electricity price of €0.30 per kWh and a water price of €4.00 per m³.

### Irrigation

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

### A CNC router or laser cutter

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

### A bread maker

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

### Further mixes

| Device | Switch on | Electricity source |
|---|---|---|
| Kiln | Part Count, and Images with a camera | Estimate from average power, or a meter |
| Pool pump | Nothing, or "Meters count each Run from 0" with a per-cycle energy sensor | Energy meter |
| Soda maker | Doses, for the CO₂ and the syrup, each with its amount in the Default row | None |

## Changing an Other Device later

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
