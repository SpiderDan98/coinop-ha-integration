# What does Spoolman provide in Home Assistant? (Issue #5)

As of 2026-11-19. Versions read:

- Spoolman `master` @ [`f9e819a`](https://github.com/Donkie/Spoolman/tree/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba) (2026-11-16), latest release `v0.27.1` (2026-10-31)
- HA integration Disane87/spoolman-homeassistant: `main` @ [`d763826`](https://github.com/Disane87/spoolman-homeassistant/tree/d763826eae1f91477d53fa5f3919f75311ca03a7) (= release `v1.4.0` plus docs), plus a brief look at `dev` @ `15db7b3` (2026-10-28)
- Moonraker `components/spoolman.py` @ [`b3f9566`](https://github.com/Arksine/moonraker/blob/b3f9566b8b8863ec85a00ce424d77c8e19576c44/moonraker/components/spoolman.py)

Abbreviations: `SM` = Spoolman repo `Donkie/Spoolman@f9e819a`, `HA` = `Disane87/spoolman-homeassistant@d763826`.

## Summary

- **Prices exist at two levels, each as a total price, not per kg:** `Filament.price` ("price of this filament", in the system-wide configured currency, default `EUR`) and `Spool.price` (an optional per-spool override). Coin-op has to compute a price per gram itself: `(spool.price ?? filament.price) / (spool.initial_weight ?? filament.weight)`. This formula is derived, not documented by Spoolman.
- **Material, vendor, colour, density and diameter belong to the filament** (`material` as free text, `vendor`, `color_hex`/`multi_color_hexes`, `density` g/cm³, `diameter` mm). **Weights belong to the spool** (`initial_weight` net, `spool_weight` tare, `used_weight`, computed `remaining_weight`/`remaining_length`/`used_length`).
- **Spoolman has no spool-to-printer or spool-to-slot assignment.** There is only `location` (free text) and user-defined `extra` fields. Anyone who wants to model an "active spool" or "ACE slot X" does it through conventions on `location` or `extra`, or Moonraker holds the active spool.
- **Booking usage works:** `PUT /api/v1/spool/{id}/use` with `use_weight` (g) or `use_length` (mm). Both are additive and not idempotent; negative values are accepted and clamped at 0. The HA integration passes this through as the service `spoolman.use_spool_filament` (no return value).
- **Usage per Run cannot be read back from Spoolman.** Spoolman stores only the cumulative `used_weight` plus `first_used`/`last_used`; there is no usage log (feature request #916 is open). At most, CoinOp could derive a Run's usage as the difference in `used_weight` before and after the Run. That is fragile.
- **Push mechanism:** Spoolman offers WebSockets (root `/api/v1/` as well as `/api/v1/spool`, `/api/v1/spool/{id}` etc.) with `added`/`updated`/`deleted` events and the full object as payload. The HA integration does **not** use them: it polls (`local_polling`, interval in minutes, default 15).
- **HA entities (Disane87):** One device per spool with many sensors (remaining weight as the main sensor, used weight, price, material, vendor, density, diameter, colour, location, …) plus a location select. The main sensor carries the **fully flattened spool JSON** as attributes, so it also includes `filament_price`, `filament_material` and `filament_weight`. The price sensor shows only `spool.price` and has no unit or currency.
- **Anycubic Kobra S1 (without Klipper/Moonraker):** Spoolman books nothing by itself. Usage is only booked when a client calls `use`. With stock firmware, that only comes from community bridges (Node-RED, kobra-spoolman) or from Coin-op itself. With the Rinkhals custom firmware, Moonraker runs on the printer, and its Spoolman component continuously books `use_length` against the *single* active spool. The ACE Pro additionally needs an unofficial patch for gate assignment.
- **Maintenance:** Spoolman is very active (push 2026-11-16, 3k stars). The HA integration is moderately active: latest stable release `v1.4.0` from 2026-05-10, `dev` is 96 commits ahead (mostly refactoring and dependency bumps, last dev pre-release 2026-06-02), 22 open issues, including an HA 2027.8 deprecation (`via_device`). Its built-in Klipper part is deprecated.
- **Assessment for Coin-op:** Spoolman works well as a **Cost Source (price per Material)**, ideally read directly via REST or WebSocket rather than through the HA entities. It does not work as a **source for usage per Run**. Spoolman is better seen as a *target* into which Coin-op books a Run's usage back.

---

## 1. Spoolman REST API data model

The API lives under `/api/v1/` ([SM `spoolman/api/v1/router.py` L25-34](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/router.py#L25-L34)); the rendered OpenAPI docs are at <https://donkie.github.io/Spoolman/> (linked in the [README L19](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/README.md#L19)). All field details below come from the Pydantic response models in [SM `spoolman/api/v1/models.py`](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py).

### Vendor ([L138-178](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L138-L178))
`id`, `registered`, `name`, `comment`, `empty_spool_weight`, `external_id`, `extra`.

### Filament ([L213-343](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L213-L343))
Relevant fields:

| Field | Meaning according to source |
|---|---|
| `vendor` | embedded Vendor object |
| `material` | free text, max. 64 characters, e.g. "PLA" (no enum) |
| `price` | "The price of this filament in the system configured currency", `ge=0`, optional |
| `density` | g/cm³, required |
| `diameter` | mm, required |
| `weight` | "weight of the filament in a full spool, in grams" (net), optional |
| `spool_weight` | tare of the empty spool |
| `color_hex`, `multi_color_hexes`, `multi_color_direction` | colour(s) |
| `settings_extruder_temp`, `settings_bed_temp`, `article_number`, `external_id`, `extra`, `tags` | other |

### Spool ([L345-482](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L345-L482))

| Field | Meaning according to source |
|---|---|
| `filament` | embedded Filament object (incl. Vendor) |
| `price` | "The price of this spool in the system configured currency", optional |
| `initial_weight` | "initial weight … of the filament on the spool (net weight)", optional |
| `spool_weight` | tare |
| `used_weight` | used weight in g (required, cumulative) |
| `remaining_weight` | computed, only set if `initial_weight` or `filament.weight` is known |
| `used_length`, `remaining_length` | computed in mm from weight, density and diameter |
| `first_used`, `last_used` | timestamps of first and last use (UTC) |
| `location` | free text, max. 64 characters ("Where this spool can be found") |
| `lot_nr`, `comment`, `archived`, `extra`, `tags` (NFC/RFID) | other |

Derivation of `remaining_weight`: `initial_weight - used_weight`, falling back to `filament.weight - used_weight`, clamped at 0 ([`Spool.from_db` L432-482](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L432-L482)). The DB model stores only `used_weight`; `remaining_*` and `used_length` are pure API computations ([SM `database/models.py` L83-113](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/database/models.py#L83-L113)).

### Price semantics (important for the Cost Source)
- The API does **not** fill `Spool.price` from `filament.price`. `Spool.from_db` returns `price=item.price` as is ([L468](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L468)). Only sorting uses `coalesce(Spool.price, Filament.price)` ([SM `database/spool.py` L243-244](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/database/spool.py#L243-L244)). The web frontend also treats the spool price as an override of the filament price (`spool?.price ?? filament?.price` in [client_v2 `labels/template.ts` L44](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/client_v2/src/lib/labels/template.ts#L44); "overridesFilament" in [`SpoolInspector.svelte` L99-100](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/client_v2/src/lib/components/library/SpoolInspector.svelte#L99-L100)).
- Both prices are **prices per spool or package**, not per kg. The reference quantity is implicitly the net weight (`initial_weight` or `filament.weight`). **Uncertain:** the reference quantity is not stated explicitly anywhere. The formula `price / net_weight` is our own derivation.
- The currency is a global setting `currency` (default `"EUR"`, [SM `settings.py` L64](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/settings.py#L64)), readable via the settings API.
- Missing prices are `null`. Coin-op needs a fallback for that.

### Printer or slot assignment
- There is **no** table or field for printer, slot or "active". The DB tables are `vendor`, `filament`, `spool`, `setting`, `*_field` (extra fields) and `tag` ([SM `database/models.py`](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/database/models.py)).
- Substitutes are `location` (the API examples are even `"Printer 1"`, `"Printer 2"`: [SM `api/v1/other.py` L102-120](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/other.py#L102-L120)) or a choice extra field. The Spoolman maintainer recommends exactly that for "assigning spools to a printer" ([Donkie/Spoolman#932, maintainer comment](https://github.com/Donkie/Spoolman/issues/932)).
- The "active spool" is a **Moonraker** concept, not a Spoolman one (see §4).
- New since 0.27: tag readers (`reader_id`, example `"printer-voron"`) and tag scans ([models.py L742-845](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L742-L845)). This is scanning infrastructure, but not a persistent spool-to-printer assignment. **Uncertain** whether it will be extended in that direction.

## 2. Booking and reading usage

### Writing
- `PUT /api/v1/spool/{spool_id}/use`, body `{"use_weight": g}` **or** `{"use_length": mm}`. Both together return 400 ([SM `api/v1/spool.py` L174-176, L945-980](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/spool.py#L945-L980)).
- Semantics: `used_weight += weight`; a negative result is set to 0. `first_used` is set if needed, `last_used = now`, followed by an `updated` event ([SM `database/spool.py` L1121-1168](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/database/spool.py#L1121-L1168)). There is no `ge=0` on `use_weight`, so negative correction bookings are possible ([L174-176](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/spool.py#L174-L176)).
- `use_length` is converted to weight using the filament's density and diameter ([L1170 ff.](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/database/spool.py#L1170)).
- `PUT /api/v1/spool/{id}/measure` with the gross scale weight derives `used_weight` ([api L983-1010](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/spool.py#L983-L1010)).
- `PATCH /api/v1/spool/{id}` sets fields absolutely (including `used_weight`, `remaining_weight`, `location`, `price`).
- **Not idempotent:** a repeated `use` call books twice. There is no idempotency key and no job or Run reference. For Coin-op this means keeping its own "already booked" marker per Run.
- **No authentication:** "Spoolman has no authentication by design" ([SM `security.py` L3](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/security.py#L3)). Protection comes from the network and from origin checks against browser CSRF (same file). For the HA integration, API key auth is therefore an open feature request ([Disane87/spoolman-homeassistant#886](https://github.com/Disane87/spoolman-homeassistant/issues/886)).

### Reading per Run
- Spoolman keeps **no usage log**; only the cumulative `used_weight` is stored (DB model above). The feature request "Spool Usage Log" ([#916](https://github.com/Donkie/Spoolman/issues/916)) is open. There, the maintainer points to Prometheus for history (comment from 2026-04-21). A more recent duplicate ([#1069](https://github.com/Donkie/Spoolman/issues/1069)) was closed as a duplicate.
- Prometheus metrics are gauges only (including `spool_price`, `spool_weight_used`, `filament_density`, …: [SM `prometheus/metrics.py` L17-31](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/prometheus/metrics.py#L17-L31)), so they have no job reference either.
- What Coin-op could do: read `used_weight` at Run start and Run end and take the difference. This is **only correct** if exactly one spool is active during that time and nobody else books. Moonraker, for example, books incrementally every 5 s, and values from the HA integration can be up to 15 min old. This is our inference and not documented.

## 3. Event mechanism (WebSocket)

- A root WebSocket at `/api/v1/` reports "changes to any data" ([SM `router.py` L92-107](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/router.py#L92-L107)). In addition there are WebSockets at `/api/v1/spool` (all spools) and `/api/v1/spool/{id}` (one spool) ([SM `spool.py` L427-443, L737-753](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/spool.py#L427-L443)), and likewise for filament and vendor. The subscription hierarchy is a subscription tree ([SM `ws.py`](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/ws.py)).
- Message format `Event{type: added|updated|deleted, resource: spool|filament|vendor|setting, date, payload: <full object>}` ([models.py L897-942](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/spoolman/api/v1/models.py#L897-L942)). Tag scans travel over separate WebSockets with `scanned` (L945-954).
- Keepalive: the client sends text, the server replies `{"status":"healthy"}` (same place).
- Moonraker uses exactly this WebSocket to detect, for example, deletion of the active spool ([Moonraker `spoolman.py` L126-209](https://github.com/Arksine/moonraker/blob/b3f9566b8b8863ec85a00ce424d77c8e19576c44/moonraker/components/spoolman.py#L126-L209)).

## 4. Who reports usage? (Klipper vs. Anycubic)

- Spoolman itself measures nothing. According to its README it "integrates with" Moonraker, OctoPrint (plugin), OctoEverywhere, Home Assistant (Disane87) and MCP ([SM README L32-37](https://github.com/Donkie/Spoolman/blob/f9e819af43d59c8297acee9cdb86b96f6f6fc6ba/README.md#L32-L37)).
- **Moonraker** (Klipper) tracks the E-axis position, accumulates extrusion for the *single* active `spool_id` and sends `PUT …/use {"use_length": mm}` every `sync_rate` seconds (default 5) ([Moonraker `spoolman.py` L44, L261-330](https://github.com/Arksine/moonraker/blob/b3f9566b8b8863ec85a00ce424d77c8e19576c44/moonraker/components/spoolman.py#L261-L330)). The active spool is stored in Moonraker. Moonraker writes the `spool_ids` used per job into its own job history (auxiliary field "Spool IDs used", [L58-62](https://github.com/Arksine/moonraker/blob/b3f9566b8b8863ec85a00ce424d77c8e19576c44/moonraker/components/spoolman.py#L58-L62)). So the link between job and spool lives *in Moonraker*, not in Spoolman.
- **Anycubic Kobra S1 with stock firmware:** No known first-party route to Spoolman. Spoolman does not list Anycubic as an integration (README above). Community solutions:
  - [ToralionPL/anycubic-spoolman-integration](https://github.com/ToralionPL/anycubic-spoolman-integration): Node-RED reads via an "Anycubic MQTT Bridge" and maps ACE slots to spools via the convention `location = "AcePro Slot N"` (README). This confirms the `location` pattern from §1.
  - [xNoVoSx/kobra-spoolman](https://github.com/xNoVoSx/kobra-spoolman): bridge for Kobra S1 + ACE (2) Pro, books "consumption per spool" and supports Rinkhals and Klipper. According to the README, stock firmware also requires Rinkhals ("Works on the stock firmware with Rinkhals").
- **Kobra S1 with Rinkhals** (custom firmware, supports Kobra S1 and S1 Max): ships Moonraker, Mainsail and Fluidd as apps ([rinkhals-community/Rinkhals README](https://github.com/rinkhals-community/Rinkhals)). With that, the Moonraker Spoolman component works in principle. For the ACE Pro, however, stock Rinkhals keeps resetting the gates' `spool_id` and does not tie Moonraker's active spool to the loaded gate. The unofficial patch [edwinlepere/rinkhals-ace-spoolman-patch](https://github.com/edwinlepere/rinkhals-ace-spoolman-patch) addresses this (README, section "The problem it solves"). **Uncertain:** we have not checked how robust this is in daily use (community projects with 0-2 stars).
- **HA Anycubic integration** [WaresWichall/hass-anycubic_cloud](https://github.com/WaresWichall/hass-anycubic_cloud): according to the README it has ACE sensors and slot colours, but no Spoolman connection (code search for "spoolman" returned 0 hits). Last push was 2024-12-01. Whether it reports filament used per job was **not checked here** (belongs to the Kobra S1 ticket).
- **Consequence for Coin-op:** Without Moonraker, nobody books. Either Coin-op reports the Run's usage itself (from slicer estimate or printer data) via `use` or `spoolman.use_spool_filament`, or the user runs one of the bridges. Coin-op would have to know the spool-to-slot assignment itself (configuration or a `location`/`extra` convention).

## 5. HA integration Disane87/spoolman-homeassistant

### Architecture
- `iot_class: local_polling` ([HA `manifest.json`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/manifest.json)). A `DataUpdateCoordinator` fetches `GET /spool`, `/filament`, `/field/spool` and `/location`; the interval is `timedelta(minutes=update_interval)` ([HA `coordinator.py` L23-133](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/coordinator.py)). Default 15 min, minimum 1 ([HA `schema_helper.py` L77-79](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/schema_helper.py#L77-L79)). **No WebSocket**, not on `dev` either (grep for `websocket` found nothing, `iot_class` unchanged).
- Per filament, `total_remaining_weight` is aggregated over all non-archived spools (coordinator.py).

### Entities (one device per spool, with a "Location" hub device as `via_device`)
Sensor classes in [HA `sensors/`](https://github.com/Disane87/spoolman-homeassistant/tree/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/sensors): `spool` (state = `remaining_weight` in g), `spool_used_weight`, `spool_weight` (tare), `spool_remaining_length`, `spool_used_length`, `spool_used_percentage`, `spool_price`, `spool_location`, `spool_lot_number`, `spool_comment`, `spool_first_used`, `spool_last_used`, `spool_registered`, `spool_id`, `spool_flow_rate` (g/h, computed in HA), `spool_estimated_run_out`, `spool_extra_field` (one per extra field), `filament_material`, `filament_name`, `filament_color_hex`, `filament_density`, `filament_diameter`, `filament_weight`, `filament_extruder_temp`, `filament_bed_temp`, `filament_article_number`, `vendor_name`. In addition, a filament device sensor (`filament.py`, state = `total_remaining_weight`, attributes = flattened filament JSON incl. `price`).

Relevant for the Cost Source:
- The main sensor `sensor.spoolman_spool_<id>` exposes **the entire flattened spool JSON** as attributes, e.g. `price`, `filament_price`, `filament_material`, `filament_weight`, `initial_weight`, `filament_vendor_name`, `location`, `extra_*` ([HA `sensors/spool.py` `extra_state_attributes` + `flatten_dict`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/sensors/spool.py)).
- `sensor.spoolman_spool_<id>_price` reports only `spool.price`, so it is `None` if only the filament price is maintained. It has no `unit_of_measurement` and no currency, just the icon `mdi:currency-usd` ([HA `sensors/spool_price.py`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/sensors/spool_price.py)). This matches the open issue "should report units to Home Assistant" ([#898](https://github.com/Disane87/spoolman-homeassistant/issues/898)).
- A `select` entity per spool sets the `location` via PATCH ([HA `select.py` L103-177](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/select.py#L103-L177)). This could be used in HA to set "spool X is in ACE slot 2", provided the locations are named accordingly.
- A "Low Filament" `binary_sensor` per spool ([HA `binary_sensor.py`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/binary_sensor.py)) and the HA event `spoolman_spool_threshold_exceeded` ([HA `const.py`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/const.py)).
- Entity IDs are stable by spool ID (`sensor.spoolman_spool_<id>…`), but there is **no entity per material type**. Material is an attribute or a sensor per spool. Coin-op would have to aggregate a "price per PLA" itself.

### Services ([HA `services.yaml`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/services.yaml), registered in [`__init__.py` L78-109](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/__init__.py#L78-L109))
- `spoolman.use_spool_filament` (`id`, `use_weight` | `use_length`) calls `PUT /spool/{id}/use` and then triggers a coordinator refresh ([`classes/spoolman_api.py` L213-240](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/classes/spoolman_api.py#L213-L240)).
- `spoolman.patch_spool` (`id` plus any spool fields incl. `price`, `used_weight`, `location`, `extra`) calls `PATCH /spool/{id}`. Note: the service description calls `initial_weight` "including filament". Spoolman defines the field as *net weight*, so the integration's docs are imprecise here.
- Neither service returns a **response** (no `supports_response`). So from HA you do not directly get the new spool state back.
- The built-in Klipper part (`klipper_url`, attribute `klipper_active_spool`, reads Moonraker's `/server/spoolman/spool_id`: [HA `classes/klipper_api.py`](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/custom_components/spoolman/classes/klipper_api.py)) is **deprecated and slated for removal** according to the README ([README L29-36](https://github.com/Disane87/spoolman-homeassistant/blob/d763826eae1f91477d53fa5f3919f75311ca03a7/README.md#L29-L36)).

### Maintenance status (GitHub API, as of 2026-11-19)
- Not archived, 266 stars, 22 open issues, last push 2026-11-12 (branches).
- Latest stable release `v1.4.0` from 2026-05-10. Pre-releases `v1.4.0-dev.3`/`dev.4` from 2026-06-02. `dev` is 96 commits ahead of `main`, a larger refactor (including `entity.py`, `models.py`, `diagnostics.py`, `quality_scale.yaml`); the most recent dev commits (Oct. 2026) are Renovate dependency bumps.
- Open problems relevant to Coin-op: HA deprecation of `via_device`, breaking in HA 2027.8.0 ([#887](https://github.com/Disane87/spoolman-homeassistant/issues/887)), missing units ([#898](https://github.com/Disane87/spoolman-homeassistant/issues/898)) and "Remaining weight not updating" ([#850](https://github.com/Disane87/spoolman-homeassistant/issues/850)).
- Assessment: the integration is maintained, but releases are infrequent and it depends heavily on a single code owner (per `manifest.json`). This is an inference from the metadata above.

### Other HA-related projects (only surveyed, code not checked)
- [metaathron/ha-spoolman-active](https://github.com/metaathron/ha-spoolman-active): extends Disane87 with an "active spool per printer", but via **Moonraker**. Only relevant for the Kobra S1 with Rinkhals.
- [gibz104/SpoolmanSync](https://github.com/gibz104/SpoolmanSync), [marcokreeft87/spoolman-updater](https://github.com/marcokreeft87/spoolman-updater): slot assignment and usage booking via HA, but for Bambu Lab or Creality, not Anycubic. SpoolmanSync keeps its own print history with deductions per spool (README). This shows that Spoolman itself lacks such a history.
- No official HA core Spoolman integration was found (GitHub search "spoolman home assistant"). **Uncertain:** the HA core integration list was not checked separately.

## 6. Implications for Coin-op (inference, not sourced)

1. **Cost Source "Spoolman":** Most robust directly against the REST API (`GET /api/v1/spool/{id}` or `/filament`), optionally with the WebSocket `/api/v1/spool` for live updates. This is independent of the polling interval and the quirks of the HA integration. Alternatively, read the attributes `filament_price`/`price`/`initial_weight`/`filament_weight` from the sensor `sensor.spoolman_spool_<id>`, which allows a generic "Cost Source = HA entity attribute" solution.
2. **Price per gram** = `(spool.price ?? filament.price) / (spool.initial_weight ?? filament.weight)`. If any of these values is missing, there is no price and a fallback is needed.
3. **Material type**: `filament.material` is free text, so a mapping to a Coin-op "Material" has to be tolerant (e.g. "PLA+", "PLA Matte").
4. **Spool in the Run**: Spoolman does not know it. For the Kobra S1, CoinOp has to configure it or read it from `location`/`extra`, e.g. with a convention "ACE Slot N".
5. **Booking back** via `use` or `spoolman.use_spool_filament` is possible, but not idempotent and without a Run reference. Double bookings with Moonraker or bridges have to be avoided if they run in parallel.
