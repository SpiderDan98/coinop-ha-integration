"""Projected Total: an open Run's cost so far plus the rest its time left adds."""

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
import pytest

from .clock import Clock
from .devices import ENERGY, add_device, add_hub
from .test_measured import set_meter
from .test_runs import set_status, stored_runs
from .test_templates import WEAR, add_template, create
from .websocket import PanelClient

REMAINING = "sensor.kobra_time_remaining"
PROJECTED = "sensor.kobra_projected_run_cost"


async def set_remaining(hass: HomeAssistant, minutes: float | str) -> None:
    hass.states.async_set(REMAINING, str(minutes), {"unit_of_measurement": "min"})
    await hass.async_block_till_done()


def projected(hass: HomeAssistant) -> State:
    state = hass.states.get(PROJECTED)
    assert state is not None
    return state


async def add_metered_printer(hass: HomeAssistant, **options: Any) -> None:
    await set_meter(hass, 10.0)
    entry = await add_hub(hass)
    await add_device(
        hass,
        entry,
        source="energy",
        meter={"entity_id": ENERGY},
        price=0.30,
        remaining_time=REMAINING,
        **options,
    )


async def preheat_then_print(hass: HomeAssistant, clock: Clock) -> None:
    """40 minutes at 600 W heating up, then 40 at 150 W: 0.5 kWh so far."""
    await set_status(hass, "printing")
    for kwh in (0.1, 0.2, 0.3, 0.4, 0.425, 0.45, 0.475, 0.5):
        await clock.advance(minutes=10)
        await set_meter(hass, 10.0 + kwh)


async def test_a_metered_run_projects_its_rest_from_the_last_half_hours_power(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_metered_printer(hass)
    assert projected(hass).state == STATE_UNKNOWN

    await preheat_then_print(hass, clock)
    await set_remaining(hass, 120)

    # 0.15 so far, and 2 h at 150 W: 0.3 kWh at 0.30, not the preheat's average.
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.24)
    assert state.attributes["ends_at"] == clock.now() + timedelta(hours=2)
    assert state.attributes["unit_of_measurement"] == "EUR"
    assert state.attributes["device_class"] == "monetary"


async def test_a_preheat_in_the_last_half_hour_still_counts(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_metered_printer(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=20)
    await set_meter(hass, 10.2)
    await set_remaining(hass, 60)

    # Less than half an hour ran: its own 600 W, for 1 h at 0.30.
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.18)


async def test_a_device_on_average_powers_projects_its_running_power(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass, entry, running_power=200, price=0.30, remaining_time=REMAINING
    )
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_remaining(hass, 90)

    # 0.03 so far, and 1.5 h at 200 W.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)


async def test_running_hours_line_items_add_their_rate_over_the_time_left(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, source="none", remaining_time=REMAINING)
    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await add_template(panel, run["id"], await create(panel, **WEAR))
    await clock.advance(hours=1)
    await set_remaining(hass, 120)

    # 1 h of wear at 0.15 so far, 2 h to come.
    assert float(projected(hass).state) == pytest.approx(0.15 + 0.30)


async def test_without_a_time_left_or_anything_to_project_there_is_no_value(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, source="none", remaining_time=REMAINING)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    assert projected(hass).state == STATE_UNKNOWN

    await set_remaining(hass, 30)
    assert projected(hass).state == STATE_UNKNOWN
    assert "ends_at" not in projected(hass).attributes


async def test_the_projection_follows_the_time_left_and_ends_with_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass, entry, running_power=200, price=0.30, remaining_time=REMAINING
    )
    await set_remaining(hass, STATE_UNKNOWN)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    assert projected(hass).state == STATE_UNKNOWN

    await set_remaining(hass, 30)
    assert float(projected(hass).state) == pytest.approx(0.06)
    await clock.advance(minutes=30)
    await set_remaining(hass, 0)
    assert float(projected(hass).state) == pytest.approx(0.06)

    await set_status(hass, "finished")
    assert projected(hass).state == STATE_UNKNOWN
    assert "ends_at" not in projected(hass).attributes
    [run] = stored_runs(hass_storage)
    assert not any("project" in key for key in run)
