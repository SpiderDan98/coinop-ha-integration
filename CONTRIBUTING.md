# Contributing

## Layout

- `custom_components/wattbill/`: the integration. Everything shipped to users lives here, including `translations/` (en and de, same keys) and `brand/`.
- `tests/`: backend tests, run inside a real Home Assistant test instance.
- `scripts/test_ha.py`: runs the tests against the minimum, stable or beta Home Assistant release.
- `GLOSSARY.md`: domain terms; use them in code, tests and docs. Decisions go in `docs/adr/`.

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
