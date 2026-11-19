"""Electricity price: a fixed value or a price entity, each kWh at the price that applied."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import ENERGY, PRICE, add_device, add_hub, configure, walk_to_price
from .test_device_flow import fields, suggested
from .test_lifecycle import at
from .test_measured import electricity, set_meter
from .test_persistence import live_runs, restart
from .test_runs import TOTAL_COST, set_status, stored_runs, value

PRICE_ENTITY = {"entity_id": PRICE}


async def set_price(
    hass: HomeAssistant, value: float | str, unit: str = "EUR/kWh"
) -> None:
    hass.states.async_set(PRICE, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def test_the_price_is_a_fixed_value_or_a_price_entity(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_to_price(hass, entry)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["fixed_price", "price_entity"]


async def test_a_price_entity_with_a_price_per_kwh_is_accepted(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, STATE_UNAVAILABLE, "ct/kWh")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})
    assert fields(result) == ["entity_id", "attribute"]

    result = await configure(hass, result, {"entity_id": PRICE})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"] == {
        "source": "entity",
        "entity_id": PRICE,
        "attribute": None,
        "unit": "ct/kWh",
        "factor": None,
    }


async def test_a_price_entity_without_a_recognisable_unit_needs_a_conversion_factor(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 25, "points")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(hass, result, {"entity_id": PRICE})
    assert result["errors"] == {"entity_id": "unknown_unit"}
    assert fields(result) == ["entity_id", "attribute", "factor"]
    result = await configure(hass, result, {"entity_id": PRICE, "factor": 0.01})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"]["factor"] == 0.01


async def test_a_price_in_another_currency_is_not_recognised(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 0.3, "USD/kWh")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(hass, result, {"entity_id": PRICE})

    assert result["errors"] == {"entity_id": "unknown_unit"}


async def test_a_price_attribute_asks_for_its_unit(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.tariff", "high", {"price": 31.2})
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(
        hass, result, {"entity_id": "sensor.tariff", "attribute": "price"}
    )
    assert result["step_id"] == "price_unit"
    result = await configure(hass, result, {"unit": "pts"})
    assert result["errors"] == {"unit": "unknown_unit"}
    assert fields(result) == ["unit", "factor"]
    result = await configure(hass, result, {"unit": "ct/kWh"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"]["unit"] == "ct/kWh"


async def test_the_first_devices_price_is_empty(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)

    result = await configure(hass, result, {"next_step_id": "fixed_price"})

    assert suggested(result, "price") is None


async def test_a_new_devices_fixed_price_is_pre_filled_from_the_last_device(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, price=0.27)
    await add_device(hass, entry, name="Voron", status="sensor.voron", price=0.31)
    result = await walk_to_price(hass, entry, status="sensor.prusa")

    result = await configure(hass, result, {"next_step_id": "fixed_price"})

    assert suggested(result, "price") == 0.31


async def test_a_new_devices_price_entity_is_pre_filled_from_the_last_device(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 0.3)
    entry = await add_hub(hass)
    await add_device(hass, entry, price={"entity_id": PRICE})
    result = await walk_to_price(hass, entry, status="sensor.voron")

    result = await configure(hass, result, {"next_step_id": "price_entity"})

    assert suggested(result, "entity_id") == PRICE


def segments(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (s["start"], s["end"], pytest.approx(s["kwh"]), pytest.approx(s["unit_price"]))
        for s in electricity(run)["segments"]
    ]


async def test_each_kwh_is_charged_at_the_price_that_applied_when_it_was_used(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price={"entity_id": PRICE})

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_price(hass, 0.40)
    await clock.advance(minutes=15)
    await set_price(hass, 0.10)
    await clock.advance(minutes=15)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    item = electricity(run)
    assert item["quantity"] == pytest.approx(1.0)
    assert item["amount"] == pytest.approx(0.1 + 0.1 + 0.025)
    assert segments(run) == [
        (at(), at(minutes=30), 0.5, 0.20),
        (at(minutes=30), at(minutes=45), 0.25, 0.40),
        (at(minutes=45), at(hours=1), 0.25, 0.10),
    ]
    assert run["flags"] == []


async def test_meter_readings_at_a_price_change_are_interpolated(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    await set_meter(hass, 10.0)
    entry = await add_hub(hass)
    await add_device(
        hass, entry, source="energy", meter={"entity_id": ENERGY}, price=PRICE_ENTITY
    )

    await set_status(hass, "printing")
    await clock.advance(minutes=45)
    await set_price(hass, 0.40)
    await clock.advance(minutes=15)
    await set_meter(hass, 11.0)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert segments(run) == [
        (at(), at(minutes=45), 0.75, 0.20),
        (at(minutes=45), at(hours=1), 0.25, 0.40),
    ]
    assert electricity(run)["amount"] == pytest.approx(0.15 + 0.1)


@pytest.mark.parametrize(
    ("price", "unit"),
    [(25, "ct/kWh"), (25, "c/kWh"), (25, "p/kWh"), (250, "EUR/MWh"), (0.25, "€/kWh")],
)
async def test_prices_in_sub_units_or_per_mwh_are_converted(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    price: float,
    unit: str,
) -> None:
    await set_price(hass, price, unit)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)

    await print_for_an_hour(hass, clock)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["unit_price"] == pytest.approx(0.25)
    assert electricity(run)["amount"] == pytest.approx(0.25)


async def test_a_conversion_factor_turns_the_price_into_one_per_kwh(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 2500, "points")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})
    result = await configure(hass, result, {"entity_id": PRICE})
    result = await configure(hass, result, {"entity_id": PRICE, "factor": 0.0001})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    await print_for_an_hour(hass, clock)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["unit_price"] == pytest.approx(0.25)


async def test_while_the_price_is_unavailable_the_last_valid_price_applies(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_price(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=15)
    await set_price(hass, 0.40)
    await clock.advance(minutes=15)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert segments(run) == [
        (at(), at(minutes=45), 0.75, 0.20),
        (at(minutes=45), at(hours=1), 0.25, 0.40),
    ]
    assert run["flags"] == ["price_gap"]


async def test_a_price_unavailable_at_start_is_the_last_known_one_before_it(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)
    await clock.advance(minutes=10)
    await set_price(hass, STATE_UNAVAILABLE)

    await print_for_an_hour(hass, clock)

    [run] = stored_runs(hass_storage)
    assert segments(run) == [(at(minutes=10), at(minutes=70), 1.0, 0.20)]
    assert run["flags"] == ["price_gap"]


async def test_without_a_price_before_the_runs_first_one_that_one_applies(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, STATE_UNAVAILABLE)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_price(hass, 0.30)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["amount"] == pytest.approx(0.30)
    assert run["flags"] == ["price_gap"]


async def test_without_any_price_electricity_costs_nothing_and_is_flagged(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, STATE_UNAVAILABLE)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)

    await print_for_an_hour(hass, clock)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(1.0)
    assert electricity(run)["amount"] == 0
    assert run["flags"] == ["price_gap"]


async def test_a_price_report_updates_the_provisional_cost_at_once(
    hass: HomeAssistant, clock: Clock
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)
    await set_status(hass, "printing")
    await clock.advance(minutes=30, seconds=30)
    assert value(hass, TOTAL_COST) == pytest.approx(0.20 * 30.5 / 60)

    await clock.advance(seconds=15)
    await set_price(hass, 0.40)

    assert value(hass, TOTAL_COST) == pytest.approx(0.20 * (30 * 60 + 45) / 3600)


async def test_price_segments_survive_a_restart_of_the_open_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)
    await set_status(hass, "printing")
    await clock.advance(minutes=20)
    await set_price(hass, 0.40)
    await clock.advance(minutes=10)
    [live] = live_runs(hass_storage)
    assert len(electricity(live)["segments"]) == 2

    await restart(hass, entry)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert segments(run) == [
        (at(), at(minutes=20), 1 / 3, 0.20),
        (at(minutes=20), at(hours=1), 2 / 3, 0.40),
    ]
    assert run["flags"] == []


async def print_for_an_hour(hass: HomeAssistant, clock: Clock) -> None:
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
