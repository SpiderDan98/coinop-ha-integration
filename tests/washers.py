"""Registry entries shaped like WashData, Miele and Home Connect register an
appliance.

Unique ids, units, options and what tells the appliance's kind follow each
integration's source.
"""

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry


@dataclass
class Washer:
    device: dr.DeviceEntry
    # Entity ids by the integration's entity key.
    entities: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def _washer(
    hass: HomeAssistant, domain: str, identifier: str, name: str
) -> tuple[MockConfigEntry, Washer]:
    config_entry = MockConfigEntry(domain=domain)
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(domain, identifier)},
        name=name,
    )
    return config_entry, Washer(device)


def _add(
    hass: HomeAssistant,
    washer: Washer,
    config_entry: ConfigEntry,
    platform: str,
    key: str,
    unique_id: str,
    object_id: str,
    **kwargs: Any,
) -> None:
    washer.entities[key] = (
        er.async_get(hass)
        .async_get_or_create(
            platform,
            config_entry.domain,
            unique_id,
            config_entry=config_entry,
            device_id=washer.device.id,
            suggested_object_id=object_id,
            **kwargs,
        )
        .entity_id
    )


def add_washdata(
    hass: HomeAssistant,
    device_type: str | None = "washing_machine",
    *,
    name: str = "Washer",
    changed_to: str | None = None,
) -> Washer:
    """3dg1luk43/ha_washdata: one HA device per config entry, named after it, unique
    ids `<entry id>_<key>`.

    `device_type` is the kind picked when the entry was created, which WashData keeps
    in the entry's data (None: an entry without one, which WashData reads as a washing
    machine). `changed_to` is a kind picked later: it goes to the options, and the
    data keeps the old one.
    """
    settings = {"power_sensor": "sensor.plug_power", "min_power": 2.0}
    kind = {} if device_type is None else {"device_type": device_type}
    config_entry = MockConfigEntry(
        domain="ha_washdata",
        title=name,
        version=3,
        minor_version=13,
        data={"name": name} | kind | settings,
        options={"device_type": changed_to} | settings if changed_to else {},
    )
    config_entry.add_to_hass(hass)
    washer = Washer(
        dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={("ha_washdata", config_entry.entry_id)},
            manufacturer="WashData",
            name=name,
        )
    )

    def add(key: str, **kwargs: Any) -> None:
        _add(
            hass,
            washer,
            config_entry,
            "sensor",
            key,
            f"{config_entry.entry_id}_{key}",
            key,
            translation_key=key,
            **kwargs,
        )

    add("washer_state")
    add("washer_program")
    add("current_power", unit_of_measurement="W")
    add("energy_total", unit_of_measurement="kWh")
    add("last_cycle_energy", unit_of_measurement="kWh")
    add("last_cycle_cost")
    return washer


# HA core `miele`'s sensors by key: object id, translation key and unit.
MIELE_SENSORS = {
    "state_status": ("status", "status", None),
    "state_program_id": ("program", "program_id", None),
    "state_program_phase": ("program_phase", "program_phase", None),
    "current_energy_consumption": ("energy_consumption", "energy_consumption", "kWh"),
    "current_water_consumption": ("water_consumption", "water_consumption", "L"),
}
_STATUS = ("state_status",)
_PROGRAM = (*_STATUS, "state_program_id", "state_program_phase")
_ENERGY = (*_PROGRAM, "current_energy_consumption")
_WATER = (*_ENERGY, "current_water_consumption")
# The sensors it registers for an appliance, by the model it gives the HA device: the
# appliance type's tag (`DEVICE_TYPE_TAGS` in its const.py), capitalised, and the
# `types` of each sensor description in its sensor.py.
MIELE_MODELS = {
    "Washing machine": _WATER,
    "Washer dryer": _WATER,
    "Dishwasher": _WATER,
    "Tumble dryer": _ENERGY,
    "Coffee system": _PROGRAM,
    "Oven": _PROGRAM,
    "Oven microwave": _PROGRAM,
    "Steam oven": _PROGRAM,
    "Steam oven combi": _PROGRAM,
    "Steam oven micro": _PROGRAM,
    "Dialog oven": _PROGRAM,
    "Microwave": _PROGRAM,
    "Warming drawer": _PROGRAM,
    "Hob": _STATUS,
    "Hood": _STATUS,
    "Refrigerator": _STATUS,
}


def add_miele(
    hass: HomeAssistant,
    model: str = "Washing machine",
    *,
    serial: str = "000123456789",
) -> Washer:
    """HA core `miele`: every appliance of an account on one config entry, named
    after its kind, unique ids `<serial>-<key>`.

    `model` is the appliance's kind as the integration writes it on the HA device; it
    also decides which sensors the integration registers. A second appliance needs
    its own `serial`.
    """
    config_entry = next(iter(hass.config_entries.async_entries("miele")), None)
    if config_entry is None:
        config_entry = MockConfigEntry(domain="miele")
        config_entry.add_to_hass(hass)
    washer = Washer(
        dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={("miele", serial)},
            manufacturer="Miele",
            name=model,
            model=model,
            serial_number=serial,
        )
    )
    for key in MIELE_MODELS[model]:
        object_id, translation_key, unit = MIELE_SENSORS[key]
        _add(
            hass,
            washer,
            config_entry,
            "sensor",
            key,
            f"{serial}-{key}",
            f"{slugify(model)}_{object_id}",
            translation_key=translation_key,
            unit_of_measurement=unit,
        )
    return washer


def add_home_connect(hass: HomeAssistant) -> Washer:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`."""
    config_entry, washer = _washer(
        hass, "home_connect", "SIEMENS-WM14T6H0-0123", "Washer"
    )

    def add(platform: str, key: str, object_id: str, translation_key: str) -> None:
        _add(
            hass,
            washer,
            config_entry,
            platform,
            key,
            f"SIEMENS-WM14T6H0-0123-{key}",
            f"washer_{object_id}",
            translation_key=translation_key,
        )

    add(
        "sensor",
        "BSH.Common.Status.OperationState",
        "operation_state",
        "operation_state",
    )
    add("sensor", "BSH.Common.Status.DoorState", "door", "door")
    add(
        "select",
        "BSH.Common.Root.SelectedProgram",
        "selected_program",
        "selected_program",
    )
    add("select", "BSH.Common.Root.ActiveProgram", "active_program", "active_program")
    return washer
