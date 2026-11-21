"""Registry entries shaped like EV charger integrations register a charger.

Unique ids, units and which entities are registered follow each integration's source.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .registry import HaDevice, add_ha_device, entity

# HA core `tesla_wall_connector`'s entities by key: platform, object id and the unit
# HA shows (both energy counters are native Wh, suggested kWh).
WALL_CONNECTOR_ENTITIES = {
    "status": ("sensor", "status", None),
    "energy_kWh": ("sensor", "energy", "kWh"),
    "session_energy_wh": ("sensor", "session_energy", "kWh"),
    "evse_state": ("sensor", "state_code", None),
    "vehicle_connected": ("binary_sensor", "vehicle_connected", None),
    "contactor_closed": ("binary_sensor", "contactor_closed", None),
}


def add_wall_connector(
    hass: HomeAssistant,
    *,
    disabled: tuple[str, ...] = ("evse_state",),
    missing: tuple[str, ...] = (),
    serial: str = "PGT21234567890",
) -> HaDevice:
    """HA core `tesla_wall_connector`: one HA device per Wall Connector, unique ids
    `<serial>-<key>`.

    `disabled` are registered but disabled (the raw state code is by default),
    `missing` aren't registered at all.
    """
    return add_ha_device(
        hass,
        "tesla_wall_connector",
        {
            key: entity(
                platform,
                f"{serial}-{key}",
                unit=unit,
                disabled=key in disabled,
                object_id=f"Tesla Wall Connector {object_id}",
            )
            for key, (platform, object_id, unit) in WALL_CONNECTOR_ENTITIES.items()
            if key not in missing
        },
        identifiers={("tesla_wall_connector", serial)},
        manufacturer="Tesla",
        model="Wall Connector",
        name="Tesla Wall Connector",
    )


def _charger(
    hass: HomeAssistant,
    config_entry: str | ConfigEntry,
    entities: dict[str, tuple[str, str, str | None]],
    *,
    disabled: tuple[str, ...],
    missing: tuple[str, ...],
    **device: Any,
) -> HaDevice:
    """A charger's HA device with `entities` by key: platform, unique id and unit."""
    return add_ha_device(
        hass,
        config_entry,
        {
            key: entity(platform, unique_id, unit=unit, disabled=key in disabled)
            for key, (platform, unique_id, unit) in entities.items()
            if key not in missing
        },
        **device,
    )


def add_easee(
    hass: HomeAssistant,
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    charger_id: str = "EH123456",
) -> HaDevice:
    """HACS `easee`: one HA device per charger, unique ids `<charger id>_<key>`."""
    keys = {
        "status": ("sensor", None),
        "lifetime_energy": ("sensor", "kWh"),
        "session_energy": ("sensor", "kWh"),
        "cost_day": ("sensor", "EUR"),
        "smart_charging": ("binary_sensor", None),
    }
    return _charger(
        hass,
        "easee",
        {
            key: (platform, f"{charger_id}_{key}", unit)
            for key, (platform, unit) in keys.items()
        },
        disabled=disabled,
        missing=missing,
        identifiers={("easee", charger_id)},
        manufacturer="Easee",
        model="Home",
        name="Garage",
    )


def add_zaptec(
    hass: HomeAssistant,
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    charger_id: str = "0d1c3f5e-charger",
) -> HaDevice:
    """HACS `zaptec`: an HA device per installation and per charger, the charger's
    linked to its installation's, unique ids `<id>_<key>`.

    `signed_meter_value_kwh` is only registered for a charger that reports it.
    """
    entry = MockConfigEntry(domain="zaptec")
    entry.add_to_hass(hass)
    installation_id = "7a9b2c4d-installation"
    installation = add_ha_device(
        hass,
        entry,
        {
            key: entity("sensor", f"{installation_id}_{key}", unit="A")
            for key in ("max_current", "available_current_phase1")
        },
        identifiers={("zaptec", installation_id)},
        manufacturer="Zaptec",
        model="Zaptec Installation",
        name="Home",
    )
    keys = {
        "charger_operation_mode": None,
        "signed_meter_value_kwh": "kWh",
        "total_charge_power_session": "kWh",
        "total_charge_power": "W",
    }
    charger = _charger(
        hass,
        entry,
        {key: ("sensor", f"{charger_id}_{key}", unit) for key, unit in keys.items()},
        disabled=disabled,
        missing=missing,
        identifiers={("zaptec", charger_id)},
        manufacturer="Zaptec",
        model="Zaptec Go",
        name="Driveway",
    )
    dr.async_get(hass).async_update_device(
        charger.device.id, via_device_id=installation.device.id
    )
    return charger


def add_goe_mqtt(
    hass: HomeAssistant,
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    serial: str = "012345",
) -> HaDevice:
    """HACS `goecharger_mqtt`: one HA device per charger, unique ids
    `<serial>-<platform>-<key>-<attribute or 0>`; both energy counters are in Wh."""
    return _charger(
        hass,
        "goecharger_mqtt",
        {
            "car": ("sensor", f"{serial}-sensor-car-car", None),
            "eto": ("sensor", f"{serial}-sensor-eto-0", "Wh"),
            "wh": ("sensor", f"{serial}-sensor-wh-0", "Wh"),
            "etop": ("sensor", f"{serial}-sensor-etop-0", "Wh"),
            "car_connected": ("binary_sensor", f"{serial}-binary_sensor-car-1", None),
        },
        disabled=disabled,
        missing=missing,
        identifiers={("goecharger_mqtt", serial)},
        manufacturer="go-e",
        model="go-eCharger",
        name="go-eCharger",
    )


def add_goe_api2(
    hass: HomeAssistant,
    *,
    disabled: tuple[str, ...] = ("car",),
    missing: tuple[str, ...] = (),
    serial: str = "012345",
) -> HaDevice:
    """HACS `goecharger_api2`: one HA device per charger, unique ids
    `goecharger_api2.goe_<serial>_<key>`. The raw car state `car` is disabled by
    default; both energy counters are native Wh, shown in kWh."""
    keys = {
        "car_value": None,
        "car": None,
        "eto": "kWh",
        "wh": "kWh",
        "cus_value": None,
    }
    return _charger(
        hass,
        "goecharger_api2",
        {
            key: ("sensor", f"goecharger_api2.goe_{serial}_{key}", unit)
            for key, unit in keys.items()
        },
        disabled=disabled,
        missing=missing,
        identifiers={("goecharger_api2", serial)},
        manufacturer="go-e",
        model="Gemini",
        name="go-e Charger",
    )
