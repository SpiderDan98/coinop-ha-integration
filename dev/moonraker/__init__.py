"""Dev container only: a stand-in for Moonraker (marcolivierarsenault/moonraker-home-assistant).

Its device, sensors, preview camera and webcam are registered the way the integration
registers them, so Coin-op's Integration Profile finds them, and they follow the
Voron's helpers from the dev configuration.yaml.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "moonraker"
PLATFORMS = [Platform.CAMERA, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
