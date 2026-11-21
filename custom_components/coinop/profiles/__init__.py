"""Integration Profiles: Device Input defaults for known integrations.

A profile only pre-fills the Add Device and Detect again steps; the Device stores the
concrete entities it found, so nothing stays coupled to the profile (ADR 0004).

Each group's profiles and kind checks live in its own module (`printers`,
`appliances`, `ev_chargers`); the registry and how its entries are used live here.
"""

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.coinop.quantities import ELECTRICITY, WATER

from . import appliances, printers
from .base import Find, Integration, NoDeviceType

# Sections a profile pre-fills only in Add Device: Detect again leaves them alone.
METERS = (ELECTRICITY.source_key, WATER.source_key)

# By integration domain, in the order Quick Start and the HA device step list them.
INTEGRATIONS = {
    # 3D printers
    "anycubic": Integration(
        "Anycubic 3D Printer - Local Control",
        printers.anycubic,
        printers.DEVICE_TYPES,
        printers.KIND,
    ),
    "anycubic_cloud": Integration(
        "Anycubic Cloud & LAN",
        printers.anycubic_cloud,
        printers.DEVICE_TYPES,
        printers.KIND,
    ),
    # Appliances
    "ha_washdata": Integration(
        "WashData",
        appliances.washdata,
        appliances.DEVICE_TYPES,
        appliances.washdata_kind,
    ),
    "miele": Integration(
        "Miele", appliances.miele, appliances.DEVICE_TYPES, appliances.miele_kind
    ),
    "home_connect": Integration(
        "Home Connect",
        appliances.home_connect,
        appliances.DEVICE_TYPES,
        appliances.home_connect_kind,
    ),
    "homeconnect_ws": Integration(
        "Home Connect Local",
        appliances.home_connect_local,
        appliances.DEVICE_TYPES,
        appliances.cant_tell,
    ),
    "home_connect_alt": Integration(
        "Home Connect Alt",
        appliances.home_connect_alt,
        appliances.DEVICE_TYPES,
        appliances.cant_tell,
    ),
    "smartthings": Integration(
        "SmartThings",
        appliances.smartthings,
        appliances.SMARTTHINGS_DEVICE_TYPES,
        appliances.smartthings_kind,
    ),
    # EV chargers
}


def _serving(device_type: str) -> dict[str, Integration]:
    return {
        domain: integration
        for domain, integration in INTEGRATIONS.items()
        if device_type in integration.device_types
    }


def known_integrations(device_type: str) -> str:
    """The names of the integrations with a profile for the Device Type."""
    return ", ".join(integration.name for integration in _serving(device_type).values())


def _finder(hass: HomeAssistant, device_id: str, config_entry: ConfigEntry) -> Find:
    """Finds the integration's entities of the HA device and the devices linked to it."""
    # A multi-material unit is its own HA device, linked to the printer's.
    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
        if device_id in (device.id, device.via_device_id)
    ]
    entities = er.async_get(hass)
    candidates = [
        entity
        for device in device_ids
        for entity in er.async_entries_for_device(
            entities, device, include_disabled_entities=True
        )
        if entity.platform == config_entry.domain
    ]

    def find(platform: str, *suffixes: str, disabled: bool = False) -> str | None:
        return next(
            (
                entity.entity_id
                for suffix in suffixes
                for entity in candidates
                if entity.domain == platform
                and entity.unique_id.endswith(suffix)
                and (disabled or not entity.disabled)
            ),
            None,
        )

    return find


def detect(
    hass: HomeAssistant, device_type: str, device_id: str | None
) -> dict[str, Any] | None:
    """The Device Input sections the HA device's profile fills in.

    None if the device belongs to no integration that serves the Device Type; what
    kind of device it is isn't asked. Inputs the profile can't find are left out of
    their section, and the mapping with the Status.
    """
    serving = _serving(device_type)
    ha_device = dr.async_get(hass).async_get(device_id) if device_id else None
    if ha_device is None:
        return None
    config_entry = next(
        (
            config_entry
            for entry_id in ha_device.config_entries
            if (config_entry := hass.config_entries.async_get_entry(entry_id))
            and config_entry.domain in serving
        ),
        None,
    )
    if config_entry is None:
        return None
    return serving[config_entry.domain].profile(
        _finder(hass, ha_device.id, config_entry)
    )


@dataclass(frozen=True)
class Candidate:
    """An HA device Quick Start can add: the Device Types it can be added as (one
    where its integration tells its kind, else those the integration serves), its
    integration's name and the sections its profile fills in."""

    device_types: tuple[str, ...]
    integration: str
    sections: dict[str, Any]


def candidates(hass: HomeAssistant) -> dict[str, Candidate]:
    """The HA devices Quick Start can add, by device id.

    Those are the devices a profile finds a Status for, so not a multi-material unit,
    and whose kind is a Device Type or can't be told.
    """
    devices = dr.async_get(hass)
    found: dict[str, Candidate] = {}
    for domain, integration in INTEGRATIONS.items():
        for config_entry in hass.config_entries.async_entries(
            domain, include_ignore=False, include_disabled=False
        ):
            for device in dr.async_entries_for_config_entry(
                devices, config_entry.entry_id
            ):
                find = _finder(hass, device.id, config_entry)
                sections = integration.profile(find)
                if not sections["status"]:
                    continue
                kind = integration.kind(find, device, config_entry)
                if kind is NoDeviceType.NOT_A_DEVICE:
                    continue
                device_types = (
                    integration.device_types
                    if kind is NoDeviceType.CANT_TELL
                    else (kind,)
                )
                found.setdefault(
                    device.id, Candidate(device_types, integration.name, sections)
                )
    return found
