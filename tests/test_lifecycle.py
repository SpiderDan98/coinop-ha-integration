"""Real-world Run lifecycles: pauses, faults, outages and job changes."""

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest

from .clock import CLOCK_START, Clock
from .devices import MAPPING, add_device, add_hub
from .test_runs import (
    NO_MATERIAL,
    RUNS,
    TOTAL_COST,
    set_status,
    stored_runs,
    value,
)
from .test_sensors import FLAGGED, RUNNING_TIME, enable

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
    await enable(hass, entry, RUNNING_TIME)

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
    assert value(hass, RUNNING_TIME) == pytest.approx(2)


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
    assert run["flags"] == ["fault", *NO_MATERIAL]
    assert run["pauses"] == [{"start": at(hours=1), "end": at(hours=2)}]
    assert kwh(run) == pytest.approx(0.2)
    assert value(hass, FLAGGED) == 1


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
    assert run["flags"] == ["fault", *NO_MATERIAL]
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


JOB = "sensor.kobra_job"


async def start_job(hass: HomeAssistant, job: str) -> None:
    hass.states.async_set(JOB, job)
    await set_status(hass, "printing")


async def test_a_run_is_named_after_its_job(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB)

    await start_job(hass, "benchy.gcode")
    await clock.advance(minutes=30)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["name"] == "benchy.gcode"


async def test_the_job_name_can_come_from_an_attribute_of_the_print_event(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass,
        entry,
        status=PRINT_EVENT,
        mapping=EVENTS,
        job=PRINT_EVENT,
        job_attribute="filename",
    )

    await fire(hass, "started", at(), filename="benchy.gcode")
    await clock.advance(minutes=30)
    await fire(hass, "finished", at(minutes=30), filename="benchy.gcode")

    [run] = stored_runs(hass_storage)
    assert run["name"] == "benchy.gcode"


async def test_a_print_resumed_with_the_same_job_continues_its_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB, running_power=100)

    await start_job(hass, "benchy.gcode")
    await clock.advance(hours=1)
    hass.states.async_set(JOB, STATE_UNAVAILABLE)
    await set_status(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await start_job(hass, "benchy.gcode")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["ended"] == at(hours=3)
    assert run["outcome"] == "completed"
    assert kwh(run) == pytest.approx(0.3)


async def test_a_print_with_another_job_closes_the_old_run_and_opens_a_new_one(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB, running_power=100)

    await start_job(hass, "benchy.gcode")
    await clock.advance(hours=1)
    await set_status(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await start_job(hass, "cube.gcode")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    benchy, cube = stored_runs(hass_storage)
    assert benchy | {"quantity": kwh(benchy)} == benchy | {
        "name": "benchy.gcode",
        "started": at(),
        "ended": at(hours=1),
        "outcome": "unknown",
        "end_reconstructed": True,
        "quantity": pytest.approx(0.1),
    }
    assert cube | {"quantity": kwh(cube)} == cube | {
        "name": "cube.gcode",
        "started": at(hours=2),
        "ended": at(hours=3),
        "outcome": "completed",
        "quantity": pytest.approx(0.1),
    }
    assert value(hass, RUNS) == 2


async def test_a_job_change_while_wattbill_was_stopped_closes_at_the_last_sighting(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB, running_power=100)
    await start_job(hass, "benchy.gcode")
    await clock.advance(hours=1)

    await stop_wattbill(hass, entry)
    await set_status(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await start_job(hass, "cube.gcode")
    await clock.advance(hours=1)
    await start_wattbill(hass, entry)

    [benchy] = stored_runs(hass_storage)
    assert benchy["ended"] == at(hours=1)
    assert benchy["outcome"] == "unknown"
    assert kwh(benchy) == pytest.approx(0.1)
    assert value(hass, RUNS) == 2


async def test_a_paused_print_with_another_job_closes_including_its_pause(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB, running_power=100, paused_power=10)

    await start_job(hass, "benchy.gcode")
    await clock.advance(hours=1)
    await set_status(hass, "paused")
    await clock.advance(hours=1)
    await set_status(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await start_job(hass, "cube.gcode")

    [benchy] = stored_runs(hass_storage)
    assert benchy["ended"] == at(hours=2)
    assert benchy["pauses"] == [{"start": at(hours=1), "end": at(hours=2)}]
    assert kwh(benchy) == pytest.approx(0.11)


async def test_runs_have_no_minimum_duration(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    await set_status(hass, "printing")
    await clock.advance(seconds=1)
    await set_status(hass, "cancelled")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(seconds=1)


async def test_runs_have_no_timeout(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100)

    await set_status(hass, "printing")
    for _ in range(3 * 24):
        await clock.advance(hours=1)
    assert stored_runs(hass_storage) == []
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(days=3)
    assert kwh(run) == pytest.approx(7.2)


async def test_every_run_books_its_full_consumption_whatever_its_outcome(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, mapping=WITH_FAULT, running_power=100, price=1)

    for ending in ("finished", "cancelled", "idle"):
        await set_status(hass, "printing")
        await clock.advance(hours=1)
        await set_status(hass, ending)
    await set_status(hass, "printing")
    await set_status(hass, "error")
    await clock.advance(hours=1)
    await set_status(hass, "cancelled")

    runs = stored_runs(hass_storage)
    assert [run["outcome"] for run in runs] == [
        "completed",
        "cancelled",
        "unknown",
        "failed",
    ]
    assert [kwh(run) for run in runs] == pytest.approx([0.1] * 4)
    assert value(hass, TOTAL_COST) == pytest.approx(0.4)
