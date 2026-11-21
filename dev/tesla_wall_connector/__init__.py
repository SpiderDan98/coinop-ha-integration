"""Dev container only: a stand-in for HA core's Tesla Wall Connector, whose status
and lifetime energy follow the Wall Connector's helpers from the dev
configuration.yaml. The status helper's options are the integration's own states."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..coinop_dev import stand_in
from ..coinop_dev.stand_in import async_unload_entry

FOLLOW = {
    "status": stand_in.following("input_select.wall_connector_status"),
    "energy_kWh": stand_in.following("input_number.wall_connector_energy"),
}

__all__ = ["async_setup_entry", "async_unload_entry"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await stand_in.async_setup_entry(hass, entry, lambda kind: FOLLOW)
