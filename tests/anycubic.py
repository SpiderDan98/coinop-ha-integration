"""Registry entries shaped like the two Anycubic integrations register a Kobra S1 + ACE Pro.

Unique ids, units and capabilities follow each integration's source; the ACE unit is
its own HA device linked to the printer with `via_device_id`.
"""

from typing import Any

from homeassistant.core import HomeAssistant

from .registry import HaDevice, add_ha_device, entity

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


def add_anycubic_local(
    hass: HomeAssistant,
    *,
    serial: str = "S1SERIAL",
    images: tuple[str, ...] = ("object_thumbnail", "object_top_view"),
) -> HaDevice:
    """chrisfore/anycubic_ha_local (domain `anycubic`); its image entities only exist
    after the printer's first job, so `images` may leave them out."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{serial}_{key}", **kwargs)

    def ace(key: str) -> tuple[str, dict[str, Any]]:
        return f"ace0_{key}", entity(
            "sensor",
            f"{serial}_ace0_{key}",
            object_id=f"ace_pro_{key}",
            linked=True,
        )

    return add_ha_device(
        hass,
        "anycubic",
        dict(
            [
                own(
                    "event",
                    "print_event",
                    capabilities={"event_types": LOCAL_EVENT_TYPES},
                ),
                own("sensor", "status"),
                own("sensor", "filename", object_id="anycubic_kobra_s1_file_name"),
                own("sensor", "filament_used", unit="g"),
                own("sensor", "pause_reason"),
                own("binary_sensor", "printing"),
                own("camera", "camera"),
                *(own("image", key) for key in images),
                *(ace(f"slot_{number}") for number in range(1, 5)),
                ace("loaded_slot"),
                ace("humidity"),
            ]
        ),
        identifiers={("anycubic", serial)},
        manufacturer="Anycubic",
        name="Anycubic Kobra S1",
        model="Anycubic Kobra S1",
        linked={
            "identifiers": {("anycubic", f"{serial}_ace0")},
            "manufacturer": "Anycubic",
            "name": "ACE Pro",
            "model": "ACE Pro",
        },
    )


def add_anycubic_cloud(
    hass: HomeAssistant,
    *,
    mac: str = "aa:bb:cc:dd:ee:ff",
    name: str = "Kobra S1",
    cloud: bool = True,
) -> HaDevice:
    """Nino6689/hass-anycubic (domain `anycubic_cloud`), 2.x and 3.0 alike: unique ids
    `<MAC>-<key>`. The job preview only exists with the cloud."""

    def add(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{mac}-{key}", **kwargs)

    def ace(key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return add("sensor", key, linked=True, **kwargs)

    return add_ha_device(
        hass,
        "anycubic_cloud",
        dict(
            [
                add("sensor", "job_state"),
                add("sensor", "job_name"),
                add("sensor", "job_filament_used", unit="mm"),
                add("sensor", "job_filament_required"),
                add("sensor", "job_energy", unit="kWh"),
                add("sensor", "job_electricity_cost"),
                add("sensor", "last_job_total_cost"),
                add("binary_sensor", "job_in_progress"),
                add("camera", "camera"),
                *(
                    [
                        add("image", "job_image_url", object_id=f"{name}_job_preview"),
                        add("camera", "cloud_camera"),
                    ]
                    if cloud
                    else []
                ),
                *(
                    entry
                    for number in range(1, 5)
                    for entry in (
                        ace(f"ace_slot_{number}"),
                        ace(f"ace_slot_{number}_filament_remaining", unit="g"),
                    )
                ),
                ace("ace_loaded_slot"),
                ace("secondary_ace_loaded_slot"),
            ]
        ),
        identifiers={("anycubic_cloud", "1234-5678")},
        manufacturer="Anycubic",
        name=name,
        model="Anycubic Kobra S1",
        linked={
            "identifiers": {("anycubic_cloud", "1234-5678-ace0")},
            "manufacturer": "Anycubic",
            "name": f"{name} ACE Pro",
            "model": "ACE Pro",
        },
    )
