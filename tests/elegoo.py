"""Registry entries shaped like danielcherubini/elegoo-homeassistant (domain
`elegoo_printer`) registers a Centauri Carbon or a Saturn.

Unique ids `<machine id>_<key>`.
"""

from typing import Any

from homeassistant.core import HomeAssistant

from .registry import HaDevice, add_ha_device, entity

RESIN_STATUS_OPTIONS = [
    "idle",
    "homing",
    "dropping",
    "printing",
    "lifting",
    "pausing",
    "paused",
    "stopping",
    "stopped",
    "complete",
    "file_checking",
    "recovery",
    "printing_recovery",
    "loading",
    "preheating",
    "leveling",
]
FDM_STATUS_OPTIONS = [
    *RESIN_STATUS_OPTIONS,
    "printers_checking",
    "resuming",
    "error",
    "resonance_testing",
    "print_started",
    "auto_leveling_completed",
    "preheating_completed",
    "homing_completed",
    "resonance_testing_completed",
    "auto_feeding",
    "filament_unloading",
    "filament_unload_abnormal",
    "filament_unload_paused",
    "unrecognized",
]


def add_elegoo(
    hass: HomeAssistant,
    *,
    machine_id: str = "f25273b12b094c5a8b9513a30ca60049",
    resin: bool = False,
    cover_image: bool = True,
) -> HaDevice:
    """A Centauri Carbon (FDM, with OpenCentauri firmware), or with `resin` a Saturn,
    which has no extrusion sensor. Without `cover_image` the printer speaks the
    MQTT protocol, which has no cover image."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{machine_id}_{key}", **kwargs)

    options = RESIN_STATUS_OPTIONS if resin else FDM_STATUS_OPTIONS
    return add_ha_device(
        hass,
        "elegoo_printer",
        dict(
            [
                own("sensor", "print_status", capabilities={"options": options}),
                own("sensor", "current_status"),
                own("sensor", "filename"),
                own("sensor", "percent_complete", unit="%"),
                *(
                    []
                    if resin
                    else [
                        own("sensor", "current_extrusion", unit="mm"),
                        own("sensor", "total_extrusion", unit="mm"),
                    ]
                ),
                *([own("image", "cover_image")] if cover_image else []),
                own("camera", "chamber_camera"),
            ]
        ),
        identifiers={("elegoo_printer", machine_id)},
        manufacturer="Elegoo",
        name="Saturn 4 Ultra" if resin else "Centauri Carbon",
        model="Saturn 4 Ultra" if resin else "Centauri Carbon",
    )
