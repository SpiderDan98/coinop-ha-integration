# Nothing recalculates by itself after Run end

While a Run is open, its computed values (electricity, measured material, running-hours quantities) are provisional and recomputed live. At finalisation they are frozen into its Line Items, stored unrounded, together with the evidence they came from (method, price segments, measured length, Material copy). From then on WattBill never recomputes a Line Item on its own: not on restart, not when a Device's price or average power changes, not when recorder history is purged, not when a Material is repriced, and not when the user edits the Run's start, end, Outcome or pauses. Only an explicit user action on a Line Item (override, reset to computed value, changing its Material) changes a frozen value.

## Why

- A Run's cost is a record of what happened, not a view over current settings. A Cost Statement handed over last month must still add up to the same figure today.
- Recomputing from recorder history is not repeatable: history is purged after a few days by default, so a "recalculate" would silently fall back to a different method.
- Times are corrected far more often than costs (a wrong end time, a print marked Failed). Tying costs to those edits would surprise users with changed figures they didn't ask for; the panel says so next to those fields.

## Consequences

- Migrations only reshape stored data and fill defaults; they never recompute frozen values.
- A user who wants a different electricity figure for an ended Run overrides the Line Item; the computed value is kept for "reset to computed value".
- The Run engine computes through the pure cost core both live and once more at finalisation, and nothing calls it for finalised Runs.
