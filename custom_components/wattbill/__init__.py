"""WattBill: records what each Run of a Device costs."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import ha_device, panel, websocket
from .catalog import Catalog
from .const import DOMAIN, SUBENTRY_DEVICE
from .device_config import DeviceConfig
from .device_settings import DeviceSettings
from .images import DeviceImages, ImageLibrary, RunImageView
from .run_book import RunBook
from .runtime import WattBill, WattBillConfigEntry
from .store import RunStore, WattBillStores
from .tracker import DeviceTracker

PLATFORMS = [Platform.EVENT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket.async_setup(hass)
    hass.http.register_view(RunImageView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> bool:
    stores = WattBillStores(hass)
    data = await stores.async_load(entry)
    store = RunStore(stores)
    book = RunBook(store, store.runs(data))
    images = ImageLibrary(hass, book)
    await images.async_remove_orphans()
    devices = [
        DeviceConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_DEVICE
    ]
    settings = DeviceSettings(
        stores["device_settings"],
        data["device_settings"],
        (device.device_id for device in devices),
    )
    await settings.async_prune()
    entry.runtime_data = WattBill(
        book=book,
        catalog=Catalog(stores["catalog"], data["catalog"], book.uses_material),
        images=images,
        devices=devices,
        settings=settings,
        trackers=[
            DeviceTracker(
                hass,
                book,
                device,
                settings,
                DeviceImages(hass, book, images, device),
            )
            for device in devices
        ],
    )
    entry.async_on_unload(images.async_follow_deletions())
    for device in devices:
        ha_device.async_register(hass, entry, device)
        await book.async_rename_device(device.device_id, device.name)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(websocket.async_announce(hass, book))
    entry.async_on_unload(
        websocket.async_announce_catalog(hass, entry.runtime_data.catalog)
    )
    await panel.async_register(hass, entry)
    for tracker in entry.runtime_data.trackers:
        await tracker.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(ha_device.async_track_renames(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> bool:
    entry.runtime_data.images.async_close()
    for tracker in entry.runtime_data.trackers:
        tracker.async_stop()
    await entry.runtime_data.book.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: WattBillConfigEntry) -> None:
    await WattBillStores(hass).async_remove()


async def _async_reload(hass: HomeAssistant, entry: WattBillConfigEntry) -> None:
    runtime = entry.runtime_data
    for device, tracker in zip(runtime.devices, runtime.trackers, strict=True):
        if device.device_id not in entry.subentries:
            await tracker.async_end_run()
    await hass.config_entries.async_reload(entry.entry_id)
