"""Meter reports Coin-op missed while it was stopped come from recorder history."""

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.typing import RecorderInstanceGenerator

from custom_components.coinop.const import DOMAIN

from .clock import Clock
from .devices import add_device, add_hub
from .test_dynamic_price import PRICE_ENTITY, set_price
from .test_lifecycle import start_coinop, stop_coinop
from .test_measured import add_metered_device, electricity, set_meter
from .test_projected_drying import add_drying_printer, draw, dry, stop_drying
from .test_projected_total import (
    REMAINING,
    add_timed_printer,
    projected,
    set_remaining,
)
from .test_runs import NO_MATERIAL, set_status, stored_runs


@pytest.fixture
async def mock_recorder_before_hass(
    async_setup_recorder_instance: RecorderInstanceGenerator,
) -> None:
    """Set the recorder up before `hass`, as the recorder fixtures require."""


@pytest.fixture(autouse=True)
async def recorder(
    hass: HomeAssistant,
    clock: Clock,
    async_setup_recorder_instance: RecorderInstanceGenerator,
) -> None:
    """Recording from `CLOCK_START` on."""
    await async_setup_recorder_instance(hass)


async def test_reports_missed_while_stopped_are_filled_from_recorder_history(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)

    await stop_coinop(hass, entry)
    await clock.advance(minutes=10)
    await set_meter(hass, 10.1)
    await clock.advance(minutes=10)
    await set_status(hass, "finished")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.5)
    await async_wait_recording_done(hass)
    await clock.advance(minutes=1)
    await start_coinop(hass, entry)

    [run] = stored_runs(hass_storage)
    assert run["ended"] == "2026-01-15T10:30:00+00:00"
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert run["flags"] == NO_MATERIAL


async def test_price_changes_missed_while_stopped_come_from_recorder_history(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=1000, price=PRICE_ENTITY)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)

    await stop_coinop(hass, entry)
    await clock.advance(minutes=20)
    await set_price(hass, 0.40)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await async_wait_recording_done(hass)
    await clock.advance(minutes=1)
    await start_coinop(hass, entry)

    [run] = stored_runs(hass_storage)
    assert [s["unit_price"] for s in electricity(run)["segments"]] == [0.20, 0.40]
    assert electricity(run)["amount"] == pytest.approx(0.5 * 0.20 + 0.5 * 0.40)


async def test_a_restart_during_a_pause_holds_the_time_left_from_before_it(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    [entry] = hass.config_entries.async_entries(DOMAIN)
    await set_status(hass, "printing")
    await set_remaining(hass, 90)
    await clock.advance(minutes=30)
    await set_remaining(hass, 60)
    await clock.advance(seconds=10)
    await set_status(hass, "paused")
    await set_remaining(hass, 0)
    await clock.advance(minutes=20)
    await async_wait_recording_done(hass)

    await stop_coinop(hass, entry)
    await start_coinop(hass, entry)

    # 0.03 so far, and the hour left before the pause at 200 W.
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.03 + 0.06)
    assert state.attributes["ends_at"] == clock.now() + timedelta(minutes=60)


async def test_a_restart_mid_run_learns_from_the_drying_the_recorder_kept(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_drying_printer(hass)
    await set_status(hass, "printing")
    await draw(hass, clock, 150, 40)
    await dry(hass)
    await draw(hass, clock, 300, 20)
    await stop_drying(hass)
    await draw(hass, clock, 150, 40)
    await async_wait_recording_done(hass)

    await stop_coinop(hass, entry)
    await start_coinop(hass, entry)
    await dry(hass, 40)
    await set_remaining(hass, 120)

    # 0.09 so far, 2 h at 150 W and 40 minutes at the 300 W less 150 W it drew.
    assert float(projected(hass).state) == pytest.approx(0.09 + 0.09 + 0.03)
