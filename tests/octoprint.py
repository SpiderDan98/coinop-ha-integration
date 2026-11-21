"""Registry entries shaped like Home Assistant's `octoprint` integration registers a
printer with its webcam enabled.

Unique ids `<Name>-<device id>`, the device id being the config entry's unique id;
the camera's unique id is the device id alone.
"""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .registry import HaDevice, add_ha_device, entity

DEVICE_ID = "6f2c5b1e-8a0d-4c3b-9e7f-1a2b3c4d5e6f"

CURRENT_STATE_OPTIONS = [
    "open_serial",
    "detect_serial",
    "connecting",
    "operational",
    "starting_sd",
    "starting_streaming",
    "starting",
    "printing_sd",
    "printing_streaming",
    "printing",
    "cancelling",
    "pausing",
    "paused",
    "resuming",
    "finishing",
    "offline",
    "error",
    "offline_after_error",
    "transferring_file",
]


def add_octoprint(hass: HomeAssistant, *, camera: bool = True) -> HaDevice:
    """Without `camera` the webcam is turned off in OctoPrint."""
    config_entry = MockConfigEntry(domain="octoprint", unique_id=DEVICE_ID)
    config_entry.add_to_hass(hass)

    def own(platform: str, name: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return name, entity(platform, f"{name}-{DEVICE_ID}", **kwargs)

    entities = dict(
        [
            # Before `Current File`, so a match on that name alone would take it.
            own("sensor", "Current File Size", unit="MB"),
            own(
                "sensor",
                "Current State",
                capabilities={"options": CURRENT_STATE_OPTIONS},
            ),
            own("sensor", "Current File"),
            own("sensor", "Job Percentage", unit="%"),
            own("sensor", "Estimated Finish Time"),
            own("sensor", "Start Time"),
            own("sensor", "actual tool0 temp", unit="°C"),
            own("binary_sensor", "Printing"),
            own("binary_sensor", "Printing Error"),
        ]
    )
    if camera:
        entities["camera"] = entity("camera", DEVICE_ID, object_id="octoprint_camera")
    return add_ha_device(
        hass,
        config_entry,
        entities,
        identifiers={("octoprint", DEVICE_ID)},
        manufacturer="OctoPrint",
        name="OctoPrint",
    )
