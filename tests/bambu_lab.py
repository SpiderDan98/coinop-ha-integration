"""Registry entries shaped like greghesp/ha-bambulab (domain `bambu_lab`) registers a
P1S with an AMS.

Unique ids `<serial>_<key>`; each AMS is its own HA device linked to the printer with
`via_device_id`, its unique ids `<model>_<serial>_AMS_<AMS serial>_<key>`.
"""

from typing import Any

from homeassistant.core import HomeAssistant

from .registry import HaDevice, add_ha_device, entity

PRINT_STATUS_OPTIONS = [
    "failed",
    "finish",
    "idle",
    "init",
    "offline",
    "pause",
    "prepare",
    "running",
    "slicing",
    "unknown",
]


def add_bambu_lab(
    hass: HomeAssistant, *, serial: str = "01P00A123456789", camera: bool = True
) -> HaDevice:
    """Without `camera` the printer has the option on that offers its chamber picture
    as an image entity instead of a camera."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{serial}_{key}", **kwargs)

    def ams(key: str) -> tuple[str, dict[str, Any]]:
        return f"ams_{key}", entity(
            "sensor",
            f"P1S_{serial}_AMS_006A123456_{key}",
            object_id=f"ams_1_{key}",
            linked=True,
        )

    return add_ha_device(
        hass,
        "bambu_lab",
        dict(
            [
                own(
                    "sensor",
                    "print_status",
                    capabilities={"options": PRINT_STATUS_OPTIONS},
                ),
                own("sensor", "subtask_name"),
                own("sensor", "print_weight", unit="g"),
                own("sensor", "print_length", unit="m"),
                own("sensor", "print_progress", unit="%"),
                own("sensor", "active_tray"),
                own("image", "cover_image"),
                own("image", "pick_image"),
                own("camera", "camera") if camera else own("image", "p1p_camera"),
                *(ams(f"tray_{number}") for number in range(1, 5)),
                ams("ams_status"),
                ams("humidity_index"),
            ]
        ),
        identifiers={("bambu_lab", serial)},
        manufacturer="Bambu Lab",
        name="P1S",
        model="P1S",
        linked={
            "identifiers": {("bambu_lab", "006A123456")},
            "manufacturer": "Bambu Lab",
            "name": "AMS 1",
            "model": "AMS",
        },
    )
