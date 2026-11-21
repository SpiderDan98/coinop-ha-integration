"""Dev container only: a stand-in for Moonraker (marcolivierarsenault/moonraker-home-assistant).

Its print state, file name and filament used follow the Voron's helpers from the dev
configuration.yaml; the print state helper's options are Klipper's own print states.
Its cameras are entity objects of its own (`camera.py`).
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from ..coinop_dev import stand_in

FOLLOW = {
    "print_state": stand_in.following("input_select.voron_status"),
    "filename": stand_in.following("input_text.voron_job"),
    "filament_used": stand_in.following("input_number.voron_filament"),
}
PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await stand_in.async_setup_entry(hass, entry, lambda kind: FOLLOW, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await stand_in.async_unload_entry(hass, entry, PLATFORMS)
