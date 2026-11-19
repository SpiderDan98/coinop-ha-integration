"""WattBill's own HA device per Device, which carries the Device's entities."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
