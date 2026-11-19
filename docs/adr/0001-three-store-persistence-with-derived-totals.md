# Three Stores, with sensor totals derived from Runs

WattBill keeps its data in three Home Assistant Stores: `catalog` (Materials, Line Item Templates, Tags), `runs` (ended Runs, written on finalisation and on every edit) and `live` (open Runs, written with a delay of about 60 seconds). Finalisation writes `runs` first, then `live`; a Run found in both is taken from `runs`. Sensor totals are never stored: at startup each Device's totals are the sum over its stored Runs (open Runs at their provisional values) and are then advanced in memory by the delta of each change.

## Why

- An open Run changes every minute (live electricity) while an ended Run changes only when the user edits it. Writing the whole Run history every minute would rewrite thousands of Runs for one changing value, so the hot, small set of open Runs gets its own Store with a delayed save.
- Writing `runs` before `live` means a crash between the two writes leaves the Run in both Stores, never in neither. Taking it from `runs` then resolves the duplicate without losing the frozen values.
- Stored totals could drift from the Runs after a crash, a restore or a bug. Deriving them from the Runs makes the Runs the single source of truth; the Runs sensor and the cost sensors can never disagree with the panel.

## Consequences

- Up to about a minute of an open Run's progress can be lost on a crash; it is recovered like an outage (gaps filled from recorder history where a consumption entity exists).
- Home Assistant's `Store.async_delay_save` pushes the write back on every call, so the live Store keeps its first deadline itself; otherwise an open Run updated every minute would never be written.
- Startup cost grows with the number of Runs (expected ~2,000 a year, summed in memory).
- After a restore of recorder and WattBill data from different points in time, statistics jump once to the totals of the restored Runs.

## Amendment: a fourth Store for Device settings

WattBill's own per-Device settings (Tags for new Runs, automatic Line Item Templates, default Material) live in a fourth Store, `device_settings`, rather than in the catalog Store or the Device's subentry.

- They belong to one Device, not to a global catalogue, and are dropped with it when the Device is removed; in the catalog Store each catalogue change would also rewrite them and the other way round.
- The subentry holds what the Device flow configures, and every subentry change reloads the hub entry; settings changed from the panel must not restart every tracker.
- Like every Store, it is registered in `store.SCHEMAS`, so the missing-data check, migrations and uninstall cover it.
