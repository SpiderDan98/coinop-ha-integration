"""Runs persist: ended Runs in the runs Store, open Runs in the live Store."""

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value


def live_runs(hass_storage: dict[str, Any]) -> list[dict[str, Any]]:
    if "coinop.live" not in hass_storage:
        return []
    runs: list[dict[str, Any]] = hass_storage["coinop.live"]["data"]["runs"]
    return runs


async def restart(hass: HomeAssistant, entry: ConfigEntry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_an_open_run_is_saved_about_a_minute_after_it_changed(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=60)

    await set_status(hass, "printing")
    await clock.advance(seconds=50)
    assert live_runs(hass_storage) == []
    await clock.advance(seconds=11)
    [run] = live_runs(hass_storage)
    assert run["ended"] is None


async def test_a_long_open_run_is_saved_again_every_minute_or_two(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=60)

    await set_status(hass, "printing")
    for _ in range(10):
        await clock.advance(minutes=1)

    [run] = live_runs(hass_storage)
    assert run["line_items"][0]["quantity"] >= 0.008


async def test_an_ended_run_moves_from_live_to_runs_at_once(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    assert len(live_runs(hass_storage)) == 1

    await set_status(hass, "finished")

    assert len(stored_runs(hass_storage)) == 1
    assert live_runs(hass_storage) == []


async def test_totals_are_rebuilt_from_stored_runs(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    for _ in range(2):
        await set_status(hass, "printing")
        await clock.advance(hours=1)
        await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await restart(hass, entry)

    assert value(hass, RUNS) == 3
    assert value(hass, TOTAL_COST) == pytest.approx(0.3)


async def test_an_open_run_survives_a_restart_and_keeps_accumulating(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await restart(hass, entry)
    await clock.advance(hours=1)
    assert value(hass, TOTAL_COST) == pytest.approx(0.2)
    await set_status(hass, "finished")

    assert value(hass, RUNS) == 1
    [run] = stored_runs(hass_storage)
    assert run["line_items"][0]["quantity"] == pytest.approx(0.2)


async def test_a_run_found_in_both_stores_is_taken_from_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    live_before_end = deepcopy(hass_storage["coinop.live"])
    await set_status(hass, "finished")
    assert await hass.config_entries.async_unload(entry.entry_id)

    # As if HA stopped after writing runs but before writing live.
    hass_storage["coinop.live"] = live_before_end
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await clock.advance(hours=1)

    assert value(hass, RUNS) == 1
    assert value(hass, TOTAL_COST) == pytest.approx(0.1)
