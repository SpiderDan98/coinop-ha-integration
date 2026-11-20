# Nothing recalculates by itself after Run end

While a Run is open, its computed values (electricity, water, measured material, Doses, running-hours quantities) are provisional and recomputed live. At finalisation they are frozen into its Line Items, stored unrounded, together with the evidence they came from (method, price segments, measured length, Material copy, Dose source). From then on Coin-op never recomputes a Line Item on its own: not on restart, not when a Device's price, average power or Program Defaults change, not when recorder history is purged, not when a Material is repriced, and not when the user edits the Run's start, end, Outcome or pauses. Only an explicit user action changes a frozen value: on a Line Item (override, reset to computed value, changing its Material), or correcting the Run's Program.

## Amendment: correcting the Program

Correcting a Run's Program (open or ended) re-applies the new Program's defaults, from its row of the Program Defaults or else the Default row, to every Line Item whose method or Dose source is a Program default and that the user hasn't overridden: electricity kWh, water litres and Doses. A Dose the new Program doesn't use loses its default-sourced Line Item; a Dose it uses gains one, at its Material's current price, unless its stock input measured the Run (nothing used included; finalisation keeps which Doses it measured). Re-applied electricity and water keep the prices they were charged at. Measured, from-history, stock-input and entered Line Items, overridden ones, Dose Line Items given another Material and those of Doses removed since stay as they are. A Flag the defaults called for already and the user marked as checked is not raised again. Saving the same Program again re-applies nothing, so later changes to the Program Defaults still never reach an ended Run.

A wrong Program (a late or mistaken recognition) makes every default on the Run wrong, so the correction is a deliberate request for the costs to follow, like changing a Line Item's Material. The panel says so next to the Program field.

## Why

- A Run's cost is a record of what happened, not a view over current settings. A Cost Statement handed over last month must still add up to the same figure today.
- Recomputing from recorder history is not repeatable: history is purged after a few days by default, so a "recalculate" would silently fall back to a different method.
- Times are corrected far more often than costs (a wrong end time, a print marked Failed). Tying costs to those edits would surprise users with changed figures they didn't ask for; the panel says so next to those fields.

## Consequences

- Migrations only reshape stored data and fill defaults; they never recompute frozen values.
- A user who wants a different electricity figure for an ended Run overrides the Line Item; the computed value is kept for "reset to computed value".
- The Run engine computes through the pure cost core both live and once more at finalisation, and for finalised Runs only when the user corrects the Program.
