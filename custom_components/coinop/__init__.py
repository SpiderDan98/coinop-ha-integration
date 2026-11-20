"""Coin-op: records what each Run of a Device costs."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import ha_device, panel, websocket
from .catalog import Catalog
from .const import DEVICE_TYPE_3D_PRINTER, DOMAIN, SUBENTRY_DEVICE
from .device_config import DeviceConfig
from .device_settings import DeviceSettings
from .images import DeviceImages, ImageLibrary, RunImageView, RunUploadView
from .run_book import RunBook
from .runtime import CoinOp, CoinOpConfigEntry
from .spoolman import CONF_SPOOLMAN_URL, Spoolman
from .statement import CONF_MARKUP, CostStatements, CostStatementView
from .store import CoinOpStores, RunStore
from .tracker import DeviceTracker

PLATFORMS = [Platform.EVENT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket.async_setup(hass)
    hass.http.register_view(RunImageView())
    hass.http.register_view(RunUploadView())
    hass.http.register_view(CostStatementView())
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: CoinOpConfigEntry) -> bool:
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        for subentry in entry.subentries.values():
            if subentry.subentry_type == SUBENTRY_DEVICE:
                hass.config_entries.async_update_subentry(
                    entry,
                    subentry,
                    data={**subentry.data, "device_type": DEVICE_TYPE_3D_PRINTER},
                )
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CoinOpConfigEntry) -> bool:
    stores = CoinOpStores(hass)
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
    settings = stores.parse(
        data,
        "device_settings",
        lambda stored: DeviceSettings(
            stores["device_settings"],
            stored,
            (device.device_id for device in devices),
        ),
    )
    await settings.async_prune()
    catalog = stores.parse(
        data,
        "catalog",
        lambda stored: Catalog(stores["catalog"], stored, book.uses_material),
    )
    spoolman = Spoolman(hass, entry.options.get(CONF_SPOOLMAN_URL), catalog)
    entry.runtime_data = CoinOp(
        book=book,
        catalog=catalog,
        images=images,
        devices=devices,
        settings=settings,
        spoolman=spoolman,
        trackers=[
            DeviceTracker(
                hass,
                book,
                device,
                settings,
                DeviceImages(hass, book, images, device),
                catalog,
                spoolman,
            )
            for device in devices
        ],
        statements=CostStatements(markup=entry.options.get(CONF_MARKUP, 0.0)),
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


async def async_unload_entry(hass: HomeAssistant, entry: CoinOpConfigEntry) -> bool:
    entry.runtime_data.images.async_close()
    for tracker in entry.runtime_data.trackers:
        tracker.async_stop()
    await entry.runtime_data.book.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: CoinOpConfigEntry) -> None:
    await CoinOpStores(hass).async_remove()


async def _async_reload(hass: HomeAssistant, entry: CoinOpConfigEntry) -> None:
    runtime = entry.runtime_data
    for device, tracker in zip(runtime.devices, runtime.trackers, strict=True):
        if device.device_id not in entry.subentries:
            await tracker.async_remove()
    await hass.config_entries.async_reload(entry.entry_id)
