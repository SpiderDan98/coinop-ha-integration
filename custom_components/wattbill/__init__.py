"""WattBill: records what each Run of a Device costs."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import panel
from .const import SUBENTRY_DEVICE
from .device_config import DeviceConfig
from .run_book import RunBook
from .runtime import WattBill, WattBillConfigEntry
from .store import RunStore
from .tracker import DeviceTracker

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> bool:
    store = RunStore(hass)
    book = RunBook(store, await store.async_load())
    devices = [
        DeviceConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_DEVICE
    ]
    entry.runtime_data = WattBill(
        book=book,
        devices=devices,
        trackers=[DeviceTracker(hass, book, device) for device in devices],
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await panel.async_register(hass, entry)
    for tracker in entry.runtime_data.trackers:
        tracker.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> bool:
    for tracker in entry.runtime_data.trackers:
        tracker.async_stop()
    await entry.runtime_data.book.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: WattBillConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
