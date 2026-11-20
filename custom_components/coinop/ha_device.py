"""Coin-op's own HA device per Device, which carries the Device's entities."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .device_config import DeviceConfig


def device_info(device: DeviceConfig) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, device.device_id)}, name=device.name)


@callback
def async_register(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceConfig
) -> None:
    """Create the HA device before its entities, linked to the printer's HA device."""
    registry = dr.async_get(hass)
    ha_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        config_subentry_id=device.device_id,
        identifiers={(DOMAIN, device.device_id)},
        name=device.name,
    )
    printer = device.printer_device_id
    # Set by id: the minimum HA version has no `via_device_id` in DeviceInfo.
    registry.async_update_device(
        ha_device.id,
        via_device_id=printer if printer and registry.async_get(printer) else None,
    )


@callback
def async_track_renames(hass: HomeAssistant, entry: ConfigEntry) -> CALLBACK_TYPE:
    """A name given on the HA device page becomes the Device's name."""

    @callback
    def renamed(event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        if (
            event.data["action"] != "update"
            or "name_by_user" not in event.data["changes"]
        ):
            return
        ha_device = dr.async_get(hass).async_get(event.data["device_id"])
        if ha_device is None or not ha_device.name_by_user:
            return
        for subentry in entry.subentries.values():
            if (DOMAIN, subentry.subentry_id) in ha_device.identifiers:
                hass.config_entries.async_update_subentry(
                    entry, subentry, title=ha_device.name_by_user
                )

    return hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, renamed)
