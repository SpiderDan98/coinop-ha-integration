"""WashData's state and program sensors, read from the helpers of the entry's device."""

from collections.abc import Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import DOMAIN

# The helpers' prefix in the dev configuration.yaml, by WashData's device type.
HELPERS = {
    "washing_machine": "washer",
    "dishwasher": "dishwasher",
    "dryer": "washdata_dryer",
}
# The Status helper's words that WashData says differently.
STATES = {"cancelled": "interrupted"}


def _state(hass: HomeAssistant, status: str) -> str | None:
    state = hass.states.get(status)
    return STATES.get(state.state, state.state) if state else None


def _program(hass: HomeAssistant, status: str, program: str) -> str | None:
    """WashData knows no program while the device is off."""
    state, running = hass.states.get(status), hass.states.get(program)
    if state is None or running is None:
        return None
    return "off" if state.state == "off" else running.state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            HelperSensor(entry, "washer_state", "State", _state, "status"),
            HelperSensor(
                entry, "washer_program", "Program", _program, "status", "program"
            ),
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
        read: Callable[..., str | None],
        *helpers: str,
    ) -> None:
        # WashData's unique ids, which the Integration Profile looks for.
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="WashData",
        )
        prefix = HELPERS[entry.data["device_type"]]
        self._helpers = [f"input_select.{prefix}_{helper}" for helper in helpers]
        self._read = read

    async def async_added_to_hass(self) -> None:
        self._attr_native_value = self._read(self.hass, *self._helpers)
        self.async_on_remove(
            async_track_state_change_event(self.hass, self._helpers, self._changed)
        )

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        self._attr_native_value = self._read(self.hass, *self._helpers)
        self.async_write_ha_state()
