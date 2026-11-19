# Contributing

## Layout

- `custom_components/wattbill/`: the integration. Everything shipped to users lives here, including `translations/` (en and de, same keys) and `brand/`.
- `tests/`: backend tests, run inside a real Home Assistant test instance.
- `scripts/test_ha.py`: runs the tests against the minimum, stable or beta Home Assistant release.
- `GLOSSARY.md`: domain terms; use them in code, tests and docs. Decisions go in `docs/adr/`.

### Backend modules

- `config_flow.py`: the hub entry; `device_flow.py`: the Add Device subentry flow, one step per section of the Device's data (`status`, `mapping`, `job`, `consumption`, `price`). `device_config.py` reads that data into a `DeviceConfig`; `device_inputs.py` reads Device Inputs from HA states and the entity registry.
- `models.py`: `Run` and `LineItem`, free of HA types, with the JSON shape the Stores keep (`as_dict` / `from_dict`).
- `cost/`: the pure cost core (no HA imports): `consumption.py` (kWh between two moments), `electricity.py` (price segments and the Electricity Line Item), `running_time.py` (running time without pauses), `totals.py` (per-Device totals advanced by deltas).
- `tracker.py`: the Run engine for one Device (Status input → open, pause, end Run; reconciling after an outage; job changes; live refresh every minute, finalisation).
- `run_book.py`: all Runs in memory; every change goes through it so Stores, totals and listeners (`async_listen`) stay in step.
- `store.py`: every Store (registered in `SCHEMAS`) and the file folder (`files_path`). `WattBillStores` loads them together at setup (failing on missing or newer-major data), copies a Store to `<key>.bak` before a major migration and deletes everything when the hub entry is removed; `RunStore` writes Runs to `runs` and `live`. A new Store or file kind only registers there.
- `repairs.py`: the fix flow for missing data (restore guidance or a deliberate fresh start). `backup.py`: writes pending delayed saves before a backup.
- `entity.py`: `DeviceEntity`, the base of every per-Device entity (device info, re-read on any change to one of the Device's Runs). `sensor.py`: totals, Current and Last Run cost, Flagged Runs. `event.py`: the Run event (`started`, and `ended` only from finalisation).

## Setup

Python is managed by [uv](https://docs.astral.sh/uv/); the system Python is not used. Home Assistant needs Python 3.14 (pinned in `.python-version`).

```sh
uv sync
```

This creates `.venv` with Home Assistant, the test harness ([pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)), ruff and mypy, pinned in `uv.lock`.

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
- `tests/devices.py` sets up the hub (`add_hub`) and walks Add Device through the real flow (`add_device`, `walk_to_mapping`). Stored Runs are read from the `hass_storage` fixture (`wattbill.runs`, `wattbill.live`).

## Lint and type check

```sh
uv run ruff check .
uv run ruff format .        # CI runs: uv run ruff format --check .
uv run mypy
```

## CI

`.github/workflows/ci.yaml` runs on every push, pull request and nightly: hassfest, HACS validation, lint and type check, and the tests against the minimum, stable and beta HA releases.

## Conventions

- Everything in the repository is written in English.
- No user-facing text in Python: put it in `translations/en.json` and `translations/de.json` with identical keys (a test enforces this).
- Comments only for a non-obvious *why*.
