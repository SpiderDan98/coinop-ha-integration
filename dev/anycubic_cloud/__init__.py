"""Dev container only: a stand-in for Anycubic Cloud & LAN (Nino6689/hass-anycubic),
whose job state and job name follow the Kobra's helpers from the dev
configuration.yaml. The Status helper's options are hass-anycubic's own job states."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..coinop_dev import stand_in
from ..coinop_dev.stand_in import async_unload_entry

FOLLOW = {
    "job_state": stand_in.following("input_select.kobra_status"),
    "job_name": stand_in.following("input_text.kobra_job"),
}

__all__ = ["async_setup_entry", "async_unload_entry"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await stand_in.async_setup_entry(hass, entry, lambda kind: FOLLOW)
