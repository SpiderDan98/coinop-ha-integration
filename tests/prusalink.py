"""Registry entries shaped like Home Assistant's PrusaLink (domain `prusalink`) registers
an MK4.

Unique ids `<config entry id>_<key>`; the HA device is the config entry's, named after
its title.
"""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .registry import HaDevice, add_ha_device, entity

PRINTER_STATE_OPTIONS = [
    "idle",
    "busy",
    "printing",
    "paused",
    "finished",
    "stopped",
    "error",
    "attention",
    "ready",
]


def add_prusalink(hass: HomeAssistant, *, title: str = "Prusa MK4") -> HaDevice:
    config_entry = MockConfigEntry(domain="prusalink", title=title)
    config_entry.add_to_hass(hass)

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return key, entity(platform, f"{config_entry.entry_id}_{key}", **kwargs)

    return add_ha_device(
        hass,
        config_entry,
        dict(
            [
                # Named after the HA device itself.
                own(
                    "sensor",
                    "printer.state",
                    capabilities={"options": PRINTER_STATE_OPTIONS},
                    object_id=title,
                ),
                own("sensor", "job.filename"),
                own("sensor", "job.progress", unit="%"),
                # The filament type, not an amount.
                own("sensor", "printer.telemetry.material"),
                own(
                    "sensor", "printer.telemetry.temp-nozzle", unit="°C", disabled=True
                ),
                own("camera", "job_preview"),
                own("button", "job.cancel"),
            ]
        ),
        identifiers={("prusalink", config_entry.entry_id)},
        manufacturer="Prusa",
        name=title,
    )
