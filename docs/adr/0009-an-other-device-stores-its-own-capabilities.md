# A shipped Device Type's Capabilities live in code; an Other Device stores its own

What a Device has (its Capabilities) is answered in one place, `capabilities_of` in `device_config.py`, from the Device's subentry data. For a shipped Device Type it is a lookup by the Device Type's key in `CAPABILITIES`; such a Device stores only the key. A Device of the Device Type Other stores, next to the key, its Type Name and the Capabilities its user's choices brought, and the lookup has no entry for Other. The Device's configuration and the subentry flow both ask `capabilities_of`, and everything else branches on the Capabilities it answers, never on the Device Type.

## Why

- A shipped Device Type means one thing. Its set can change in a release (the washing machine gained per-Run meters that way) and every Device of the type follows at the next start, without a migration and without a Device left behind on an old set.
- What an Other Device has is its user's own choice, made per Device. No release knows it, so it can only live with the Device; two Other Devices with the same Type Name may have different sets.
- Storing a copy of the set on shipped Devices too would make the two alike, at the price of migrating every stored Device whenever a shipped set changes, and of deciding whether a copy that differs from the code is the user's intent or just old.
- Other as one more fixed set in the lookup can't work: there is no one set, and one set per combination would be Device Types nobody named.
- The Capabilities are stored, not the choices picked. The choices are how the form asks; what each brings can be regrouped or reworded later without touching a stored Device, and the rest of the code reads Capabilities anyway.

## Consequences

- Nothing existing is migrated and no Store changes shape: Devices of shipped Device Types store what they stored before.
- The two must not be unified by accident. A Capability set in the subentry of a shipped Device Type is ignored, and Other must not get an entry in `CAPABILITIES`.
- A change to what a choice brings (`CHOICES`) applies to Other Devices added afterwards. Existing ones keep the Capabilities they stored, so removing or renaming a `Capability` needs a migration of the subentries that store it.
- Without a Program, an Other Device stores the average power Capability too: it is what makes the electricity estimate available, and it is decided when the choices are saved (`chosen_capabilities`), not when they are read.
- The Type Name is stored the same way and for the same reason; `coinop/devices/list` sends it only for a Device that has one, and the panel groups by it instead of the Device Type's heading.
