"""Shared fixtures: every test gets a fresh Home Assistant instance from `hass`."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest

# Imported first so `custom_components` resolves to this repo, not to the test
# config dir that HA puts on sys.path.
import custom_components.wattbill  # noqa: F401

from .clock import CLOCK_START, Clock


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load `custom_components/wattbill` in every test."""


@pytest.fixture
def clock(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Clock:
    """Clock frozen at `CLOCK_START`; advance it with `await clock.advance(...)`."""
    freezer.move_to(CLOCK_START)
    return Clock(hass, freezer)
