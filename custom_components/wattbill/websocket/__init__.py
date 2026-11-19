"""The panel's backend API: `wattbill/<area>/<verb>` websocket commands.

Each area module lists its handlers in `COMMANDS`, built with `command.command`.
"""

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import devices, runs
from .runs import async_announce

__all__ = ["async_announce", "async_setup"]


@callback
def async_setup(hass: HomeAssistant) -> None:
    for handler in (*runs.COMMANDS, *devices.COMMANDS):
        websocket_api.async_register_command(hass, handler)
