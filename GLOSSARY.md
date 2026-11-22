# Coin-op

Tracks what individual household devices cost to run, one Run at a time, inside Home Assistant.

## Language

**Device**:
A single tracked appliance, such as one specific 3D printer.
_Avoid_: Machine, appliance, printer (as the generic term)
_German UI_: Gerät

**Device Type**:
The kind of Device (3D printer, washing machine, dishwasher, …, or Other), chosen when it is added and fixed afterwards. A shipped Device Type determines which Device Inputs, computed Line Items (such as electricity and material), entities and panel parts the Device has. Other is for a Device Coin-op ships no Device Type for: the user gives it a Type Name and picks what it has from those same parts. What is fixed is the Device Type itself: an Other Device stays Other and a shipped one never becomes Other. An Other Device's Type Name and what it has can be changed later, while it has no open Run (nor one that ended and still waits for its meters' last reports); what a shipped Device Type has can't.
_Avoid_: Category, device class
_German UI_: Gerätetyp (Other: Sonstiges)

**Type Name**:
The user's own name for what kind of Device an Other Device is, such as "Kiln" or "Pool pump"; the panel lists the Devices that share one under it as their heading. Only Other Devices have one, and unlike the Device Type it can be changed later. It is not a Device Type: one that reads like a shipped Device Type's name is still a group of its own.
_Avoid_: Custom type, type label, category
_German UI_: Typbezeichnung

**Device Input**:
A Home Assistant value a Device reads, such as its print status, material used, planned material, remaining time, progress, expected energy, a multi-material unit's drying, thumbnail or camera, chosen by the user.
_Avoid_: Sensor mapping, source
_German UI_: Geräteeingang

**Slot**:
A place on a Device that holds one Material at a time, such as one bay of a multi-material unit.
_Avoid_: Gate, bay, tray
_German UI_: Fach

**Integration Profile**:
The known Device Inputs of a specific integration, used to fill in a Device's Device Inputs automatically for the Device Types the integration serves. It also tells an HA device's appliance kind: what the integration itself registered it as (Miele's "Tumble dryer", WashData's "dishwasher"), before it is a Device. A kind is not a Device Type: Quick Start adds a kind that is one as that Device Type (several kinds can be the same one, as a washer-dryer is a Washing machine), asks for the Device Type where the integration doesn't tell the kind, and leaves out a kind that is none, such as a fridge. The kind is never stored.
_Avoid_: Preset, adapter, template
_German UI_: Integrationsprofil

**Quick Start**:
The short way through Add Device: the user picks an HA device of an integration with an Integration Profile, and the Device takes the Device Type the integration says it is and every Device Input the profile finds without showing its steps, asking only for the meter and the prices, and for the Device Type where the integration doesn't say. Add Device always opens on it, also when it has no device to offer.
_Avoid_: Wizard, auto-setup, express setup
_German UI_: Schnellstart

**Run**:
One working cycle of a Device, such as a single print job, from start to end and together with its costs, whatever its Outcome.
_Avoid_: Job, session, cycle, print
_German UI_: Lauf

**Outcome**:
How a Run ended: Completed, Cancelled, Failed or Unknown; a Run still going has no Outcome yet.
_Avoid_: Result, status (for the ending)
_German UI_: Ausgang (Abgeschlossen, Abgebrochen, Fehlgeschlagen, Unbekannt)

**Part Count**:
The number of usable parts a Run produced, which its total cost is divided by to give the cost per part. Only Runs of a Device that has a Part Count have one: a 3D printer, or an Other Device it was picked for.
_Avoid_: Quantity, pieces, copies
_German UI_: Teileanzahl

**Program**:
The program a Run ran, such as a washing machine's "Cotton 60°", a dishwasher's "Eco 50°" or a coffee machine's "Cappuccino", as the Device's Program Device Input reports it or the user corrects it. Only Devices with a Program input have one: those of a Device Type that has it, and an Other Device given one.
_Avoid_: Cycle, mode, wash type
_German UI_: Programm

**Tag**:
A user-chosen keyword that groups Runs across Devices and periods, such as "Cosplay helmet" or "Gift"; a Run can have any number of them.
_Avoid_: Project, label, category
_German UI_: Tag

**Flag**:
A marker on a Run pointing out something the user may want to check, such as a reported fault or a gap in price or consumption data.
_Avoid_: Warning, error, notice
_German UI_: Hinweis

**Thumbnail**:
The preview image of what a Run produces, such as the model a 3D printer prints, taken from the Device's thumbnail.
_Avoid_: Preview, model image
_German UI_: Vorschaubild

**Snapshot**:
The camera image of a Device taken when a Run ends.
_Avoid_: Photo, picture, completion image
_German UI_: Kamerabild

**Cover Image**:
The one image that stands for a Run wherever only one is shown: the one the user picked, otherwise the newest of the kind its Device prefers (Thumbnail, Snapshot or uploaded photo), otherwise the first of its Thumbnail, Snapshot and uploaded images.
_Avoid_: Main image, title image
_German UI_: Titelbild

**Line Item**:
One cost line on a Run, such as electricity, filament, or inserting threaded inserts. Its kind is Electricity, Water, Material or Other.
_Avoid_: Position, entry, cost line
_German UI_: Posten (Strom, Wasser, Material, Sonstiges)

**Line Item Template**:
A saved Line Item that can be added to any Run again.
_Avoid_: Preset, Vorlage
_German UI_: Postenvorlage

**Cost Source**:
Where a Line Item's unit price comes from: a fixed value, or a live value read from Home Assistant or Spoolman. A Material's Cost Source follows from where it comes from: fixed for an own Material, Spoolman for one from a Spoolman Filament; the user never picks it.
_Avoid_: Price provider, input
_German UI_: Preisquelle

**Cost Statement**:
A document that lists selected ended Runs with their costs and a total, optionally plus a Markup; explicitly not an invoice.
_Avoid_: Invoice, bill, Rechnung, quote
_German UI_: Kostenaufstellung

**Projected Total**:
The cost an open Run is expected to reach by its end: its cost so far plus the rest still to come, such as its recent power draw over the time it has left. Only an open Run has one, and only when there is something to project the rest from. It is never stored, is not a Line Item and is never part of a Cost Statement; once the Run ends, only its real costs remain.
_Avoid_: Estimate, forecast, preliminary price
_German UI_: Voraussichtlich

**Markup**:
A percentage added on top of a Cost Statement's total; never part of a Run's own costs.
_Avoid_: Surcharge, margin
_German UI_: Aufschlag

**Material**:
A consumable a Device uses up during a Run, bought at one price, such as "PLA" or "eSun PLA+ black"; as broad or as specific as the user keeps it.
_Avoid_: Filament (as the generic term), consumable
_German UI_: Material

**Spoolman Filament**:
A filament product in Spoolman, not a single spool. While Spoolman is connected, each one is a Material on its own, created when Coin-op reads Spoolman and archived when the Filament is deleted there; it takes its name, price, type, density, diameter, colour and vendor from the Filament, so a new spool changes nothing. An own Material of the same type (and colour) can be merged into one, keeping its id and its Runs.
_Avoid_: Spool (as what a Material links to)
_German UI_: Spoolman-Filament

**Dose**:
One product a Device's Runs use, such as a washing machine's detergent, a dishwasher's tabs or a soda maker's CO₂, pointing to one Material; each Dose a Run uses becomes one Material Line Item.
_Avoid_: Additive, dosage, detergent (as the generic term)
_German UI_: Dosierung

**Stock input**:
An entity reporting how much of a Dose's product is left, in g or ml (for example a scale under the bottle); what it loses during a Run, refills ignored, is the Dose's amount.
_Avoid_: Level sensor, fill level
_German UI_: Bestandssensor

**Program Defaults**:
A Device's kWh, litres and Dose amounts for each Program, whichever of them the Device has (an oven's are just the kWh), plus a Default row for Runs without a known Program, filling in whatever a Run doesn't measure. On a Device with Doses and no Program they are the Default row alone, which every Run uses.
_Avoid_: Presets, program profiles, estimates
_German UI_: Programmvorgaben
