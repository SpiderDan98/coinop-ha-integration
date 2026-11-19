"""Meter reports WattBill missed while it was stopped come from recorder history."""

from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.typing import RecorderInstanceGenerator

from .clock import Clock
from .test_lifecycle import start_wattbill, stop_wattbill
from .test_measured import add_metered_device, electricity, set_meter
from .test_runs import set_status, stored_runs


@pytest.fixture
async def mock_recorder_before_hass(
    async_setup_recorder_instance: RecorderInstanceGenerator,
) -> None:
    """Set the recorder up before `hass`, as the recorder fixtures require."""


@pytest.fixture(autouse=True)
async def recorder(
    hass: HomeAssistant, async_setup_recorder_instance: RecorderInstanceGenerator
) -> None:
    await async_setup_recorder_instance(hass)


async def test_reports_missed_while_stopped_are_filled_from_recorder_history(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)

    await stop_wattbill(hass, entry)
    await clock.advance(minutes=10)
    await set_meter(hass, 10.1)
    await clock.advance(minutes=10)
    await set_status(hass, "finished")
    await clock.advance(minutes=10)
    await set_meter(hass, 10.5)
    await async_wait_recording_done(hass)
    await clock.advance(minutes=1)
    await start_wattbill(hass, entry)

    [run] = stored_runs(hass_storage)
    assert run["ended"] == "2026-01-15T10:30:00+00:00"
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert run["flags"] == []
