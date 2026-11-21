# No binding to a specific printer integration

Coin-op never depends on a particular printer integration. Each Device reads configurable Device Inputs (an entity, optionally one of its attributes), and an Integration Profile only pre-fills them when the printer's HA device belongs to a known integration domain. What is stored is the concrete entities and values the user confirmed, never a reference to the profile. v1 ships profiles for `anycubic` (chrisfore/anycubic_ha_local) and `anycubic_cloud` (Nino6689/hass-anycubic); every other printer, Moonraker/Rinkhals included, is mapped by hand. The same holds for washing machines: profiles are kept per Device Type, and washing machines have profiles for `ha_washdata` (WashData), `miele` and `home_connect`.

## Why

- The Kobra S1 alone has two maintained integrations, both reverse-engineered, fast-changing and single-maintainer. Binding to one would tie Coin-op's lifecycle to theirs.
- Every integration exposes a print status somehow; reading entities makes any printer work, and keeps the cost model identical for every Device.
- A profile that only pre-fills can be wrong without harm: the user sees every step and corrects it.

## Quick Start

Add Device first offers the HA devices of integrations with a profile that the profile finds a Status for (Quick Start). Picking one stores what the profile finds without walking its steps, and asks only for what no profile knows: the electricity meter, the electricity price and, for a washing machine, the water price.

- Walking every step is a lot at once for a user whose integration Coin-op already knows, and most of them accept every pre-filled step anyway.
- What is stored is unchanged: the concrete entities and values, in the shape the steps write them, never a reference to the profile. Reconfigure and Detect again work on such a Device as on any other.
- A wrong profile is no longer seen before it is stored. In exchange the second form lists the entities found, the manual way stays one choice away, and a Run that starts or ends wrongly is corrected in the reconfigure menu.
- Nothing is guessed: a printer without a meter is sent to the manual way instead of getting an invented average power, and a meter whose unit is neither energy nor power is refused.

## Consequences

- Profiles find entities in the entity registry by unique id (of the printer's HA device and of devices linked to it via `via_device_id`, such as an ACE unit), so entities the user renamed are still found. An integration that changes its unique ids breaks detection, not existing Devices.
- When an integration renames or replaces entities, a Device keeps pointing at the old ones until the user runs "Detect again", which re-applies the profile to Status, mapping, job, images and Program and never touches the electricity or water source or their prices (a profile may pre-fill a meter in Add Device, as Miele's per-cycle energy and water sensors).
- Coin-op takes nothing else from the integration: its live telemetry and its own cost sensors (hass-anycubic's job energy and cost) are ignored.
- Adding a profile is a code change in `profiles.py`; nothing in the stored data needs migrating. Its devices then show up in Quick Start by themselves.
- Miele and Home Connect register every appliance with the same Status entities, so Quick Start lists their ovens and dishwashers too; the user picks.
