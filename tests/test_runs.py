"""A print becomes a Run: opened and closed by the Status input, costed by estimate."""

from typing import Any

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import STATUS, add_device, add_hub

TOTAL_COST = "sensor.kobra_total_cost"
RUNS = "sensor.kobra_runs"


def value(hass: HomeAssistant, entity_id: str) -> float:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return float(state.state)


async def set_status(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(STATUS, status)
    await hass.async_block_till_done()


def stored_runs(hass_storage: dict[str, Any]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = hass_storage["wattbill.runs"]["data"]["runs"]
    return runs


async def test_devices_start_without_runs(hass: HomeAssistant, clock: Clock) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    assert value(hass, TOTAL_COST) == 0
    assert value(hass, RUNS) == 0
    cost = hass.states.get(TOTAL_COST)
    assert cost is not None
    assert cost.attributes["device_class"] == "monetary"
    assert cost.attributes["state_class"] == "total"
    assert cost.attributes[ATTR_UNIT_OF_MEASUREMENT] == hass.config.currency
    runs = hass.states.get(RUNS)
    assert runs is not None
    assert runs.attributes["state_class"] == "total"


async def test_a_print_is_one_run_with_a_frozen_estimated_line_item(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await set_status(hass, "idle")
    await add_device(hass, entry, running_power=120, price=0.30)

    await set_status(hass, "printing")
    assert value(hass, RUNS) == 1
    await clock.advance(hours=1)
    assert value(hass, TOTAL_COST) == pytest.approx(0.036)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await set_status(hass, "idle")
    await clock.advance(hours=3)

    assert value(hass, RUNS) == 1
    assert value(hass, TOTAL_COST) == pytest.approx(0.072)
    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    [item] = run["line_items"]
    assert item | {"quantity": pytest.approx(0.24), "amount": pytest.approx(0.072)} == {
        **item,
        "kind": "electricity",
        "label": None,
        "unit": "kWh",
        "unit_price": 0.30,
        "method": "estimated",
    }


@pytest.mark.parametrize(
    ("ending", "outcome"),
    [("finished", "completed"), ("cancelled", "cancelled"), ("idle", "unknown")],
)
async def test_the_ending_value_sets_the_outcome(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    ending: str,
    outcome: str,
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_status(hass, ending)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == outcome


async def test_values_mapped_to_nothing_are_ignored(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    await set_status(hass, "heating")
    assert value(hass, RUNS) == 0
    await set_status(hass, "printing")
    await set_status(hass, "heating")
    await clock.advance(hours=1)

    assert value(hass, RUNS) == 1
    assert "wattbill.runs" not in hass_storage


async def test_each_print_is_its_own_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)

    for _ in range(3):
        await set_status(hass, "printing")
        await clock.advance(hours=1)
        await set_status(hass, "finished")
        await clock.advance(hours=1)

    assert value(hass, RUNS) == 3
    assert value(hass, TOTAL_COST) == pytest.approx(0.3)
    assert len(stored_runs(hass_storage)) == 3


async def test_devices_keep_their_own_runs(hass: HomeAssistant, clock: Clock) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await add_device(hass, entry, name="Voron", status="sensor.voron_status")

    await set_status(hass, "printing")
    await clock.advance(hours=1)

    assert value(hass, RUNS) == 1
    assert value(hass, "sensor.voron_runs") == 0
    assert value(hass, "sensor.voron_total_cost") == 0
