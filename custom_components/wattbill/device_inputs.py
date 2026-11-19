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
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    EnergyConverter,
    MassConverter,
    PowerConverter,
)

from .device_config import ConsumptionSource
from .models import UsageUnit

ON_OFF_DOMAINS = frozenset({"binary_sensor", "switch", "input_boolean"})
# Readings are kept in kWh (energy) or W (power).
METER_UNITS = {
    ConsumptionSource.ENERGY: (EnergyConverter, UnitOfEnergy.KILO_WATT_HOUR),
    ConsumptionSource.POWER: (PowerConverter, UnitOfPower.WATT),
}
USAGE_UNITS = (
    (DistanceConverter, UsageUnit.MILLIMETRE),
    (MassConverter, UsageUnit.GRAM),
)
# Price units name the currency by its code or one of these symbols.
CURRENCY_SYMBOLS = {
    "EUR": {"€"},
    "USD": {"$"},
    "AUD": {"$", "A$"},
    "CAD": {"$", "C$"},
    "NZD": {"$", "NZ$"},
    "GBP": {"£"},
    "JPY": {"¥"},
    "CHF": {"Fr.", "Fr"},
    "SEK": {"kr"},
    "NOK": {"kr"},
    "DKK": {"kr"},
    "PLN": {"zł"},
    "CZK": {"Kč"},
    "INR": {"₹"},
}
# Sub-units worth a hundredth of the currency: cent, penny, Rappen, öre, grosz.
SUB_UNITS = frozenset(
    {"ct", "c", "¢", "cent", "cents", "p", "rp", "öre", "øre", "ore", "gr"}
)


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
    if split_entity_id(state.entity_id)[0] == "event" and (
        fired := dt_util.parse_datetime(state.state)
    ):
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


def usage_scale(unit: str | None) -> tuple[float, UsageUnit] | None:
    """Factor from `unit` to mm or g; None if it is neither a length nor a mass."""
    for converter, canonical in USAGE_UNITS:
        if unit in converter.VALID_UNITS:
            return converter.get_unit_ratio(canonical, unit), canonical
    return None


def price_scale(unit: str | None, currency: str) -> float | None:
    """Factor from a price in `unit` to `currency`/kWh; None if not recognised."""
    if unit is None or unit.count("/") != 1:
        return None
    money, energy = (part.strip() for part in unit.split("/"))
    if energy not in EnergyConverter.VALID_UNITS:
        return None
    if money.upper() == currency.upper() or money in CURRENCY_SYMBOLS.get(
        currency.upper(), set()
    ):
        scale = 1.0
    elif money.lower() in SUB_UNITS:
        scale = 0.01
    else:
        return None
    return scale * EnergyConverter.get_unit_ratio(energy, UnitOfEnergy.KILO_WATT_HOUR)


def _number(state: State | None, attribute: str | None) -> float | None:
    value = input_value(state, attribute)
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _reported_unit(state: State, attribute: str | None) -> str | None:
    """An attribute has no unit of its own; the state's unit is the entity's."""
    return None if attribute else state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)


def price_reading(
    state: State | None, price: Mapping[str, Any], currency: str
) -> float | None:
    """The price entity's current price in `currency`/kWh, or None while it has none."""
    number = _number(state, price["attribute"])
    if state is None or number is None:
        return None
    scale = (
        price_scale(_reported_unit(state, price["attribute"]), currency)
        or price_scale(price["unit"], currency)
        or price["factor"]
    )
    return None if scale is None else number * scale


def meter_reading(state: State | None, meter: Mapping[str, Any]) -> float | None:
    """The meter's current reading in kWh or W, or None while it has none."""
    number = _number(state, meter["attribute"])
    if state is None or number is None:
        return None
    source = ConsumptionSource(meter["source"])
    scale = (
        unit_scale(source, _reported_unit(state, meter["attribute"]))
        or unit_scale(source, meter["unit"])
        or meter["factor"]
    )
    return None if scale is None else number * scale
