"""Real-world Run lifecycles: pauses, faults, outages and job changes."""

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest

from .clock import CLOCK_START, Clock
from .devices import MAPPING, add_device, add_hub
from .test_runs import RUNS, set_status, stored_runs, value

WITH_FAULT = MAPPING | {"fault": ["error"]}
PRINT_EVENT = "event.kobra_print"
EVENTS = {
    "running": ["started", "resumed"],
    "paused": ["paused"],
    "finished": ["finished"],
    "cancelled": ["stopped"],
}


def at(**offset: float) -> str:
    return (CLOCK_START + timedelta(**offset)).isoformat()


def kwh(run: dict[str, Any]) -> float:
    quantity: float = run["line_items"][0]["quantity"]
    return quantity


async def test_pauses_are_recorded_and_estimated_at_paused_power(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=120, paused_power=20)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "paused")
    await clock.advance(hours=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [{"start": at(hours=1), "end": at(hours=2)}]
    assert kwh(run) == pytest.approx(0.26)


async def test_an_empty_paused_power_estimates_pauses_at_running_power(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=120)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "paused")
    await clock.advance(hours=1)
    await set_status(hass, "cancelled")

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [{"start": at(hours=1), "end": at(hours=2)}]
    assert kwh(run) == pytest.approx(0.24)


async def test_a_fault_flags_the_run_and_pauses_it(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, mapping=WITH_FAULT, running_power=100, paused_power=0)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "error")
    await clock.advance(hours=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == ["fault"]
    assert run["pauses"] == [{"start": at(hours=1), "end": at(hours=2)}]
    assert kwh(run) == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("ending", "outcome"),
    [("cancelled", "failed"), ("finished", "completed"), ("idle", "unknown")],
)
async def test_the_outcome_after_a_fault(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    ending: str,
    outcome: str,
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, mapping=WITH_FAULT)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_status(hass, "error")
    await clock.advance(minutes=5)
    await set_status(hass, ending)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == outcome
    assert run["flags"] == ["fault"]
    assert run["pauses"] == [{"start": at(minutes=30), "end": at(minutes=35)}]


async def fire(
    hass: HomeAssistant, event_type: str, fired: str, **attributes: Any
) -> None:
    """Set the print event entity as HA's event platform does: state = when it fired."""
    hass.states.async_set(PRINT_EVENT, fired, {"event_type": event_type} | attributes)
    await hass.async_block_till_done()


async def stop_wattbill(hass: HomeAssistant, entry: ConfigEntry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)


async def start_wattbill(hass: HomeAssistant, entry: ConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("lost", [STATE_UNAVAILABLE, STATE_UNKNOWN])
async def test_a_lost_status_never_ends_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], lost: str
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, lost)
    await clock.advance(hours=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    assert value(hass, RUNS) == 1
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(hours=3)
    assert run["end_reconstructed"] is False
    assert kwh(run) == pytest.approx(0.3)


async def test_a_run_that_ended_while_the_status_was_lost_ends_when_it_returns(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["ended"] == at(hours=2)
    assert run["end_reconstructed"] is True
    assert kwh(run) == pytest.approx(0.2)


async def test_a_run_that_ended_while_wattbill_was_stopped_takes_the_end_state_time(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await stop_wattbill(hass, entry)
    await clock.advance(hours=1)
    await set_status(hass, "cancelled")
    await clock.advance(hours=1)
    await start_wattbill(hass, entry)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "cancelled"
    assert run["ended"] == at(hours=2)
    assert run["end_reconstructed"] is True
    assert kwh(run) == pytest.approx(0.2)


async def test_a_terminal_event_missed_while_stopped_ends_the_run_when_it_fired(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, status=PRINT_EVENT, mapping=EVENTS, running_power=100)
    await fire(hass, "started", at())
    await clock.advance(hours=1)

    await stop_wattbill(hass, entry)
    await clock.advance(hours=1)
    await fire(hass, "finished", at(hours=1, minutes=30))
    await clock.advance(hours=1)
    await start_wattbill(hass, entry)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["ended"] == at(hours=1, minutes=30)
    assert run["end_reconstructed"] is True
    assert kwh(run) == pytest.approx(0.15)


async def test_an_open_run_whose_print_goes_on_continues_after_a_restart(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, status=PRINT_EVENT, mapping=EVENTS, running_power=100)
    await fire(hass, "started", at())
    await clock.advance(hours=1)

    await stop_wattbill(hass, entry)
    await clock.advance(hours=1)
    await start_wattbill(hass, entry)
    await clock.advance(hours=1)
    await fire(hass, "finished", at(hours=3))

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["ended"] == at(hours=3)
    assert run["end_reconstructed"] is False
