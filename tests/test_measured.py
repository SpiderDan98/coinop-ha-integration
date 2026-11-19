"""Measured electricity: a Run's kWh from an energy meter or a power sensor."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    ENERGY,
    POWER,
    add_device,
    add_hub,
    configure,
    walk_to_consumption,
)
from .test_lifecycle import start_wattbill, stop_wattbill
from .test_persistence import live_runs, restart
from .test_runs import NO_MATERIAL, set_status, stored_runs


async def set_meter(
    hass: HomeAssistant, value: float | str, *, entity: str = ENERGY, unit: str = "kWh"
) -> None:
    hass.states.async_set(entity, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def add_metered_device(
    hass: HomeAssistant, source: str = "energy", **meter: Any
) -> ConfigEntry:
    entity = ENERGY if source == "energy" else POWER
    entry = await add_hub(hass)
    await add_device(hass, entry, source=source, meter={"entity_id": entity} | meter)
    return entry


def electricity(run: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = next(
        i for i in run["line_items"] if i["kind"] == "electricity"
    )
    return item


async def test_meter_readings_are_interpolated_at_run_start_and_end(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)

    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.2)
    await clock.advance(minutes=38)
    await set_meter(hass, 10.5)
    await clock.advance(minutes=2)
    await set_status(hass, "finished")
    await clock.advance(minutes=2)
    await set_meter(hass, 10.54)

    [run] = stored_runs(hass_storage)
    item = electricity(run)
    assert item["method"] == "measured"
    assert item["quantity"] == pytest.approx(10.52 - 10.1)
    assert item["amount"] == pytest.approx((10.52 - 10.1) * 0.30)
    assert run["flags"] == NO_MATERIAL


async def test_without_a_final_report_the_last_reading_applies_after_five_minutes(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, 10.3)
    await clock.advance(minutes=10)

    await set_status(hass, "finished")
    await clock.advance(minutes=4, seconds=59)
    [waiting] = live_runs(hass_storage)
    assert waiting["ended"] is not None
    assert waiting["outcome"] == "completed"
    assert waiting["finalised"] is False
    assert stored_runs(hass_storage) == []
    await clock.advance(seconds=1)

    [run] = stored_runs(hass_storage)
    assert run["finalised"] is True
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert live_runs(hass_storage) == []


async def test_reports_after_finalisation_change_nothing(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)
    await set_meter(hass, 10.4)
    await clock.advance(minutes=10)
    await set_meter(hass, 11.0)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.4 * 30 / 31)


async def set_power(hass: HomeAssistant, watts: float | str) -> None:
    await set_meter(hass, watts, entity=POWER, unit="W")


async def test_power_is_integrated_with_the_left_rule(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_power(hass, 100)
    await add_metered_device(hass, "power")

    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=20)
    await set_power(hass, 200)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await set_power(hass, 5)

    [run] = stored_runs(hass_storage)
    item = electricity(run)
    assert item["method"] == "measured"
    assert item["quantity"] == pytest.approx(100 * 20 / 60_000 + 200 * 30 / 60_000)
    assert run["flags"] == NO_MATERIAL


async def test_energy_across_a_meter_gap_is_spread_evenly_and_flagged(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)
    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=20)
    await set_status(hass, "finished")
    await clock.advance(minutes=4)
    await set_meter(hass, 10.44)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert run["flags"] == ["consumption_gap", *NO_MATERIAL]


async def test_a_meter_unavailable_at_run_start_is_a_gap(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, STATE_UNAVAILABLE)
    await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.0)
    await clock.advance(minutes=10)
    await set_meter(hass, 10.2)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.2)
    assert run["flags"] == ["consumption_gap", *NO_MATERIAL]


async def test_a_falling_reading_is_a_meter_reset_counting_from_zero(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 5.0)
    await add_metered_device(hass)
    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, 5.2)
    await clock.advance(minutes=10)
    await set_meter(hass, 0.1)
    await clock.advance(minutes=10)
    await set_meter(hass, 0.3)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.1 + 0.1 + 0.2)
    assert run["flags"] == ["meter_reset", *NO_MATERIAL]


async def test_a_small_dip_counts_nothing_and_is_flagged(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.2)
    await clock.advance(minutes=10)
    await set_meter(hass, 10.1)
    await clock.advance(minutes=10)
    await set_meter(hass, 10.3)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.2 + 0.2)
    assert run["flags"] == ["meter_reset", *NO_MATERIAL]


@pytest.mark.parametrize(
    ("running_power", "gap_watts"), [(None, 100), (120, 120)], ids=["last", "average"]
)
async def test_a_power_gap_holds_the_average_or_else_the_last_power(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    running_power: float | None,
    gap_watts: float,
) -> None:
    await set_power(hass, 100)
    gaps = {} if running_power is None else {"running_power": running_power}
    await add_metered_device(hass, "power", **gaps)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_power(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=20)
    await set_power(hass, 150)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(
        (100 * 10 + gap_watts * 20 + 150 * 30) / 60_000
    )
    assert run["flags"] == ["consumption_gap", *NO_MATERIAL]


async def print_half_an_hour(
    hass: HomeAssistant, clock: Clock, start: float, end: float, **meter: Any
) -> None:
    await set_meter(hass, start, **meter)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, end, **meter)
    await set_status(hass, "finished")


async def test_an_energy_meter_in_wh_is_read_in_kwh(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10_000, unit="Wh")
    await add_metered_device(hass)

    await print_half_an_hour(hass, clock, 10_000, 10_300, unit="Wh")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.3)


async def test_a_power_sensor_in_kw_is_read_in_watts(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 0.1, entity=POWER, unit="kW")
    await add_metered_device(hass, "power")

    await print_half_an_hour(hass, clock, 0.1, 0.1, entity=POWER, unit="kW")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.05)


async def finish_add_device(hass: HomeAssistant, result: Any) -> None:
    assert result["step_id"] == "price", result.get("errors")
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.30})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_a_conversion_factor_turns_readings_into_kwh(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10_000, unit="pulses")
    result = await walk_to_consumption(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": ENERGY})
    result = await configure(hass, result, {"entity_id": ENERGY, "factor": 0.001})
    await finish_add_device(hass, result)

    await print_half_an_hour(hass, clock, 10_000, 10_300, unit="pulses")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.3)


async def test_a_meter_attribute_is_read_in_the_unit_given_for_it(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    plug = "switch.kobra_plug"
    hass.states.async_set(plug, "on", {"energy_wh": 10_000})
    result = await walk_to_consumption(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(
        hass, result, {"entity_id": plug, "attribute": "energy_wh"}
    )
    result = await configure(hass, result, {"unit": "Wh"})
    await finish_add_device(hass, result)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    hass.states.async_set(plug, "on", {"energy_wh": 10_300})
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.3)


async def test_meter_readings_survive_a_restart(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.2)
    await clock.advance(minutes=10)

    await restart(hass, entry)
    await clock.advance(minutes=10)
    await set_status(hass, "finished")
    await clock.advance(minutes=2)
    await set_meter(hass, 10.5)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(10.2 + 0.3 * 20 / 22 - 10.1)
    assert run["flags"] == NO_MATERIAL


async def test_a_restart_during_the_final_wait_keeps_waiting(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)

    await restart(hass, entry)
    assert stored_runs(hass_storage) == []
    await clock.advance(minutes=1)
    await set_meter(hass, 10.4)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert electricity(run)["quantity"] == pytest.approx(0.4 * 30 / 32)


async def test_an_outage_during_a_run_is_a_consumption_gap(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)

    await stop_wattbill(hass, entry)
    await clock.advance(minutes=30)
    await start_wattbill(hass, entry)
    await set_meter(hass, 10.4)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.4)
    assert run["flags"] == ["consumption_gap", *NO_MATERIAL]


async def test_an_outage_holds_the_average_power(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_power(hass, 100)
    entry = await add_metered_device(hass, "power", running_power=200)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)

    await stop_wattbill(hass, entry)
    await clock.advance(minutes=30)
    await start_wattbill(hass, entry)
    await set_power(hass, 150)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx((100 + 200 + 150) / 2 / 1000)
    assert run["flags"] == ["consumption_gap", *NO_MATERIAL]
