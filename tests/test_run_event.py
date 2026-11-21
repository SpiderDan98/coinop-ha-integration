"""The Run event entity: `started` when a Run opens, `ended` once it is final."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_persistence import restart
from .test_runs import set_status

RUN_EVENT = "event.kobra_run"


def record_events(
    hass: HomeAssistant, entity_id: str = RUN_EVENT
) -> list[dict[str, Any]]:
    """Attributes of each event the Run event entity fires, in order."""
    fired: list[dict[str, Any]] = []
    # The state is the event's timestamp; a restart restores it without firing. Older
    # Home Assistant gives two events of one instant the same timestamp, so the
    # event's type tells them apart.
    seen: set[tuple[str, Any]] = set()

    # Without it Home Assistant runs the listener in a thread, in no certain order.
    @callback
    def on_change(event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None or new.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        key = (new.state, new.attributes.get("event_type"))
        if key not in seen:
            seen.add(key)
            fired.append(dict(new.attributes))

    async_track_state_change_event(hass, entity_id, on_change)
    return fired


async def test_the_run_event_offers_started_and_ended(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    state = hass.states.get(RUN_EVENT)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["event_types"] == ["started", "ended"]


async def test_a_run_fires_started_then_ended_once_with_its_final_values(
    hass: HomeAssistant, clock: Clock
) -> None:
    hass.config.currency = "EUR"
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    fired = record_events(hass)

    await set_status(hass, "printing")
    started = clock.now()
    await clock.advance(minutes=90)
    await set_status(hass, "finished")
    ended = clock.now()
    await clock.advance(hours=2)
    await set_status(hass, "idle")
    await restart(hass, entry)
    await clock.advance(hours=1)

    assert [event["event_type"] for event in fired] == ["started", "ended"]
    assert {k: fired[0][k] for k in ("name", "start")} == {
        "name": None,
        "start": started,
    }
    keys = (
        "name",
        "outcome",
        "start",
        "end",
        "running_hours",
        "total_cost",
        "cost_per_part",
        "part_count",
        "energy_kwh",
        "material_grams",
        "has_flags",
    )
    assert {k: fired[1][k] for k in keys} == {
        "name": None,
        "outcome": "completed",
        "start": started,
        "end": ended,
        "running_hours": pytest.approx(1.5),
        "total_cost": pytest.approx(0.15),
        "cost_per_part": pytest.approx(0.15),
        "part_count": 1,
        "energy_kwh": pytest.approx(0.15),
        "material_grams": 0,
        "has_flags": True,
    }


async def test_each_run_fires_its_own_ended(hass: HomeAssistant, clock: Clock) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await add_device(hass, entry, name="Voron", status="sensor.voron_status")
    fired = record_events(hass)

    for _ in range(2):
        await set_status(hass, "printing")
        await clock.advance(minutes=30)
        await set_status(hass, "cancelled")
        await clock.advance(minutes=30)

    assert [event["event_type"] for event in fired] == [
        "started",
        "ended",
        "started",
        "ended",
    ]
    voron = hass.states.get("event.voron_run")
    assert voron is not None
    assert voron.state == STATE_UNKNOWN
