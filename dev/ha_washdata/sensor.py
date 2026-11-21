"""WashData's state and program sensors, read from the washing machine's helpers."""

from collections.abc import Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import DOMAIN

STATUS = "input_select.washer_status"
PROGRAM = "input_select.washer_program"
# The Status helper's words that WashData says differently.
STATES = {"cancelled": "interrupted"}


def _state(hass: HomeAssistant) -> str | None:
    status = hass.states.get(STATUS)
    return STATES.get(status.state, status.state) if status else None


def _program(hass: HomeAssistant) -> str | None:
    """WashData knows no program while the machine is off."""
    status, program = hass.states.get(STATUS), hass.states.get(PROGRAM)
    if status is None or program is None:
        return None
    return "off" if status.state == "off" else program.state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            HelperSensor(entry, "washer_state", "State", _state),
            HelperSensor(entry, "washer_program", "Program", _program),
        ]
    )


class HelperSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        key: str,
        name: str,
        read: Callable[[HomeAssistant], str | None],
    ) -> None:
        # WashData's unique ids, which the Integration Profile looks for.
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="WashData",
        )
        self._read = read

    async def async_added_to_hass(self) -> None:
        self._attr_native_value = self._read(self.hass)
        self.async_on_remove(
            async_track_state_change_event(self.hass, [STATUS, PROGRAM], self._changed)
        )

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        self._attr_native_value = self._read(self.hass)
        self.async_write_ha_state()
