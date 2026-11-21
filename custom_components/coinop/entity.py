"""Base for per-Device entities: one HA device per Device, refreshed on its Run changes."""

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .device_config import DeviceConfig
from .ha_device import device_info
from .models import Run
from .run_book import RunBook, RunChange


def unique_id(device_id: str, key: str) -> str:
    return f"{device_id}_{key}"


class DeviceEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, book: RunBook, device: DeviceConfig, key: str) -> None:
        self._book = book
        self._device_id = device.device_id
        self._capabilities = device.capabilities
        self._attr_unique_id = unique_id(device.device_id, key)
        self._attr_device_info = device_info(device)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._book.async_listen(self._on_book_change))

    @callback
    def _on_book_change(self, change: RunChange, run: Run) -> None:
        if run.device_id == self._device_id:
            self._on_run_change(change, run)

    @callback
    def _on_run_change(self, change: RunChange, run: Run) -> None:
        """Any change to one of the Device's Runs, whatever kind: state is re-read."""
        self.async_write_ha_state()
