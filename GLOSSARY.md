# WattBill

Tracks what individual household devices cost to run, one Run at a time, inside Home Assistant.

## Language

**Device**:
A single tracked appliance, such as one specific 3D printer.
_Avoid_: Machine, appliance, printer (as the generic term)

**Device Type**:
The kind of Device (3D printer, washing machine, …), which determines which Line Items a Run gets by default.
_Avoid_: Category, device class

**Device Input**:
A Home Assistant value a Device reads, such as its print status, material used, thumbnail or camera, chosen by the user.
_Avoid_: Sensor mapping, source

**Slot**:
A place on a Device that holds one Material at a time, such as one bay of a multi-material unit.
_Avoid_: Gate, bay, tray

**Integration Profile**:
The known Device Inputs of a specific printer integration, used to fill in a Device's Device Inputs automatically.
_Avoid_: Preset, adapter, template

**Run**:
One working cycle of a Device, such as a single print job, from start to end and together with its costs, whatever its Outcome.
_Avoid_: Job, session, cycle, print

**Outcome**:
How a Run ended: Completed, Cancelled, Failed or Unknown; a Run still going has no Outcome yet.
_Avoid_: Result, status (for the ending)

**Flag**:
A marker on a Run pointing out something the user may want to check, such as a reported fault or a gap in price or consumption data.
_Avoid_: Warning, error, notice

**Line Item**:
One cost line on a Run, such as electricity, filament, or inserting threaded inserts.
_Avoid_: Position, entry, cost line

**Line Item Template**:
A saved Line Item that can be added to any Run again.
_Avoid_: Preset, Vorlage

**Cost Source**:
Where a Line Item's unit price comes from: a fixed value, or a live value read from Home Assistant or Spoolman.
_Avoid_: Price provider, input

**Cost Statement**:
A document that lists selected Runs with their Line Items and a total; explicitly not an invoice.
_Avoid_: Invoice, bill, Rechnung, quote

**Material**:
A consumable a Device uses up during a Run, bought at one price, such as "PLA" or "eSun PLA+ black"; as broad or as specific as the user keeps it.
_Avoid_: Filament (as the generic term), consumable
