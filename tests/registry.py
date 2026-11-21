"""Registers an HA device the way an integration does, for an Integration Profile's fixture."""

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry


@dataclass
class HaDevice:
    device: dr.DeviceEntry
    # A second HA device linked to `device` with `via_device_id`, such as an ACE unit.
    linked: dr.DeviceEntry | None
    # Entity ids by the integration's entity key.
    entities: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def entity(
    platform: str,
    unique_id: str,
    *,
    unit: str | None = None,
    capabilities: dict[str, Any] | None = None,
    disabled: bool = False,
    linked: bool = False,
    object_id: str | None = None,
) -> dict[str, Any]:
    """An entity of `add_ha_device`: `linked` puts it on the linked HA device, and its
    object id defaults to its HA device's name and its key."""
    return {
        "platform": platform,
        "unique_id": unique_id,
        "unit": unit,
        "capabilities": capabilities,
        "disabled": disabled,
        "linked": linked,
        "object_id": object_id,
    }


def add_ha_device(
    hass: HomeAssistant,
    config_entry: str | ConfigEntry,
    entities: dict[str, dict[str, Any]],
    *,
    linked: dict[str, Any] | None = None,
    **device: Any,
) -> HaDevice:
    """An HA device of `config_entry` (a domain gets a config entry of its own, an
    entry is used as it is) with `entities` by key, made with `entity`.

    `device` and `linked` are the HA devices' registry fields; their identifiers
    default to the domain and the name.
    """
    if isinstance(config_entry, str):
        mock_entry = MockConfigEntry(domain=config_entry)
        mock_entry.add_to_hass(hass)
    entry = mock_entry if isinstance(config_entry, str) else config_entry
    domain = entry.domain
    devices = dr.async_get(hass)

    def create(fields: dict[str, Any]) -> dr.DeviceEntry:
        return devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            **{"identifiers": {(domain, fields["name"])}} | fields,
        )

    ha_device = create(device)
    second = None
    if linked is not None:
        second = create(linked)
        # HA 2026.5 has no `via_device_id` on create and later releases refuse `via_device`.
        devices.async_update_device(second.id, via_device_id=ha_device.id)

    def owner(spec: dict[str, Any]) -> dr.DeviceEntry:
        if not spec["linked"]:
            return ha_device
        assert second is not None, "a linked entity needs a linked HA device"
        return second

    registry = er.async_get(hass)
    ids = {
        key: registry.async_get_or_create(
            spec["platform"],
            domain,
            spec["unique_id"],
            config_entry=entry,
            device_id=owner(spec).id,
            suggested_object_id=slugify(
                spec["object_id"] or f"{owner(spec).name} {key}"
            ),
            unit_of_measurement=spec["unit"],
            capabilities=spec["capabilities"],
            disabled_by=er.RegistryEntryDisabler.INTEGRATION
            if spec["disabled"]
            else None,
        ).entity_id
        for key, spec in entities.items()
    }
    return HaDevice(ha_device, second, ids)
