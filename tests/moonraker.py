"""Registry entries shaped like marcolivierarsenault/moonraker-home-assistant (domain
`moonraker`) registers a Klipper printer.

Unique ids `<config entry id>_<key>`, all on one HA device. Its preview is the camera
`thumbnail`; a webcam is a camera `<entry id>_<webcam name>_<index>`.
"""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .registry import HaDevice, add_ha_device, entity

PRINT_STATE_OPTIONS = [
    "standby",
    "printing",
    "paused",
    "complete",
    "cancelled",
    "error",
]


def add_moonraker(hass: HomeAssistant, *, webcam: bool = True) -> HaDevice:
    entry = MockConfigEntry(domain="moonraker", title="Voron 2.4")
    entry.add_to_hass(hass)

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{entry.entry_id}_{key}", **kwargs)

    return add_ha_device(
        hass,
        entry,
        dict(
            [
                # The printer's own state, which a print's state is not.
                own(
                    "sensor",
                    "state",
                    capabilities={"options": ["ready", "startup", "shutdown", "error"]},
                ),
                own(
                    "sensor",
                    "print_state",
                    capabilities={"options": PRINT_STATE_OPTIONS},
                ),
                own("sensor", "filename"),
                # The printer's lifetime extrusion, which also ends in `_filament_used`.
                own("sensor", "total_filament_used", unit="m"),
                own("sensor", "filament_used", unit="m"),
                own("sensor", "progress", unit="%"),
                own("camera", "thumbnail"),
                *([own("camera", "Chamber_0")] if webcam else []),
            ]
        ),
        identifiers={("moonraker", entry.entry_id)},
        name="Voron 2.4",
        model="Klipper",
    )
