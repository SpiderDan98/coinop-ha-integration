"""Measured electricity: a Run's kWh from an energy meter or a power sensor."""

from typing import Any

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
