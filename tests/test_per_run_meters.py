"""Per-Run meters without a value as their Run opens: a counter that starts the
Run at 0 missed nothing."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_basic_device, add_hub
from .test_ev_chargers import CHARGER_MAPPING, CHARGER_STATUS, set_charger
from .test_measured import electricity, set_meter
from .test_quick_start import quick_start
from .test_robotic_mowers import STATION_ENERGY, add_mower, set_mower
from .test_runs import stored_runs
from .test_water import water
from .washers import Appliance, add_miele

COUNTERS = {
    "current_energy_consumption": "kWh",
    "current_water_consumption": "L",
}
CHARGER_METER = "sensor.wallbox_energy"
CHARGER_POWER = "sensor.wallbox_power"


async def report(
    hass: HomeAssistant,
    appliance: Appliance,
    status: str,
    kwh: float | str,
    litres: float | str,
    *,
    status_first: bool = True,
) -> None:
    """One update of a Miele appliance: its Status and its counters, written one
    after the other."""
    if status_first:
        hass.states.async_set(appliance["state_status"], status)
    for (key, unit), value in zip(COUNTERS.items(), (kwh, litres), strict=True):
        hass.states.async_set(appliance[key], str(value), {"unit_of_measurement": unit})
    if not status_first:
        hass.states.async_set(appliance["state_status"], status)
    await hass.async_block_till_done()


async def add_miele_washer(hass: HomeAssistant, **written: Any) -> Appliance:
    """A Miele washing machine, off, its counters without a value, added by Quick
    Start on those counters."""
    washer = add_miele(hass)
    await report(hass, washer, "off", STATE_UNKNOWN, STATE_UNKNOWN, **written)
    hass.states.async_set(washer["state_program_id"], "cottons")
    await quick_start(
        hass, await add_hub(hass), washer.device.id, price=0.3, water_price=4.0
    )
    return washer


@pytest.mark.parametrize("status_first", [True, False])
@pytest.mark.parametrize(
    ("counters_report_the_end", "off_after_minutes"),
    [(True, 2), (False, 2), (False, 10)],
    ids=["after the final report", "inside the wait", "after the wait"],
)
async def test_a_miele_cycle_is_counted_from_its_counters_without_a_flag(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    status_first: bool,
    counters_report_the_end: bool,
    off_after_minutes: int,
) -> None:
    """Miele's counters have no value between cycles, start a cycle at 0, keep its
    total while the program has ended and lose it once the appliance is off."""
    washer = await add_miele_washer(hass, status_first=status_first)
    await clock.advance(hours=1)

    for kwh, litres in ((0.9, 48.0), (0.7, 40.0)):
        await report(hass, washer, "in_use", 0, 0, status_first=status_first)
        await clock.advance(minutes=45)
        await report(
            hass, washer, "in_use", kwh / 2, litres / 2, status_first=status_first
        )
        await clock.advance(minutes=45)
        await report(hass, washer, "in_use", kwh, litres, status_first=status_first)
        await clock.advance(minutes=1)
        if counters_report_the_end:
            await report(
                hass, washer, "program_ended", kwh, litres, status_first=status_first
            )
        else:
            hass.states.async_set(washer["state_status"], "program_ended")
            await hass.async_block_till_done()
        await clock.advance(minutes=off_after_minutes)
        await report(
            hass,
            washer,
            "off",
            STATE_UNKNOWN,
            STATE_UNKNOWN,
            status_first=status_first,
        )
        await clock.advance(hours=5)

    first, second = stored_runs(hass_storage)
    assert [
        (electricity(run)["method"], electricity(run)["quantity"])
        for run in (first, second)
    ] == [("measured", pytest.approx(0.9)), ("measured", pytest.approx(0.7))]
    assert [
        (water(run)["method"], water(run)["quantity"]) for run in (first, second)
    ] == [("measured", pytest.approx(48)), ("measured", pytest.approx(40))]
    assert first["flags"] == second["flags"] == []
    assert first["outcome"] == second["outcome"] == "completed"


async def test_without_per_run_meters_a_meter_back_at_zero_lost_what_it_counted(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await add_mower(hass)
    await set_meter(hass, STATE_UNAVAILABLE, entity=STATION_ENERGY)
    await set_mower(hass, "mowing")
    await clock.advance(minutes=30)
    await set_meter(hass, 0, entity=STATION_ENERGY)
    await clock.advance(minutes=30)
    await set_meter(hass, 0.2, entity=STATION_ENERGY)
    await set_mower(hass, "parked")
    await set_meter(hass, 0.2, entity=STATION_ENERGY)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.2)
    assert run["flags"] == ["consumption_gap"]


async def add_charger(hass: HomeAssistant, source: str, entity_id: str) -> None:
    """An EV charger without a car on an input that has no value yet."""
    hass.config.currency = "EUR"
    await set_charger(hass, "disconnected")
    await add_basic_device(
        hass,
        await add_hub(hass),
        device_type="ev_charger",
        name="Wallbox",
        status=CHARGER_STATUS,
        mapping=CHARGER_MAPPING,
        source=source,
        meter={"entity_id": entity_id},
    )


async def test_a_lifetime_meters_first_value_is_a_gap_and_is_not_counted(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """An EV charger has per-Run meters, yet may be on one that counts for life."""
    await set_meter(hass, STATE_UNAVAILABLE, entity=CHARGER_METER)
    await add_charger(hass, "energy", CHARGER_METER)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_meter(hass, 12345.6, entity=CHARGER_METER)
    await clock.advance(hours=1)
    await set_meter(hass, 12350.6, entity=CHARGER_METER)
    await set_charger(hass, "disconnected")
    await set_meter(hass, 12350.6, entity=CHARGER_METER)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(5.0)
    assert run["flags"] == ["consumption_gap"]


async def test_a_per_run_meter_without_a_value_for_the_whole_run_is_a_gap(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, STATE_UNAVAILABLE, entity=CHARGER_METER)
    await add_charger(hass, "energy", CHARGER_METER)
    await set_charger(hass, "charging")
    await clock.advance(hours=2)
    await set_charger(hass, "disconnected")
    await clock.advance(minutes=1)
    await set_meter(hass, 0, entity=CHARGER_METER)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == 0
    assert run["flags"] == ["consumption_gap"]


async def test_a_power_sensor_without_a_value_at_the_start_is_a_gap_even_at_zero(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """Only a meter counts from 0: a power of 0 says nothing of the time before it."""
    await set_meter(hass, STATE_UNAVAILABLE, entity=CHARGER_POWER, unit="W")
    await add_charger(hass, "power", CHARGER_POWER)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_meter(hass, 0, entity=CHARGER_POWER, unit="W")
    await clock.advance(minutes=30)
    await set_meter(hass, 7000, entity=CHARGER_POWER, unit="W")
    await clock.advance(minutes=30)
    await set_charger(hass, "disconnected")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["consumption_gap"]


async def test_a_counter_losing_its_value_during_the_cycle_is_a_gap(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    washer = await add_miele_washer(hass)
    await clock.advance(hours=1)
    await report(hass, washer, "in_use", 0, 0)
    await clock.advance(minutes=30)
    await report(hass, washer, "in_use", 0.3, 16)
    await clock.advance(minutes=30)
    await report(hass, washer, "in_use", STATE_UNKNOWN, STATE_UNKNOWN)
    await clock.advance(minutes=30)
    await report(hass, washer, "in_use", 0.9, 48)
    await report(hass, washer, "program_ended", 0.9, 48)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(0.9)
    assert water(run)["quantity"] == pytest.approx(48)
    assert run["flags"] == ["consumption_gap"]
