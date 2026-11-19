# Contributing

## Layout

- `custom_components/wattbill/`: the integration. Everything shipped to users lives here, including `translations/` (en and de, same keys) and `brand/`.
- `tests/`: backend tests, run inside a real Home Assistant test instance.
- `frontend/`: the sidebar panel (TypeScript + Lit). It builds into `custom_components/wattbill/frontend/wattbill-panel.js`, which is gitignored and built by CI.
- `scripts/test_ha.py`: runs the tests against the minimum, stable or beta Home Assistant release.
- `scripts/release.py`: builds the release asset `wattbill.zip` from a version tag (see [Release](#release)).
- `GLOSSARY.md`: domain terms; use them in code, tests and docs. Decisions go in `docs/adr/`.

### Backend modules

- `config_flow.py`: the hub entry and its options flow (`OPTIONS_SCHEMA`; `_async_validate` checks the input, e.g. the Spoolman URL against Spoolman's info endpoint; a new hub option is one field there plus its check and its `options.step.init` strings). Saving the options reloads the entry. `device_flow.py`: the Device subentry flow, one step per part of the Device's data (`printer_device_id`, `status`, `mapping`, `job`, `images`, `consumption`, `price`). Steps are grouped into sections (`DeviceSubentryFlow._sections`): Add Device walks them in order, reconfigure offers them as a menu and returns to it after each; a new section is one entry there plus its menu label. `profiles.py`: the Integration Profiles (`PROFILES`, by integration domain; ADR 0004). `detect` reads the printer's HA device and the devices linked to it (e.g. an ACE unit) from the registries and returns the `status`, `mapping`, `job` and `images` sections it can fill, matching entities by unique id suffix; Add Device starts from them, and reconfigure's "Detect again" (offered only when `detect` knows the device) walks those sections pre-filled with them. A new profile is one function there. `device_config.py` reads that data into a `DeviceConfig`; `device_inputs.py` reads Device Inputs from HA states and the entity registry, including meter readings converted to kWh or W (`meter_reading`, units via HA's unit converters, else the user's conversion factor) and prices converted to `<currency>/kWh` (`price_reading`; `price_scale` understands the currency's code or symbol and sub-units like ct ÷ 100, per Wh/kWh/MWh).
- `models.py`: `Run` and `LineItem`, free of HA types, with the JSON shape the Stores keep (`as_dict` / `from_dict`). A Run keeps the consumption section it started with (`Run.consumption`, so a source change applies from the next Run) and, until finalised, its meter's `readings`. A Line Item's `quantity`, `unit_price` and `amount` are what counts; `LineItem.override` takes the user's values (an amount back-computes the unit price) and, on a computed Line Item (`is_computed`), keeps WattBill's values in `computed` until `reset`. Which Line Items are live (`Run.locked`: computed ones until the Run is final), deletable (`Run.deletable`) and allow negative prices (`negative_prices`) is decided there too; `websocket/line_items.py` (`wattbill/line_items/update`, `reset`, `add`, `delete`) applies these rules.
- `materials.py`: `Material`, free of HA types, with its built-in types (form and density for pre-filling) and its Cost Source (`PRICE_SOURCES`: each source gives a `per_gram(density)` price; `fixed` from pack price and size, `spoolman` the last price per gram read from the linked Spoolman Filament).
- `spoolman.py`: Spoolman over its REST API (URL from the hub options, `CONF_SPOOLMAN_URL`). `Spoolman.async_filaments` reads every Filament with its price per gram (`filament.price ÷ weight`, else the newest priced spool) and syncs the linked Materials (`Catalog.async_sync_spoolman`: price, type, density, diameter, colour, vendor; without a price in Spoolman the last one stays); the tracker calls `async_update_prices` before freezing a Run; `async_create_material` / `async_link` create or link a Material. Any failure raises `SpoolmanUnreachable`.
- `catalog.py`: `Catalog`, the global catalogues (Materials so far) in the `catalog` Store. Every change is saved at once and announced by catalogue name (`async_listen`). Deleting a Material a Run's Line Item references (`LineItem.material_id`) archives it instead.
- `cost/`: the pure cost core (no HA imports): `consumption.py` (kWh between two moments: estimate, energy meter interpolated between readings, power sensor by the left rule; `piecewise` switches models when the average power changed), `electricity.py` (price segments from a price timeline whose gaps take the last valid price, and the Electricity Line Item), `running_time.py` (running time without pauses), `slots.py` (Slot attribution: each loaded Slot report's share of running time, and its Material by type and colour, else the type's default), `material.py` (Material Line Items; `slot_line_items` makes one per Material and splits the measured total by share), `totals.py` (per-Device totals advanced by deltas).
- `tracker.py`: the Run engine for one Device (Status input → open, pause, end Run; reconciling after an outage; job changes; meter readings with gap and reset Flags; live refresh every minute and on each price report, finalisation; before freezing it reads Spoolman and flags `spoolman_unreachable` if that failed for a Run whose Material Line Items use a linked Material). The open Run keeps its price timeline (`Run.prices`, cleared at finalisation) and the average powers it used (`Run.average_powers`); a Device's new price or average power is appended from the moment the tracker starts with it (`_async_follow_device`), so it never recomputes what came before. A metered Run waits up to five minutes after its end for the meter's next report; `_end` returns a future done once the Run is finalised. While a Run is open, the Loaded slot input and the Slot entities build `Run.loaded_slots` (which Slot it printed from since when, with its reported type and colour; cleared at finalisation); the measured Material Line Items follow it, and finalisation flags `estimated_split` and `slot_fallback`. On start, `async_start` fills each unfinalised metered Run's missed reports from recorder history before applying the Status input. `async_create_run` makes a manual Run, final at once: electricity from recorder history if it covers the Run (`recorded.py`: the recorder was recording throughout and the meter had a reading at the start), else estimated from the average running power, else `entered` (not computed: the user types the kWh); the Material Line Item is left for the user to weigh.
- `run_book.py`: all Runs in memory; every change goes through it so Stores, totals and listeners (`async_listen`) stay in step. User corrections go through `async_correct` (announced as `updated`, so `ended` never refires) and deletions through `async_delete` (announced as `deleted`; a listener on `RunChange.DELETED` is the place to remove a Run's files). `async_correct` also records a new image. Manual Runs go through `async_add` (announced as `created`, never `ended`).
- `images/`: Run images. `library.py` (`ImageLibrary`) stores an image on its Run (`async_add`: re-encoded by `encode.py`, a new Thumbnail or Snapshot replaces the old one), keeps the files under `files_path(hass)/images/<run id>/`, deletes a Run's files when it is deleted and removes files no Run refers to at startup. `capture.py` (`DeviceImages`, one per Device, driven by its tracker) copies the Thumbnail while a Run is open and takes the Snapshot when it ends. `view.py` serves the images to admins only (`image_info` gives the panel their URLs; the Run stores metadata only); `upload.py` takes the panel's multipart photo upload (`async_upload`: up to `UPLOAD_LIMIT` per Run, JPEG/PNG/WebP, all or none). `async_delete` deletes one image; `Run.cover_id` is the picked Cover Image, which `Run.cover` checks first. The websocket commands for them are in `websocket/images.py`.
- `device_settings.py`: a Device's panel settings (WattBill's own per-Device settings, set in the Devices tab), kept in the `device_settings` Store. A new setting is one entry in `FIELDS` (default and the schema a new value must pass); it then appears in `wattbill/devices/list` and can be changed with `wattbill/devices/update_settings`. Settings of removed Devices are dropped at setup.
- `store.py`: every Store (registered in `SCHEMAS`) and the file folder (`files_path`). `WattBillStores` loads them together at setup (failing on missing or newer-major data), copies a Store to `<key>.bak` before a major migration and deletes everything when the hub entry is removed; `RunStore` writes Runs to `runs` and `live`. A new Store or file kind only registers there.
- `repairs.py`: the fix flow for missing data (restore guidance or a deliberate fresh start). `backup.py`: writes pending delayed saves before a backup.
- `ha_device.py`: WattBill's own HA device per Device (registered at setup, linked to the printer's HA device), its `device_info`, and renames from the HA device page. Removing a Device ends its open Run as Unknown in `__init__.py` before the reload; `Run.device_name` always holds the Device's current name.
- `entity.py`: `DeviceEntity`, the base of every per-Device entity (device info, re-read on any change to one of the Device's Runs). `sensor.py`: totals, Current and Last Run cost, Flagged Runs. `event.py`: the Run event (`started`, and `ended` only from finalisation).
- `cost/rounding.py`: amounts rounded to the currency's decimals; subtotals and totals are sums of rounded amounts.
- `aggregates.py`: totals across Runs grouped by any of `DIMENSIONS` (kind, Device, month, Material, Outcome, Tag) for the Overview and Analysis. Line Items are the facts: cost, grams and kWh sum the Line Items in a group, while Runs, running hours and Flagged Runs count each Run once per group it has a Line Item in, so Material and Tag groups overlap. `run_measures` is the same totals for a list of Runs (the deletion preview).
- `statement/`: the Cost Statement PDF (ADR 0005). `export.py` has the export options (`Options`; a new option is one field there, in the schema of `wattbill/cost_statement/create` in `websocket/cost_statement.py` and in the panel's dialog) and `CostStatements`, which keeps each export's Runs and options for `EXPIRES` behind a token, plus the default Markup from the hub options (`CONF_MARKUP`). `view.py` serves `/api/wattbill/cost_statement/{token}` to admins; the panel reaches it through the signed path `create` returns. On each download it renders the ended Runs as they are now, ordered by start, in the executor. `document.py` lays out the PDF with fpdf2 (`render`: header, a section per Run or a compact table, totals with Markup on the rounded subtotal, a footer on every page). `keep_together` keeps a block on one page unless it is longer than a page. `text.py` holds the strings from `strings/{en,de}.json` (their own files, not HA translations) and formats money, numbers and dates for the language. `fonts/` has Noto Sans with its OFL licence.
- `panel.py`: registers the admin-only panel while the hub entry is loaded and serves the bundle at a URL that changes with its content.
- `websocket/`: the panel's backend API, one module per area (`runs.py`, `devices.py`, `materials.py`, `catalog.py`, ...). See [Websocket commands](#websocket-commands).

### Panel modules

- `src/wattbill-panel.ts`: the element HA creates. It receives only `hass`, `narrow`, `route` and `panel`, keeps the Runs and the catalogue subscription, loads the Devices (again when the Devices tab opens or a Run of an unlisted Device changes) and routes by `route.path` (`""` Overview, `/run/<id>` Run page, `/<tab>` for each toolbar tab in `TABS`; a new tab is one entry there, a `tab.<name>` string and its view in `renderPage`). A Run whose `device_id` is not among the loaded Devices belongs to a removed Device (`deviceName` in `run-parts.ts`).
- `src/api.ts`: the websocket commands and the shapes they return. `src/hass.ts`: the part of `hass` the panel uses, plus `navigate` / `followLink` for in-app links.
- `src/overview.ts` (`<wattbill-overview>`): tiles and charts from `wattbill/aggregates/get` (drawn by `src/charts.ts` as inline SVG), the Runs running now, the gallery and the basket of selected final Runs (`selectedRuns()`, by start; its actions sit in the basket's `.actions` row, starting with "Cost Statement…"). It owns the gallery's filter and selection, and the panel keeps it (lit `cache`) while other pages show, so both survive a visit to a Run page. `src/run-gallery.ts`: filters (`Filter`, `NO_FILTER`, `matches`), tiles and checkboxes; it reports `filter-changed` / `selection-changed`.
- `src/analysis-page.ts` (`<wattbill-analysis-page>`): the Analysis tab's tables of totals by kind, Device, month, Material, Outcome and Tag, each one `wattbill/aggregates/get` grouping, read afresh whenever a Run changes. Material comes from the `["kind", "material"]` grouping, so Electricity and Other Line Items don't count as "No Material"; the Tag table has no total row, since its groups overlap.
- `src/run-page.ts`, `src/devices-page.ts`, `src/materials-page.ts`: the other views; `src/manual-run-dialog.ts`: the toolbar's "+ Manual Run" dialog; `src/statement-dialog.ts`: the basket's export dialog, which downloads the PDF with `download(path)` from `src/hass.ts`. `src/run-parts.ts`: pieces several show (`deleteDialog` for the delete confirmation with what the sensor totals drop). `src/run-image.ts`: one Run image, fetched with `hass.fetchWithAuth` (the image views need authentication, which `<img src>` can't send) and shown from a blob URL, or the placeholder. `src/styles.ts`: shared styles on HA's theme variables.
- `src/localize.ts` with `src/translations/{en,de}.json` (flat keys): panel strings, chosen by `hass.language`, falling back to English. `src/format.ts`: money, dates and durations.

## Setup

Python is managed by [uv](https://docs.astral.sh/uv/); the system Python is not used. Home Assistant needs Python 3.14 (pinned in `.python-version`).

```sh
uv sync
```

This creates `.venv` with Home Assistant, the test harness ([pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)), ruff and mypy, pinned in `uv.lock`.

The panel needs Node.js (version in `frontend/.nvmrc`):

```sh
cd frontend
npm ci
npm run build    # or: npm run watch
```

Reload the browser after a rebuild; the bundle URL changes with its content when HA restarts or the entry reloads.

## Test

```sh
uv run pytest                           # all tests, against the locked HA version
uv run pytest tests/test_config_flow.py -k second
uv run scripts/test_ha.py minimum -q    # also: stable, beta (each in its own .venv-<target>)
```

`scripts/test_ha.py` picks the harness release that pins the wanted HA version. The harness can lag behind a new HA release; the stable run then warns and tests the newest HA the harness supports. When raising the minimum HA version in `hacs.json`, update `MINIMUM_HARNESS_VERSION` in the script too (it fails if they disagree).

### Writing tests

- Drive WattBill the way Home Assistant and the user do (config flows, entity states, websocket commands, the clock) and assert on what they can observe. Don't import internals.
- Each test gets a fresh HA instance through the `hass` fixture.
- Time is frozen and moved explicitly with the `clock` fixture from `tests/conftest.py`:

  ```python
  async def test_something(hass: HomeAssistant, clock: Clock) -> None:
      ...
      await clock.advance(minutes=5)  # fires every HA timer that is now due
      await clock.move_to(CLOCK_START + timedelta(days=1))
  ```

  `Clock` and `CLOCK_START` come from `tests/clock.py`.

- Schema changes: a minor bump only adds fields (read with a default); a major bump adds a migration to the Store's `Schema` and a folder to `tests/fixtures/storage/` for the version just released (see `tests/test_migrations.py`).
- `tests/devices.py` sets up the hub (`add_hub`) and walks Add Device through the real flow (`add_device`, `walk_to_mapping`, `add_printer` for a printer's HA device) and reconfigure (`start_reconfigure`, `reconfigure`); `add_device(source="energy" | "power", meter={...})` picks a measured source, `walk_to_consumption` stops at its menu; `add_device(price={"entity_id": ...})` picks a price entity, `walk_to_price` stops at the price menu. `tests/test_dynamic_price.py` has `set_price` and `segments`. `tests/test_measured.py` has `set_meter`, `set_power` and `add_metered_device`. `add_device(material=...)` sets the Material used input (`material_attribute` and `material_unit` for an attribute); `tests/test_material_usage.py` has `set_usage` and `add_measuring_device` (with a default Material). `add_device(slots=[...], colour_attribute=..., loaded_slot=...)` sets the Slots; `tests/test_slots.py` has `fill` (a Slot's type and colour), `load` (the Loaded slot) and `add_ace_device`. `tests/anycubic.py` registers a Kobra S1 + ACE Pro the way each Anycubic integration does (`add_anycubic_local`, `add_anycubic_cloud`; `printer[key]` is an entity id by the integration's key); `tests/test_integration_profiles.py` has `walk_pre_filled` (Add Device accepting every pre-filled step) and `accepted` (a form submitted as pre-filled). A Device without Material used input or default Material flags every Run it ends with `NO_MATERIAL` (`tests/test_runs.py`). Tests that need recorder history override `mock_recorder_before_hass` in their own module (see `tests/test_recorder_history.py`), so the recorder only runs there. Stored Runs are read from the `hass_storage` fixture (`wattbill.runs`, `wattbill.live`).
- Spoolman's REST API is mocked with the harness's `aioclient_mock`: `tests/test_spoolman.py` has `serve_spoolman(aioclient_mock, filaments=[filament(7, ...)], spools=[spool(1, of, ...)])` (Filaments and spools in Spoolman's own JSON shape), `spoolman_down`, `add_spoolman_hub` (hub with the Spoolman URL set through the options flow), `set_options` and `link`.
- `tests/stored.py` places Runs, Materials and Tags in the Stores before setup (`place_runs(hass_storage, stored_run("id", ...))`, `place_materials(hass_storage, stored_material("id", ...))`, `place_tags(hass_storage, "Gift", ...)`).
- Images: `tests/images.py` has a fake Thumbnail image entity (`add_thumbnail`, then `.show(picture("green"))`) and a fake camera (`add_camera(hass, *answers)`, `.requests`), `picture(...)` to make images with metadata, and `colour` / `opened` to read stored ones. Fetch from WattBill's HTTP views with the `http` fixture (`await http.content(url)`, `await http.upload(url, *photos)`; `connect_http(user)` for others). Use the `files` fixture in tests that store images: it gives the test its own config directory and returns WattBill's file folder.
- Cost Statement: `tests/test_cost_statement.py` exports the way the panel does (`export(panel, browser, run_ids=[...], ...)`) and reads the PDF's text per page with pypdf (`Statement.pages`, `.lines`, `.paper` in mm, `.filename`). The `browser` fixture fetches without an auth header, like a plain download link, so only a signed path gets in; `HttpClient.download(path)` also returns the headers.
- Websocket commands go through the `panel` fixture (an admin's connection; `connect_panel(hass_read_only_user)` for others): `await panel.call("wattbill/runs/get", run_id=...)`, `await panel.error(...)`, `await panel.subscribe(...)` then `await panel.event()` (events pushed before a command's result are kept for `event()`). It connects on first use, so set WattBill up first.

### Panel tests

```sh
cd frontend
npm test                 # vitest, in happy-dom
npx vitest run -t "Run page"
```

- Tests mount `<wattbill-panel>` the way HA does (`mountPanel(backend, { path, narrow })` in `test/render.ts`) and assert on rendered text (`text`, `query`, `queryAll` pierce shadow roots; `click` and `fill` act like the user) and on the messages the panel sent (`backend.calls`).
- `test/fake-hass.ts` is the fake `hass`: `recordedBackend()` answers with recorded backend responses; `.reply(type, msg => result)` answers `callWS` (throw `new WsError(code)` to fail), `.subscription(type, msg => initialEvents)` accepts a subscription, `.push(type, event)` sends an event, `.update({...})` hands over a new `hass` like HA does, `.file(path)` serves an image to `fetchWithAuth` (`recordedBackend()` serves every recorded image; anything else answers 404) and `.fetches` lists what was fetched.
- The recorded responses under `frontend/test/fixtures/backend/` are written by `tests/test_panel_contract.py` from the real backend, and that test fails when the backend's answers change. Re-record after an intended change and commit the JSON:

  ```sh
  UPDATE_FIXTURES=1 uv run pytest tests/test_panel_contract.py
  ```

  A new command gets its recording in the same test file (use `stable_ids` for generated ids) and a getter on `recorded`.

## Lint and type check

```sh
uv run ruff check .
uv run ruff format .        # CI runs: uv run ruff format --check .
uv run mypy
```

```sh
cd frontend
npm run lint                # eslint and prettier --check; npm run format fixes formatting
npm run typecheck
```

## CI

`.github/workflows/ci.yaml` runs on every push, pull request and nightly: hassfest, HACS validation, lint and type check, the panel's lint, type check, tests and build, and the backend tests against the minimum, stable and beta HA releases.

## Release

The committed `manifest.json` keeps the placeholder version `0.0.0`; a release gets its version only from its tag.

1. Push a tag with the version, without a `v` prefix: `1.2.0`, or `1.2.0b1` / `1.2.0rc1` for a pre-release (releases before 1.0 are pre-releases).
2. `.github/workflows/release.yaml` builds the panel, runs `scripts/release.py` (which fails for any other tag) to zip `custom_components/wattbill/` with the tag as the manifest's version, and creates a **draft** release with `wattbill.zip` and generated notes, marked as a pre-release for `b` / `rc` tags.
3. Edit the notes (they become the release notes users see in Home Assistant; mention any raise of the minimum HA version) and publish the release. HACS and the Marketplace only offer published releases.

To check an asset locally: build the panel, then `uv run scripts/release.py 1.2.0b1 custom_components/wattbill dist`.

## Conventions

- Everything in the repository is written in English.
- No user-facing text in Python: put it in `translations/en.json` and `translations/de.json` with identical keys (a test enforces this).
- Panel strings live in `frontend/src/translations/` with identical keys in every language. A term the backend translates too is listed in `SHARED_TERMS` in `tests/test_panel_translations.py`, which checks both sides read the same.
- Comments only for a non-obvious *why*.

### Websocket commands

- Named `wattbill/<area>/<verb>` (`wattbill/runs/list`, `wattbill/runs/get`, ...), defined in `websocket/<area>.py` and listed in its `COMMANDS`; `websocket/__init__.py` registers every module's `COMMANDS`.
- Build each with `@command({vol.Required("type"): "wattbill/...", ...})` from `websocket/command.py`: it makes the command admin-only, answers `not_loaded` while the hub entry isn't loaded, and passes the loaded `WattBill` (sync or async handler).
- Results are objects (`{"runs": [...]}`, `{"run": {...}}`), never bare lists. Missing things answer `not_found`. Amounts are sent rounded with `cost/rounding.py`; the panel never adds amounts up itself.
- Subscriptions send their full state as the first event, then one event per change. Run changes reach them through the `SIGNAL_RUN_CHANGED` dispatcher signal, so a subscription survives reloads of the hub entry. Every `RunBook` change (`RunChange`) is forwarded as `{"change": ..., "run": summary}`, including `"deleted"`.
- Commands that change a Run answer with the Run in full (`{"run": ...}`), like `get`. Deleting is previewed: `delete_preview` and `delete` both answer `{"drop": ...}`, what the sensor totals lose.
- `wattbill/catalog/subscribe` sends every catalogue first (`{"materials": [...]}`), then, after each change, the whole changed catalogue (`{"materials": [...]}`) through `SIGNAL_CATALOG_CHANGED`. A new catalogue adds its entry to `CATALOGUES` in `websocket/catalog.py` and announces its name from `Catalog`; the panel keeps one catalogue subscription and merges each event into what it has.
- `wattbill/aggregates/get` takes `group_by` (a list of dimensions, none for one grand total) and answers `{"groups": [...]}`: each group's values (`month` as "YYYY-MM" in HA's time zone, `device_id` with `device_name`, `material_id` with `material_name`; `null` for none) followed by the totals `delete_preview` also sends. There are no groups without Runs. The panel reads them afresh after each Run change rather than subscribing.
- Fields of a catalogue entry travel nested (`{"type": "wattbill/materials/create", "material": {...}}`), since a Material's `type` would clash with the command's.
