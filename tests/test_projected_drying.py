"""Projected Total: a multi-material unit's drying adds its power while it overlaps
the Run's time left."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import ENERGY, add_device, add_hub
from .test_lifecycle import start_coinop, stop_coinop
from .test_measured import set_meter
from .test_projected_total import (
    REMAINING,
    add_metered_printer,
    projected,
    set_remaining,
)
from .test_runs import set_status
from .websocket import PanelClient

ACE = "switch.ace_drying"
ACE_LEFT = "sensor.ace_drying_remaining"
SECOND = "binary_sensor.second_ace_drying"
SECOND_LEFT = "sensor.second_ace_drying_remaining"
SLOTS = ["sensor.ace_slot_1"]


async def add_drying_printer(
    hass: HomeAssistant,
    units: list[tuple[str, str | None]] | None = None,
    **options: Any,
) -> ConfigEntry:
    """A metered printer at 0.30 per kWh with one ACE, unless `units` says otherwise."""
    return await add_metered_printer(
        hass, slots=SLOTS, drying=units or [(ACE, ACE_LEFT)], **options
    )


async def dry(
    hass: HomeAssistant,
    minutes: float | None = None,
    *,
    unit: str = ACE,
    left: str = ACE_LEFT,
) -> None:
    """The unit dries, with `minutes` of drying left if given."""
    hass.states.async_set(unit, "on")
    if minutes is not None:
        hass.states.async_set(left, str(minutes), {"unit_of_measurement": "min"})
    await hass.async_block_till_done()


async def stop_drying(hass: HomeAssistant, *, unit: str = ACE) -> None:
    hass.states.async_set(unit, "off")
    await hass.async_block_till_done()


async def draw(hass: HomeAssistant, clock: Clock, watts: float, minutes: int) -> None:
    """The meter counts `watts` for `minutes`, reporting every 10 minutes."""
    for _ in range(0, minutes, 10):
        await clock.advance(minutes=10)
        state = hass.states.get(ENERGY)
        assert state is not None
        await set_meter(hass, float(state.state) + watts / 6000)


async def test_a_dryer_that_stops_before_the_print_adds_its_power_while_it_dries(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass, drying_power=200)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass, 30)
    await set_remaining(hass, 120)

    # 0.03 so far; 2 h at 150 W and half an hour at 200 W, at 0.30 per kWh.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09 + 0.03)


async def test_a_dryer_that_outlasts_the_print_adds_its_power_only_up_to_its_end(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass, drying_power=200)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass, 300)
    await set_remaining(hass, 120)

    # 2 h at 150 W and, of its 5 h, the 2 h left of the Run at 200 W.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09 + 0.12)

    await stop_drying(hass)
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)


async def test_a_unit_drying_without_a_drying_left_dries_for_the_whole_time_left(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass, units=[(ACE, None)], drying_power=200)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    await set_remaining(hass, 120)

    # 2 h at 150 W and 2 h at 200 W.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09 + 0.12)


@pytest.mark.parametrize("reading", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_a_unit_whose_drying_left_reads_nothing_projects_no_drying(
    hass: HomeAssistant, clock: Clock, reading: str
) -> None:
    await add_drying_printer(hass, drying_power=200)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    hass.states.async_set(ACE_LEFT, reading)
    await set_remaining(hass, 120)

    # 2 h at 150 W, and no guess at how long the unit still dries.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)


@pytest.mark.parametrize(
    ("value", "unit"), [("30", None), ("0.5", "h"), ("1800", "s"), ("1800000", "ms")]
)
async def test_a_drying_left_is_read_in_its_unit_and_without_one_in_minutes(
    hass: HomeAssistant, clock: Clock, value: str, unit: str | None
) -> None:
    await add_drying_printer(hass, drying_power=200)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    hass.states.async_set(
        ACE_LEFT, value, {"unit_of_measurement": unit} if unit else {}
    )
    await set_remaining(hass, 120)

    # Half an hour at 200 W, as Anycubic Cloud's unitless minutes too.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09 + 0.03)


async def test_the_base_power_leaves_out_the_drying(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass, drying_power=150)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    await draw(hass, clock, 300, 20)
    await dry(hass, 40)
    await set_remaining(hass, 120)

    # 0.06 so far; 2 h at the 150 W before the drying, not the last half hour's
    # 250 W, and 40 minutes at 150 W.
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.09 + 0.03)


async def test_after_a_restart_the_time_before_it_counts_as_neither_side(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_drying_printer(hass, drying_power=150)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    await draw(hass, clock, 300, 20)
    await stop_drying(hass)
    await draw(hass, clock, 200, 10)

    await stop_coinop(hass, entry)
    await start_coinop(hass, entry)
    await set_remaining(hass, 120)

    # 0.07 so far; whether it dried before its last change is unknown after the
    # restart, so 2 h at the 200 W since, not the last half hour's 267 W.
    assert float(projected(hass).state) == pytest.approx(0.07 + 0.12)


async def test_a_run_that_dried_all_along_takes_the_drying_power_off_its_base(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass, drying_power=150)
    await dry(hass)
    await clock.advance(minutes=10)
    hass.states.async_set(ENERGY, "10.0", {"unit_of_measurement": "kWh"}, True)
    await set_status(hass, "printing")
    await draw(hass, clock, 300, 40)
    await dry(hass, 40)
    await set_remaining(hass, 120)

    # 0.06 so far; 2 h at 300 W less the 150 W of drying, and 40 minutes at 150 W.
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.09 + 0.03)


async def test_without_a_drying_power_it_is_learned_once_each_side_ran_10_minutes(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_drying_printer(hass)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass, 48)
    await set_remaining(hass, 120)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]

    # Until then: 0.03 so far and 2 h at 150 W, without the drying.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert (run["projected_parts"], run["projected_pending"]) == (
        ["electricity"],
        ["drying"],
    )

    await draw(hass, clock, 400, 10)
    await dry(hass, 48)

    # 0.05 so far, 2 h at 150 W and 48 minutes at the 400 W less 150 W it drew.
    assert float(projected(hass).state) == pytest.approx(0.05 + 0.09 + 0.06)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert (run["projected_parts"], run["projected_pending"]) == (
        ["electricity", "drying"],
        [],
    )


async def test_drying_from_the_runs_start_counts_once_it_stopped_before_a_time_left(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_drying_printer(hass)
    await dry(hass)
    await clock.advance(minutes=10)
    hass.states.async_set(ENERGY, "10.0", {"unit_of_measurement": "kWh"}, True)
    await set_status(hass, "printing")
    await draw(hass, clock, 300, 20)
    await stop_drying(hass)
    await draw(hass, clock, 150, 40)
    await dry(hass, 40)
    await set_remaining(hass, 120)

    # 0.06 so far, 2 h at 150 W and 40 minutes at the 300 W less 150 W it drew.
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.09 + 0.03)


async def test_two_drying_units_add_up(hass: HomeAssistant, clock: Clock) -> None:
    await add_drying_printer(
        hass, units=[(ACE, ACE_LEFT), (SECOND, SECOND_LEFT)], drying_power=100
    )
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass, 60)
    await dry(hass, 60, unit=SECOND, left=SECOND_LEFT)
    await set_remaining(hass, 120)

    # 2 h at 150 W, and each unit 1 h at 100 W.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09 + 0.06)


@pytest.mark.parametrize(
    ("drying_power", "total", "pending"),
    [(200, 0.03 + 0.09 + 0.03, []), (None, 0.03 + 0.09, ["drying"])],
)
async def test_a_device_on_average_powers_adds_the_drying_power_it_was_given(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    drying_power: float | None,
    total: float,
    pending: list[str],
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass,
        entry,
        running_power=150,
        remaining_time=REMAINING,
        slots=SLOTS,
        drying=[(ACE, ACE_LEFT)],
        drying_power=drying_power,
    )
    await set_status(hass, "printing")
    await clock.advance(minutes=40)
    await dry(hass, 30)
    await set_remaining(hass, 120)

    # 0.03 so far, its running power over the 2 h left, and with a drying power
    # half an hour of it; without one, nothing is learned from an estimate.
    assert float(projected(hass).state) == pytest.approx(total)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_pending"] == pending
