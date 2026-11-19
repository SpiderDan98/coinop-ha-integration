"""Measured electricity: a Run's kWh from an energy meter or a power sensor."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import ENERGY, POWER, add_device, add_hub
from .test_persistence import live_runs
from .test_runs import set_status, stored_runs


async def set_meter(
    hass: HomeAssistant, value: float | str, *, entity: str = ENERGY, unit: str = "kWh"
) -> None:
    hass.states.async_set(entity, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def add_metered_device(
    hass: HomeAssistant, source: str = "energy", **meter: Any
) -> None:
    entity = ENERGY if source == "energy" else POWER
    await add_device(
        hass, await add_hub(hass), source=source, meter={"entity_id": entity} | meter
    )


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
    assert run["flags"] == []


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
    assert "wattbill.runs" not in hass_storage
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
    assert run["flags"] == []


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
    assert run["flags"] == ["consumption_gap"]


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
    assert run["flags"] == ["consumption_gap"]


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
    assert run["flags"] == ["meter_reset"]


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
    assert run["flags"] == ["meter_reset"]


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
    assert run["flags"] == ["consumption_gap"]
