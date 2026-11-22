"""Projected Total: a multi-material unit's drying adds its power while it overlaps
the Run's time left."""

from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import ENERGY
from .test_measured import set_meter
from .test_projected_total import add_metered_printer, projected, set_remaining
from .test_runs import set_status

ACE = "switch.ace_drying"
ACE_LEFT = "sensor.ace_drying_remaining"
SECOND = "binary_sensor.second_ace_drying"
SECOND_LEFT = "sensor.second_ace_drying_remaining"
SLOTS = ["sensor.ace_slot_1"]


async def add_drying_printer(
    hass: HomeAssistant,
    units: list[tuple[str, str | None]] | None = None,
    **options: Any,
) -> None:
    """A metered printer at 0.30 per kWh with one ACE, unless `units` says otherwise."""
    await add_metered_printer(
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
