"""Reading Device Inputs from Home Assistant's state machine and entity registry."""

from collections.abc import Mapping
from datetime import datetime
import math
from typing import Any

from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, PowerConverter

from .device_config import ConsumptionSource

ON_OFF_DOMAINS = frozenset({"binary_sensor", "switch", "input_boolean"})
# Readings are kept in kWh (energy) or W (power).
METER_UNITS = {
    ConsumptionSource.ENERGY: (EnergyConverter, UnitOfEnergy.KILO_WATT_HOUR),
    ConsumptionSource.POWER: (PowerConverter, UnitOfPower.WATT),
}


def input_value(state: State | None, attribute: str | None) -> str | None:
    """The input's current value, or None while it has none to give."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    # Not state.domain: states from recorder history don't have it.
    if attribute is None and split_entity_id(state.entity_id)[0] == "event":
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


def entity_unit(hass: HomeAssistant, entity_id: str) -> str | None:
    """The unit from the entity registry, which keeps it while unavailable."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry and registry_entry.unit_of_measurement:
        return registry_entry.unit_of_measurement
    state = hass.states.get(entity_id)
    return state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None


def unit_scale(source: ConsumptionSource, unit: str | None) -> float | None:
    """Factor from `unit` to kWh or W; None if WattBill doesn't recognise it."""
    converter, canonical = METER_UNITS[source]
    if unit not in converter.VALID_UNITS:
        return None
    return converter.get_unit_ratio(canonical, unit)


def meter_reading(state: State | None, meter: Mapping[str, Any]) -> float | None:
    """The meter's current reading in kWh or W, or None while it has none."""
    value = input_value(state, meter["attribute"])
    if state is None or value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    reported_unit = (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if meter["attribute"] is None
        else None
    )
    source = ConsumptionSource(meter["source"])
    scale = (
        unit_scale(source, reported_unit)
        or unit_scale(source, meter["unit"])
        or meter["factor"]
    )
    return None if scale is None or not math.isfinite(number) else number * scale
