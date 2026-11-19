"""Per-Device sensors: totals for long-term statistics, current and last Run."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_runs import set_status, stored_runs, value

RUNNING_TIME = "sensor.kobra_running_time"
CURRENT = "sensor.kobra_current_run_cost"
LAST = "sensor.kobra_last_run_cost"


def state_of(hass: HomeAssistant, entity_id: str) -> State:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


@pytest.mark.parametrize(
    ("entity_id", "device_class", "unit"),
    [
        ("sensor.kobra_total_cost", "monetary", "EUR"),
        ("sensor.kobra_electricity_cost", "monetary", "EUR"),
        ("sensor.kobra_material_cost", "monetary", "EUR"),
        ("sensor.kobra_other_cost", "monetary", "EUR"),
        ("sensor.kobra_material_used", "weight", "g"),
        ("sensor.kobra_energy_in_runs", "energy", "kWh"),
    ],
)
async def test_totals_are_statistics_capable(
    hass: HomeAssistant, clock: Clock, entity_id: str, device_class: str, unit: str
) -> None:
    hass.config.currency = "EUR"
    entry = await add_hub(hass)
    await add_device(hass, entry)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0.0"
    assert {
        key: state.attributes.get(key)
        for key in ("device_class", "state_class", ATTR_UNIT_OF_MEASUREMENT)
    } == {
        "device_class": device_class,
        "state_class": "total",
        ATTR_UNIT_OF_MEASUREMENT: unit,
    }


async def test_totals_split_the_cost_by_kind_and_count_energy(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=0.5)

    await set_status(hass, "printing")
    await clock.advance(hours=2)

    assert value(hass, "sensor.kobra_energy_in_runs") == pytest.approx(0.2)
    assert value(hass, "sensor.kobra_electricity_cost") == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_total_cost") == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_material_cost") == 0
    assert value(hass, "sensor.kobra_other_cost") == 0
    assert value(hass, "sensor.kobra_material_used") == 0


async def enable(hass: HomeAssistant, entry: ConfigEntry, entity_id: str) -> None:
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_running_time_is_disabled_by_default(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    registered = er.async_get(hass).async_get(RUNNING_TIME)
    assert registered is not None
    assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(RUNNING_TIME) is None


async def test_running_time_counts_hours_of_every_run(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await enable(hass, entry, RUNNING_TIME)

    await set_status(hass, "printing")
    await clock.advance(minutes=90)
    await set_status(hass, "cancelled")
    await clock.advance(hours=1)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)

    state = hass.states.get(RUNNING_TIME)
    assert state is not None
    assert state.attributes["device_class"] == "duration"
    assert state.attributes["state_class"] == "total"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "h"
    assert float(state.state) == pytest.approx(2)


async def test_running_time_excludes_pauses(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await enable(hass, entry, RUNNING_TIME)
    await set_status(hass, "printing")
    await clock.advance(hours=2)
    await set_status(hass, "finished")
    assert await hass.config_entries.async_unload(entry.entry_id)

    [run] = stored_runs(hass_storage)
    paused = datetime.fromisoformat(run["started"]) + timedelta(minutes=10)
    resumed = paused + timedelta(minutes=45)
    run["pauses"] = [{"start": paused.isoformat(), "end": resumed.isoformat()}]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert value(hass, RUNNING_TIME) == pytest.approx(1.25)


async def test_current_run_cost_follows_the_open_run(
    hass: HomeAssistant, clock: Clock
) -> None:
    hass.config.currency = "EUR"
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    assert state_of(hass, CURRENT).state == STATE_UNKNOWN

    await set_status(hass, "printing")
    started = clock.now()
    await clock.advance(minutes=90)

    current = state_of(hass, CURRENT)
    assert float(current.state) == pytest.approx(0.15)
    assert current.attributes == {
        "name": None,
        "start": started,
        "running_hours": pytest.approx(1.5),
        "device_class": "monetary",
        ATTR_UNIT_OF_MEASUREMENT: "EUR",
        "friendly_name": "Kobra Current Run cost",
    }

    await set_status(hass, "finished")
    current = state_of(hass, CURRENT)
    assert current.state == STATE_UNKNOWN
    assert "start" not in current.attributes


async def test_last_run_cost_shows_the_last_ended_run(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    assert state_of(hass, LAST).state == STATE_UNKNOWN

    await set_status(hass, "printing")
    started = clock.now()
    await clock.advance(hours=2)
    await set_status(hass, "cancelled")
    ended = clock.now()
    await clock.advance(hours=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    last = state_of(hass, LAST)
    assert float(last.state) == pytest.approx(0.2)
    assert "state_class" not in last.attributes
    assert last.attributes["device_class"] == "monetary"
    assert {
        key: last.attributes[key]
        for key in (
            "name",
            "outcome",
            "start",
            "end",
            "part_count",
            "cost_per_part",
            "has_flags",
        )
    } == {
        "name": None,
        "outcome": "cancelled",
        "start": started,
        "end": ended,
        "part_count": 1,
        "cost_per_part": pytest.approx(0.2),
        "has_flags": False,
    }


async def restart_with(
    hass: HomeAssistant,
    entry: ConfigEntry,
    hass_storage: dict[str, Any],
    change: Callable[[list[dict[str, Any]]], object],
) -> None:
    """Restart after changing the stored Runs, as a correction would have."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    change(stored_runs(hass_storage))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def print_runs(hass: HomeAssistant, clock: Clock, hours: list[int]) -> None:
    for duration in hours:
        await set_status(hass, "printing")
        await clock.advance(hours=duration)
        await set_status(hass, "finished")
        await clock.advance(hours=1)


async def test_last_run_cost_follows_stored_changes(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await print_runs(hass, clock, [1, 3])

    def correct(runs: list[dict[str, Any]]) -> None:
        runs[-1] |= {"part_count": 4, "outcome": "failed", "flags": ["fault"]}

    await restart_with(hass, entry, hass_storage, correct)
    last = state_of(hass, LAST)
    assert float(last.state) == pytest.approx(0.3)
    assert last.attributes["part_count"] == 4
    assert last.attributes["cost_per_part"] == pytest.approx(0.075)
    assert last.attributes["outcome"] == "failed"
    assert last.attributes["has_flags"] is True

    await restart_with(hass, entry, hass_storage, lambda runs: runs.pop())
    assert float(state_of(hass, LAST).state) == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_total_cost") == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_runs") == 1
