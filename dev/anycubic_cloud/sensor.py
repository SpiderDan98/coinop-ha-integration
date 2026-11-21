"""hass-anycubic's job state and job name sensors, read from the Kobra's helpers.

The Status helper's options are hass-anycubic's own job states.
"""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            HelperSensor(entry, "job_state", "Job state", "input_select.kobra_status"),
            HelperSensor(entry, "job_name", "Job name", "input_text.kobra_job"),
        ]
    )


class HelperSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, key: str, name: str, helper: str) -> None:
        # hass-anycubic's unique ids, which the Integration Profile looks for.
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Anycubic",
            model="Anycubic Kobra S1",
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
