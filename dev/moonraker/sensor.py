"""Moonraker's print state, file name and filament sensors, read from the Voron's helpers.

The print state helper's options are Klipper's own print states.
"""

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import DOMAIN


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, model="Klipper"
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            HelperSensor(
                entry, "print_state", "Print state", "input_select.voron_status"
            ),
            HelperSensor(entry, "filename", "Filename", "input_text.voron_job"),
            FilamentSensor(
                entry, "filament_used", "Filament used", "input_number.voron_filament"
            ),
            TotalFilamentSensor(entry),
        ]
    )


class HelperSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, key: str, name: str, helper: str) -> None:
        # Moonraker's unique ids, which the Integration Profile looks for.
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = device_info(entry)
        self._helper = helper

    async def async_added_to_hass(self) -> None:
        self._read()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._helper], self._changed)
        )

    def _read(self) -> None:
        state = self.hass.states.get(self._helper)
        self._attr_native_value = state.state if state else None

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        self._read()
        self.async_write_ha_state()


class FilamentSensor(HelperSensor):
    _attr_native_unit_of_measurement = UnitOfLength.METERS


class TotalFilamentSensor(SensorEntity):
    """The lifetime total, whose unique id also ends in `_filament_used`."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Total filament used"
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_value = 1523.7

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_total_filament_used"
        self._attr_device_info = device_info(entry)
