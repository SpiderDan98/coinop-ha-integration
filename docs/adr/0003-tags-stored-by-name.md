# Tags are stored by name on Runs and Devices

A Tag has no id. The catalogue in the catalog Store is a list of names (unique ignoring case), and each Run and each Device's Tags for new Runs hold the names themselves. Renaming, merging or deleting a Tag rewrites every Run and Device that carries it, in one save of each Store, and announces the changed Runs like any correction.

## Why

- A Tag is nothing but its name; an id would add a lookup to every reader (Run events, Current/Last Run cost attributes, filters, Analysis, the Cost Statement title) for no extra information.
- Run events and sensor attributes carry the names automations match on. With names on the Run, they are always current without re-reading a catalogue, and an `ended` event that already fired keeps the names it had.
- Merging is a rename onto an existing name; with names on Runs it is the same rewrite with duplicates dropped.

## Consequences

- A rename touches every tagged Run. At the expected volume (a few thousand Runs) that is one write of the runs Store and of the live Store.
- Names are matched ignoring case everywhere a user types one; the catalogue's spelling wins.
- Tags never take part in costs, Flags or totals, so rewriting them never moves a sensor.
