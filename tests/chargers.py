"""Registry entries shaped like EV charger integrations register a charger.

Unique ids, units and which entities are registered follow each integration's source.
"""

from homeassistant.core import HomeAssistant

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
