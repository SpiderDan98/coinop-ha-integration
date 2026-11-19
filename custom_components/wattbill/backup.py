"""Backup platform: pending delayed saves are written before a backup."""

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .runtime import WattBillConfigEntry


async def async_pre_backup(hass: HomeAssistant) -> None:
    entry: WattBillConfigEntry
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        await entry.runtime_data.book.async_flush()


async def async_post_backup(hass: HomeAssistant) -> None:
    """Nothing to resume: WattBill keeps running during a backup."""
