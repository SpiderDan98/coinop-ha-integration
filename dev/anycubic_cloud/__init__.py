"""Dev container only: a stand-in for Anycubic Cloud & LAN (Nino6689/hass-anycubic).

Its device and two sensors are registered the way hass-anycubic registers them, so
Coin-op's Integration Profile finds them, and they follow the Kobra's helpers from
the dev configuration.yaml.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "anycubic_cloud"
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
