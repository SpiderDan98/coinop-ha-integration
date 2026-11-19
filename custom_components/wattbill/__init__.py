"""WattBill: records what each Run of a Device costs."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import ha_device
from .const import SUBENTRY_DEVICE
from .device_config import DeviceConfig
from .run_book import RunBook
from .runtime import WattBill, WattBillConfigEntry
from .store import RunStore
from .tracker import DeviceTracker

PLATFORMS = [Platform.EVENT, Platform.SENSOR]


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
    for device in devices:
        ha_device.async_register(hass, entry, device)
        await book.async_rename_device(device.device_id, device.name)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for tracker in entry.runtime_data.trackers:
        tracker.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(ha_device.async_track_renames(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> bool:
    for tracker in entry.runtime_data.trackers:
        tracker.async_stop()
    await entry.runtime_data.book.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: WattBillConfigEntry) -> None:
    runtime = entry.runtime_data
    for device, tracker in zip(runtime.devices, runtime.trackers, strict=True):
        if device.device_id not in entry.subentries:
            await tracker.async_end_run()
    await hass.config_entries.async_reload(entry.entry_id)
