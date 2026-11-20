"""Registry entries shaped like WashData, Miele and Home Connect register a washer.

Unique ids, units and options follow each integration's source.
"""

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    config_entry: MockConfigEntry,
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


def add_washdata(hass: HomeAssistant) -> Washer:
    """3dg1luk43/ha_washdata: one HA device per config entry, unique ids
    `<entry id>_<key>`."""
    config_entry, washer = _washer(hass, "ha_washdata", "washdata", "Washer")

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


def add_miele(hass: HomeAssistant, *, consumption: bool = True) -> Washer:
    """HA core `miele`: unique ids `<serial>-<key>`. Older washers report no
    consumption, so `consumption` may leave those sensors out."""
    config_entry, washer = _washer(hass, "miele", "000123456789", "Washing machine")

    def add(key: str, object_id: str, **kwargs: Any) -> None:
        _add(
            hass,
            washer,
            config_entry,
            "sensor",
            key,
            f"000123456789-{key}",
            f"washing_machine_{object_id}",
            **kwargs,
        )

    add("state_status", "status", translation_key="status")
    add("state_program_id", "program", translation_key="program_id")
    add("state_program_phase", "program_phase", translation_key="program_phase")
    if consumption:
        add(
            "current_energy_consumption",
            "energy_consumption",
            translation_key="energy_consumption",
            unit_of_measurement="kWh",
        )
        add(
            "current_water_consumption",
            "water_consumption",
            translation_key="water_consumption",
            unit_of_measurement="L",
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
