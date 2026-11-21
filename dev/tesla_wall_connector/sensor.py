"""The Wall Connector's status and lifetime energy sensors, read from its helpers.

The status helper's options are the integration's own states.
"""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import DOMAIN

SERIAL = "PGT21234567890"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            HelperSensor("status", "Status", "input_select.wall_connector_status"),
            EnergySensor("energy_kWh", "Energy", "input_number.wall_connector_energy"),
        ]
    )


class HelperSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, key: str, name: str, helper: str) -> None:
        # The integration's unique ids, which the Integration Profile looks for.
        self._attr_unique_id = f"{SERIAL}-{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, SERIAL)},
            name="Tesla Wall Connector",
            manufacturer="Tesla",
            model="Wall Connector",
        )
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


class EnergySensor(HelperSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
