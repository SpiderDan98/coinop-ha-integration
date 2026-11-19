"""Per-Device total sensors, summed over every Run of the Device."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .device_config import DeviceConfig
from .models import Run
from .run_book import RunBook, RunChange
from .runtime import WattBillConfigEntry


def _cost(key: str, translation_key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=translation_key,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    )


# Each key names the `Totals` field the sensor shows.
TOTALS = (
    _cost("cost", "total_cost"),
    _cost("electricity_cost", "electricity_cost"),
    _cost("material_cost", "material_cost"),
    _cost("other_cost", "other_cost"),
    SensorEntityDescription(
        key="material_grams",
        translation_key="material_used",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="energy_kwh",
        translation_key="energy_in_runs",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)}, name=device.name
        )
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
