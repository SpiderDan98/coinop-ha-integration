"""Registry entries shaped like 3dg1luk43/ha_creality_ws (domain `ha_creality_ws`)
registers a K1C.

Unique ids `<host>-<key>`; the job's file is the `file` attribute of the print status.
"""

from typing import Any

from homeassistant.core import HomeAssistant

from .registry import HaDevice, add_ha_device, entity

PRINT_STATUS_OPTIONS = [
    "off",
    "error",
    "self-testing",
    "completed",
    "paused",
    "stopped",
    "printing",
    "processing",
    "idle",
]


def add_creality(
    hass: HomeAssistant, *, host: str = "192.168.1.50", camera: bool = True
) -> HaDevice:
    """Without `camera` the camera is set up in custom mode without a URL."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{host}-{key}", **kwargs)

    return add_ha_device(
        hass,
        "ha_creality_ws",
        dict(
            [
                own(
                    "sensor",
                    "print_status",
                    capabilities={"options": PRINT_STATUS_OPTIONS},
                ),
                own("sensor", "used_material_length", unit="cm"),
                own("sensor", "expected_material_length", unit="cm"),
                own("sensor", "filament_consumption", unit="g"),
                own("sensor", "print_job_time", unit="s"),
                own("image", "current_print_preview"),
                *([own("camera", "camera")] if camera else []),
            ]
        ),
        identifiers={("ha_creality_ws", host)},
        manufacturer="Creality",
        name="K1C",
        model="K1C",
    )
