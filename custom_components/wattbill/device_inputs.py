"""Reading Device Inputs from Home Assistant's state machine and entity registry."""

from datetime import datetime

from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

ON_OFF_DOMAINS = frozenset({"binary_sensor", "switch", "input_boolean"})


def input_value(state: State | None, attribute: str | None) -> str | None:
    """The input's current value, or None while it has none to give."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    if attribute is None and state.domain == "event":
        # An event entity's state is the time it fired; the value is the event type.
        attribute = ATTR_EVENT_TYPE
    value = state.state if attribute is None else state.attributes.get(attribute)
    return None if value is None else str(value)


def input_time(state: State, attribute: str | None) -> datetime:
    """When the input took its current value."""
    if state.domain == "event" and (fired := dt_util.parse_datetime(state.state)):
        return fired
    return state.last_changed if attribute is None else state.last_updated


def offered_values(
    hass: HomeAssistant, entity_id: str, attribute: str | None
) -> list[str]:
    """Values the input can take, also while it is unavailable; empty if unknown."""
    state = hass.states.get(entity_id)
    if attribute is None:
        registry_entry = er.async_get(hass).async_get(entity_id)
        capabilities = (registry_entry.capabilities if registry_entry else None) or {}
        for key in (ATTR_EVENT_TYPES, ATTR_OPTIONS):
            values = capabilities.get(key) or (
                state.attributes.get(key) if state else None
            )
            if values:
                return [str(value) for value in values]
        if split_entity_id(entity_id)[0] in ON_OFF_DOMAINS or (
            state and state.state in (STATE_ON, STATE_OFF)
        ):
            return [STATE_ON, STATE_OFF]
    current = input_value(state, attribute)
    return [current] if current else []
