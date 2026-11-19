"""Real-world Run lifecycles: pauses, faults, outages and job changes."""

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import CLOCK_START, Clock
from .devices import MAPPING, add_device, add_hub
from .test_runs import set_status, stored_runs


WITH_FAULT = MAPPING | {"fault": ["error"]}


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
