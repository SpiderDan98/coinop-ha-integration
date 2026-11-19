"""Frozen, advanceable clock for driving HA timers deterministically."""

from datetime import UTC, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

CLOCK_START = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


class Clock:
    """Frozen clock that only moves when a test says so, firing due HA timers."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        self._hass = hass
        self._freezer = freezer

    def now(self) -> datetime:
        return dt_util.utcnow()

    async def advance(self, delta: timedelta | None = None, **kwargs: float) -> None:
        """Move forward by `delta` or `timedelta(**kwargs)`, e.g. `minutes=5`."""
        self._freezer.tick(delta if delta is not None else timedelta(**kwargs))
        await self._fire()

    async def move_to(self, moment: datetime) -> None:
        self._freezer.move_to(moment)
        await self._fire()

    async def _fire(self) -> None:
        async_fire_time_changed(self._hass)
        await self._hass.async_block_till_done()
