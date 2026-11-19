"""The `clock` fixture keeps time frozen and fires HA timers only when advanced."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from .clock import CLOCK_START, Clock


async def test_clock_starts_frozen(hass: HomeAssistant, clock: Clock) -> None:
    assert clock.now() == CLOCK_START
    await hass.async_block_till_done()
    assert clock.now() == CLOCK_START


async def test_advancing_fires_due_timers_only(
    hass: HomeAssistant, clock: Clock
) -> None:
    fired: list[datetime] = []
    async_call_later(hass, timedelta(minutes=5), fired.append)

    await clock.advance(minutes=4, seconds=59)
    assert fired == []

    await clock.advance(seconds=1)
    assert len(fired) == 1
    assert clock.now() == CLOCK_START + timedelta(minutes=5)


async def test_move_to_jumps_to_a_moment(hass: HomeAssistant, clock: Clock) -> None:
    fired: list[datetime] = []
    async_call_later(hass, timedelta(hours=30), fired.append)

    await clock.move_to(CLOCK_START + timedelta(days=2))

    assert len(fired) == 1
    assert clock.now() == CLOCK_START + timedelta(days=2)
