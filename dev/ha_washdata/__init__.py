"""Dev container only: a stand-in for WashData (3dg1luk43/ha_washdata).

Each config entry is one device, as in WashData: its two sensors are registered
the way WashData registers them, so Coin-op's Integration Profile finds them, and
the entry's data keeps the kind picked for it, which tells Coin-op its Device Type.
The sensors follow the helpers of that kind from the dev configuration.yaml.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "ha_washdata"
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
