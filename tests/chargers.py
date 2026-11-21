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


# HACS `evcc_intg`'s entities of a loadpoint by key: platform and unit.
EVCC_LOADPOINT_ENTITIES = {
    "charging": ("binary_sensor", None),
    "connected": ("binary_sensor", None),
    "charge_total_import": ("sensor", "kWh"),
    "charged_energy": ("sensor", "kWh"),
    "session_energy": ("sensor", "kWh"),
    "session_price": ("sensor", "EUR"),
}


def add_evcc_site(
    hass: HomeAssistant,
    loadpoints: tuple[str, ...] = ("garage",),
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    system_id: str = "evcc",
) -> list[HaDevice]:
    """HACS `evcc_intg`: unique ids `evcc_intg.<system id>_<loadpoint>_<key>`, from the
    slugified titles of the config entry and the loadpoint.

    Returns each loadpoint's HA device: with one loadpoint that is the site's, with
    several each loadpoint has its own, not linked to the site's. A vehicle is an HA
    device of its own. `disabled` and `missing` apply to every loadpoint.
    """
    entry = MockConfigEntry(domain="evcc_intg", title=system_id)
    entry.add_to_hass(hass)

    def loadpoint(name: str) -> dict[str, dict[str, Any]]:
        return {
            key: entity(
                platform,
                f"evcc_intg.{system_id}_{name}_{key}",
                unit=unit,
                disabled=key in disabled,
                object_id=f"{system_id} {name} {key}",
            )
            for key, (platform, unit) in EVCC_LOADPOINT_ENTITIES.items()
            if key not in missing
        }

    add_ha_device(
        hass,
        entry,
        {"soc": entity("sensor", f"evcc_intg.{system_id}_tesla_soc", unit="%")},
        identifiers={("evcc_intg", "did_evcc_local_tesla")},
        name=f"evcc - Vehicle Tesla [{system_id}]",
    )

    def site(loadpoint_entities: dict[str, dict[str, Any]]) -> HaDevice:
        return add_ha_device(
            hass,
            entry,
            {
                "grid_power": entity(
                    "sensor", f"evcc_intg.{system_id}_grid_power", unit="W"
                )
            }
            | loadpoint_entities,
            identifiers={("evcc_intg", "did_evcc_local")},
            name=f"evcc ☀️🚘 Solar Charging [{system_id}]",
        )

    if len(loadpoints) == 1:
        return [site(loadpoint(*loadpoints))]
    site({})
    return [
        add_ha_device(
            hass,
            entry,
            loadpoint(name),
            identifiers={("evcc_intg", f"did_evcc_local_{name}")},
            name=f"evcc - Loadpoint {name.title()} [{system_id}]",
        )
        for name in loadpoints
    ]


# HACS `ocpp`'s metrics (dots as underscores, lower case) and their units.
OCPP_CONNECTOR_METRICS = {
    "status_connector": None,
    "energy_active_import_register": "kWh",
    "energy_session": "kWh",
    "energy_meter_start": "kWh",
}
OCPP_CHARGER_METRICS = {"status": None, "heartbeat": None}


def add_charge_point(
    hass: HomeAssistant,
    *,
    connectors: int = 1,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    cpid: str = "charger",
) -> list[HaDevice]:
    """HACS `ocpp`: unique ids `ocpp.<cpid>[.conn<n>].<metric>.sensor`.

    With one connector every sensor is the charger's HA device's, without `.conn<n>`;
    with several, each connector is an HA device linked to the charger's and holds its
    own sensors. Returns the charger's HA device, then each connector's.
    `disabled` and `missing` apply to every connector.
    """
    entry = MockConfigEntry(domain="ocpp", title=cpid)
    entry.add_to_hass(hass)

    def sensors(metrics: dict[str, str | None], scope: str) -> dict[str, Any]:
        return {
            key: entity(
                "sensor",
                f"ocpp.{scope}.{key}.sensor",
                unit=unit,
                disabled=key in disabled,
                object_id=f"{scope} {key}",
            )
            for key, unit in metrics.items()
            if key not in missing
        }

    flat = OCPP_CONNECTOR_METRICS if connectors == 1 else {}
    charger = add_ha_device(
        hass,
        entry,
        sensors({**OCPP_CHARGER_METRICS, **flat}, cpid),
        identifiers={("ocpp", cpid)},
        name=cpid,
    )
    if connectors == 1:
        return [charger]
    connector_devices = [
        add_ha_device(
            hass,
            entry,
            sensors(OCPP_CONNECTOR_METRICS, f"{cpid}.conn{n}"),
            identifiers={("ocpp", f"{cpid}-conn{n}")},
            name=f"{cpid} Connector {n}",
        )
        for n in range(1, connectors + 1)
    ]
    devices = dr.async_get(hass)
    for connector in connector_devices:
        # HA 2026.5 has no `via_device_id` on create and later releases refuse `via_device`.
        updated = devices.async_update_device(
            connector.device.id, via_device_id=charger.device.id
        )
        assert updated is not None
        connector.device = updated
    return [charger, *connector_devices]


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
