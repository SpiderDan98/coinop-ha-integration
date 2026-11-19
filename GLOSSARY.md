# WattBill

Tracks what individual household devices cost to run, one Run at a time, inside Home Assistant.

## Language

**Device**:
A single tracked appliance, such as one specific 3D printer.
_Avoid_: Machine, appliance, printer (as the generic term)

**Device Type**:
The kind of Device (3D printer, washing machine, …), which determines which Line Items a Run gets by default.
_Avoid_: Category, device class

**Run**:
One completed working cycle of a Device, such as a single print job, together with its costs.
_Avoid_: Job, session, cycle, print

**Line Item**:
One cost line on a Run, such as electricity, filament, or inserting threaded inserts.
_Avoid_: Position, entry, cost line

**Line Item Template**:
A saved Line Item that can be added to any Run again.
_Avoid_: Preset, Vorlage

**Cost Source**:
Where a Line Item's unit price comes from, either a fixed value or a live value read from Home Assistant.
_Avoid_: Price provider, input

**Cost Statement**:
A document that lists selected Runs with their Line Items and a total; explicitly not an invoice.
_Avoid_: Invoice, bill, Rechnung, quote

**Material**:
A consumable a Device uses up during a Run, priced per unit and per type (e.g. PLA filament, standard resin).
_Avoid_: Filament (as the generic term), consumable
