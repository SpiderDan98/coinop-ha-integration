# Coin-op

Tracks what individual household devices cost to run, one Run at a time, inside Home Assistant.

## Language

**Device**:
A single tracked appliance, such as one specific 3D printer.
_Avoid_: Machine, appliance, printer (as the generic term)
_German UI_: Gerät

**Device Type**:
The kind of Device (3D printer, washing machine, …), chosen when it is added and fixed afterwards. It determines which Device Inputs, computed Line Items (such as electricity and material), entities and panel parts the Device has.
_Avoid_: Category, device class
_German UI_: Gerätetyp

**Device Input**:
A Home Assistant value a Device reads, such as its print status, material used, thumbnail or camera, chosen by the user.
_Avoid_: Sensor mapping, source
_German UI_: Geräteeingang

**Slot**:
A place on a Device that holds one Material at a time, such as one bay of a multi-material unit.
_Avoid_: Gate, bay, tray
_German UI_: Fach

**Integration Profile**:
The known Device Inputs of a specific integration, used to fill in a Device's Device Inputs automatically for the Device Types the integration serves.
_Avoid_: Preset, adapter, template
_German UI_: Integrationsprofil

**Quick Start**:
The short way through Add Device: the user picks an HA device of an integration with an Integration Profile, and the Device takes every Device Input the profile finds without showing its steps, asking only for the meter and the prices.
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
The number of usable parts a Run produced, which its total cost is divided by to give the cost per part. Only Runs of 3D printers have one.
_Avoid_: Quantity, pieces, copies
_German UI_: Teileanzahl

**Program**:
The washing program a Run of a washing machine ran, such as "Cotton 60°" or "Eco 40-60", as its Program Device Input reports it or the user corrects it.
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
The preview image of the model a Run produces, taken from the Device's thumbnail.
_Avoid_: Preview, model image
_German UI_: Vorschaubild

**Snapshot**:
The camera image of a Device taken when a Run ends.
_Avoid_: Photo, picture, completion image
_German UI_: Kamerabild

**Cover Image**:
The one image that stands for a Run wherever only one is shown: the one the user picked, otherwise the first of its Thumbnail, Snapshot and uploaded images.
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
Where a Line Item's unit price comes from: a fixed value, or a live value read from Home Assistant or Spoolman.
_Avoid_: Price provider, input
_German UI_: Preisquelle

**Cost Statement**:
A document that lists selected ended Runs with their costs and a total, optionally plus a Markup; explicitly not an invoice.
_Avoid_: Invoice, bill, Rechnung, quote
_German UI_: Kostenaufstellung

**Markup**:
A percentage added on top of a Cost Statement's total; never part of a Run's own costs.
_Avoid_: Surcharge, margin
_German UI_: Aufschlag

**Material**:
A consumable a Device uses up during a Run, bought at one price, such as "PLA" or "eSun PLA+ black"; as broad or as specific as the user keeps it.
_Avoid_: Filament (as the generic term), consumable
_German UI_: Material

**Spoolman Filament**:
A filament product in Spoolman, not a single spool, that a Material links to; the Material then takes its price per gram and its type, density, diameter, colour and vendor from it, so a new spool needs no relinking.
_Avoid_: Spool (as what a Material links to)
_German UI_: Spoolman-Filament

**Dose**:
One product a washing machine's Runs use, such as detergent or fabric softener, pointing to one Material; each Dose a Run uses becomes one Material Line Item.
_Avoid_: Additive, dosage, detergent (as the generic term)
_German UI_: Dosierung

**Stock input**:
An entity reporting how much of a Dose's product is left, in g or ml (for example a scale under the bottle); what it loses during a Run, refills ignored, is the Dose's amount.
_Avoid_: Level sensor, fill level
_German UI_: Bestandssensor

**Program Defaults**:
A Device's kWh, litres and Dose amounts for each Program, plus a Default row for Runs without a known Program, filling in whatever a Run doesn't measure.
_Avoid_: Presets, program profiles, estimates
_German UI_: Programmvorgaben
