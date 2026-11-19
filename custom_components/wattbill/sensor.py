"""Per-Device total sensors, summed over every Run of the Device."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device_config import DeviceConfig
from .ha_device import device_info
from .models import Run
from .run_book import RunBook, RunChange
from .runtime import WattBillConfigEntry

# Each key names the `Totals` field the sensor shows.
TOTALS = (
    SensorEntityDescription(
        key="cost",
        translation_key="total_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="runs", translation_key="runs", state_class=SensorStateClass.TOTAL
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattBillConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    book = entry.runtime_data.book
    for device in entry.runtime_data.devices:
        async_add_entities(
            [TotalSensor(hass, book, device, description) for description in TOTALS],
            config_subentry_id=device.device_id,
        )


class TotalSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        book: RunBook,
        device: DeviceConfig,
        description: SensorEntityDescription,
    ) -> None:
        self.entity_description = description
        self._book = book
        self._device_id = device.device_id
        self._attr_unique_id = f"{device.device_id}_{description.key}"
        self._attr_device_info = device_info(device)
        if description.device_class is SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = hass.config.currency

    @property
    def native_value(self) -> float:
        value: float = getattr(
            self._book.totals(self._device_id), self.entity_description.key
        )
        return value

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._book.async_listen(self._on_run_change))

    @callback
    def _on_run_change(self, change: RunChange, run: Run) -> None:
        if run.device_id == self._device_id:
            self.async_write_ha_state()
