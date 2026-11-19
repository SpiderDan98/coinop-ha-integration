# Contributing

## Layout

- `custom_components/wattbill/`: the integration. Everything shipped to users lives here, including `translations/` (en and de, same keys) and `brand/`.
- `tests/`: backend tests, run inside a real Home Assistant test instance.
- `frontend/`: the sidebar panel (TypeScript + Lit). It builds into `custom_components/wattbill/frontend/wattbill-panel.js`, which is gitignored and built by CI.
- `scripts/test_ha.py`: runs the tests against the minimum, stable or beta Home Assistant release.
- `GLOSSARY.md`: domain terms; use them in code, tests and docs. Decisions go in `docs/adr/`.

### Backend modules

- `config_flow.py`: the hub entry; `device_flow.py`: the Device subentry flow, one step per part of the Device's data (`printer_device_id`, `status`, `mapping`, `job`, `consumption`, `price`). Steps are grouped into sections (`DeviceSubentryFlow._sections`): Add Device walks them in order, reconfigure offers them as a menu and returns to it after each; a new section is one entry there plus its menu label. `device_config.py` reads that data into a `DeviceConfig`; `device_inputs.py` reads Device Inputs from HA states and the entity registry, including meter readings converted to kWh or W (`meter_reading`, units via HA's unit converters, else the user's conversion factor) and prices converted to `<currency>/kWh` (`price_reading`; `price_scale` understands the currency's code or symbol and sub-units like ct ÷ 100, per Wh/kWh/MWh).
- `models.py`: `Run` and `LineItem`, free of HA types, with the JSON shape the Stores keep (`as_dict` / `from_dict`). A Run keeps the consumption section it started with (`Run.consumption`, so a source change applies from the next Run) and, until finalised, its meter's `readings`.
- `cost/`: the pure cost core (no HA imports): `consumption.py` (kWh between two moments: estimate, energy meter interpolated between readings, power sensor by the left rule; `piecewise` switches models when the average power changed), `electricity.py` (price segments from a price timeline whose gaps take the last valid price, and the Electricity Line Item), `running_time.py` (running time without pauses), `totals.py` (per-Device totals advanced by deltas).
- `tracker.py`: the Run engine for one Device (Status input → open, pause, end Run; reconciling after an outage; job changes; meter readings with gap and reset Flags; live refresh every minute and on each price report, finalisation). The open Run keeps its price timeline (`Run.prices`, cleared at finalisation) and the average powers it used (`Run.average_powers`); a Device's new price or average power is appended from the moment the tracker starts with it (`_async_follow_device`), so it never recomputes what came before. A metered Run waits up to five minutes after its end for the meter's next report; `_end` returns a future done once the Run is finalised. On start, `async_start` fills each unfinalised metered Run's missed reports from recorder history before applying the Status input.
- `run_book.py`: all Runs in memory; every change goes through it so Stores, totals and listeners (`async_listen`) stay in step.
- `store.py`: every Store (registered in `SCHEMAS`) and the file folder (`files_path`). `WattBillStores` loads them together at setup (failing on missing or newer-major data), copies a Store to `<key>.bak` before a major migration and deletes everything when the hub entry is removed; `RunStore` writes Runs to `runs` and `live`. A new Store or file kind only registers there.
- `repairs.py`: the fix flow for missing data (restore guidance or a deliberate fresh start). `backup.py`: writes pending delayed saves before a backup.
- `ha_device.py`: WattBill's own HA device per Device (registered at setup, linked to the printer's HA device), its `device_info`, and renames from the HA device page. Removing a Device ends its open Run as Unknown in `__init__.py` before the reload; `Run.device_name` always holds the Device's current name.
- `entity.py`: `DeviceEntity`, the base of every per-Device entity (device info, re-read on any change to one of the Device's Runs). `sensor.py`: totals, Current and Last Run cost, Flagged Runs. `event.py`: the Run event (`started`, and `ended` only from finalisation).
- `cost/rounding.py`: amounts rounded to the currency's decimals; subtotals and totals are sums of rounded amounts.
- `panel.py`: registers the admin-only panel while the hub entry is loaded and serves the bundle at a URL that changes with its content.
- `websocket/`: the panel's backend API, one module per area (`runs.py`, ...). See [Websocket commands](#websocket-commands).

### Panel modules

- `src/wattbill-panel.ts`: the element HA creates. It receives only `hass`, `narrow`, `route` and `panel`, keeps the Runs subscription and routes by `route.path` (`""` gallery, `/run/<id>` Run page).
- `src/api.ts`: the websocket commands and the shapes they return. `src/hass.ts`: the part of `hass` the panel uses, plus `navigate` / `followLink` for in-app links.
- `src/run-gallery.ts`, `src/run-page.ts`: the views. `src/run-parts.ts`: pieces both show. `src/styles.ts`: shared styles on HA's theme variables.
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
- `tests/devices.py` sets up the hub (`add_hub`) and walks Add Device through the real flow (`add_device`, `walk_to_mapping`, `add_printer` for a printer's HA device) and reconfigure (`start_reconfigure`, `reconfigure`); `add_device(source="energy" | "power", meter={...})` picks a measured source, `walk_to_consumption` stops at its menu; `add_device(price={"entity_id": ...})` picks a price entity, `walk_to_price` stops at the price menu. `tests/test_dynamic_price.py` has `set_price` and `segments`. `tests/test_measured.py` has `set_meter`, `set_power` and `add_metered_device`. Tests that need recorder history override `mock_recorder_before_hass` in their own module (see `tests/test_recorder_history.py`), so the recorder only runs there. Stored Runs are read from the `hass_storage` fixture (`wattbill.runs`, `wattbill.live`).
- `tests/stored.py` places Runs in the Stores before setup (`place_runs(hass_storage, stored_run("id", ...))`).
- Websocket commands go through the `panel` fixture (an admin's connection; `connect_panel(hass_read_only_user)` for others): `await panel.call("wattbill/runs/get", run_id=...)`, `await panel.error(...)`, `await panel.subscribe(...)` then `await panel.event()`. It connects on first use, so set WattBill up first.

### Panel tests

```sh
cd frontend
npm test                 # vitest, in happy-dom
npx vitest run -t "Run page"
```

- Tests mount `<wattbill-panel>` the way HA does (`mountPanel(backend, { path, narrow })` in `test/render.ts`) and assert on rendered text (`text`, `query`, `queryAll` pierce shadow roots) and on the messages the panel sent (`backend.calls`).
- `test/fake-hass.ts` is the fake `hass`: `recordedBackend()` answers with recorded backend responses; `.reply(type, msg => result)` answers `callWS` (throw `new WsError(code)` to fail), `.subscription(type, msg => initialEvents)` accepts a subscription, `.push(type, event)` sends an event, `.update({...})` hands over a new `hass` like HA does.
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

## Conventions

- Everything in the repository is written in English.
- No user-facing text in Python: put it in `translations/en.json` and `translations/de.json` with identical keys (a test enforces this).
- Panel strings live in `frontend/src/translations/` with identical keys in every language. A term the backend translates too is listed in `SHARED_TERMS` in `tests/test_panel_translations.py`, which checks both sides read the same.
- Comments only for a non-obvious *why*.

### Websocket commands

- Named `wattbill/<area>/<verb>` (`wattbill/runs/list`, `wattbill/runs/get`, ...), defined in `websocket/<area>.py` and listed in its `COMMANDS`; `websocket/__init__.py` registers every module's `COMMANDS`.
- Build each with `@command({vol.Required("type"): "wattbill/...", ...})` from `websocket/command.py`: it makes the command admin-only, answers `not_loaded` while the hub entry isn't loaded, and passes the loaded `WattBill` (sync or async handler).
- Results are objects (`{"runs": [...]}`, `{"run": {...}}`), never bare lists. Missing things answer `not_found`. Amounts are sent rounded with `cost/rounding.py`; the panel never adds amounts up itself.
- Subscriptions send their full state as the first event, then one event per change. Run changes reach them through the `SIGNAL_RUN_CHANGED` dispatcher signal, so a subscription survives reloads of the hub entry. Every `RunBook` change (`RunChange`) is forwarded as `{"change": ..., "run": summary}`; the panel already handles `"deleted"`.
