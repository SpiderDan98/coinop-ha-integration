"""Registry entries shaped like the two Anycubic integrations register a Kobra S1 + ACE Pro.

Unique ids, translation keys, units and capabilities follow each integration's source;
the ACE unit is its own HA device linked to the printer with `via_device_id`.
"""

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

LOCAL_EVENT_TYPES = [
    "started",
    "paused",
    "resumed",
    "finished",
    "stopped",
    "error",
    "clear_ready",
    "clear_done",
    "clear_failed",
]


@dataclass
class Printer:
    device: dr.DeviceEntry
    ace: dr.DeviceEntry
    # Entity ids by the integration's entity key.
    entities: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def _add(
    hass: HomeAssistant,
    printer: Printer,
    config_entry: MockConfigEntry,
    platform: str,
    key: str,
    unique_id: str,
    object_id: str,
    *,
    ace: bool = False,
    **kwargs: Any,
) -> None:
    entry = er.async_get(hass).async_get_or_create(
        platform,
        config_entry.domain,
        unique_id,
        config_entry=config_entry,
        device_id=(printer.ace if ace else printer.device).id,
        suggested_object_id=object_id,
        **kwargs,
    )
    printer.entities[key] = entry.entity_id


def add_anycubic_local(
    hass: HomeAssistant,
    *,
    serial: str = "S1SERIAL",
    images: tuple[str, ...] = ("object_thumbnail", "object_top_view"),
) -> Printer:
    """chrisfore/anycubic_ha_local (domain `anycubic`); its image entities only exist
    after the printer's first job, so `images` may leave them out."""
    config_entry = MockConfigEntry(domain="anycubic")
    config_entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("anycubic", serial)},
        manufacturer="Anycubic",
        name="Anycubic Kobra S1",
        model="Anycubic Kobra S1",
    )
    ace = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("anycubic", f"{serial}_ace0")},
        manufacturer="Anycubic",
        name="ACE Pro",
        model="ACE Pro",
        via_device_id=device.id,
    )
    printer = Printer(device, ace)

    def add(platform: str, key: str, object_id: str, **kwargs: Any) -> None:
        _add(
            hass,
            printer,
            config_entry,
            platform,
            key,
            f"{serial}_{key}",
            f"anycubic_kobra_s1_{object_id}",
            translation_key=key,
            **kwargs,
        )

    def add_ace(key: str, object_id: str, translation_key: str) -> None:
        _add(
            hass,
            printer,
            config_entry,
            "sensor",
            f"ace0_{key}",
            f"{serial}_ace0_{key}",
            f"ace_pro_{object_id}",
            ace=True,
            translation_key=translation_key,
        )

    add(
        "event",
        "print_event",
        "print_event",
        capabilities={"event_types": LOCAL_EVENT_TYPES},
    )
    add("sensor", "status", "status")
    add("sensor", "filename", "file_name")
    add("sensor", "filament_used", "filament_used", unit_of_measurement="g")
    add("sensor", "pause_reason", "pause_reason")
    add("binary_sensor", "printing", "printing")
    add("camera", "camera", "camera")
    for key in images:
        add("image", key, key)
    for number in range(1, 5):
        add_ace(f"slot_{number}", f"slot_{number}", "ace_slot")
    add_ace("loaded_slot", "loaded_slot", "ace_loaded_slot")
    add_ace("humidity", "humidity", "ace_humidity")
    return printer


def add_anycubic_cloud(
    hass: HomeAssistant,
    *,
    mac: str = "aa:bb:cc:dd:ee:ff",
    name: str = "Kobra S1",
    cloud: bool = True,
) -> Printer:
    """Nino6689/hass-anycubic (domain `anycubic_cloud`), 2.x and 3.0 alike: unique ids
    `<MAC>-<key>`, translation key = key. The job preview only exists with the cloud."""
    config_entry = MockConfigEntry(domain="anycubic_cloud")
    config_entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("anycubic_cloud", "1234-5678")},
        manufacturer="Anycubic",
        name=name,
        model="Anycubic Kobra S1",
    )
    ace = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("anycubic_cloud", "1234-5678-ace0")},
        manufacturer="Anycubic",
        name=f"{name} ACE Pro",
        model="ACE Pro",
        via_device_id=device.id,
    )
    printer = Printer(device, ace)
    prefix = name.lower().replace(" ", "_")

    def add(
        platform: str, key: str, object_id: str, *, ace: bool = False, **kwargs: Any
    ) -> None:
        _add(
            hass,
            printer,
            config_entry,
            platform,
            key,
            f"{mac}-{key}",
            f"{prefix}_ace_pro_{object_id}" if ace else f"{prefix}_{object_id}",
            ace=ace,
            translation_key=key,
            **kwargs,
        )

    add("sensor", "job_state", "job_state")
    add("sensor", "job_name", "job_name")
    add("sensor", "job_filament_used", "job_filament_used", unit_of_measurement="mm")
    add("sensor", "job_filament_required", "job_filament_required")
    add("sensor", "job_energy", "job_energy", unit_of_measurement="kWh")
    add("sensor", "job_electricity_cost", "job_electricity_cost")
    add("sensor", "last_job_total_cost", "last_job_total_cost")
    add("binary_sensor", "job_in_progress", "job_in_progress")
    add("camera", "camera", "camera")
    if cloud:
        add("image", "job_image_url", "job_preview")
        add("camera", "cloud_camera", "cloud_camera")
    for number in range(1, 5):
        add("sensor", f"ace_slot_{number}", f"ace_slot_{number}", ace=True)
        add(
            "sensor",
            f"ace_slot_{number}_filament_remaining",
            f"ace_slot_{number}_filament_remaining",
            ace=True,
            unit_of_measurement="g",
        )
    add("sensor", "ace_loaded_slot", "ace_loaded_slot", ace=True)
    add("sensor", "secondary_ace_loaded_slot", "secondary_ace_loaded_slot", ace=True)
    return printer
