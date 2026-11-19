"""The panel's backend API: `wattbill/<area>/<verb>` websocket commands.

Each area module lists its handlers in `COMMANDS`, built with `command.command`.
"""

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import catalog, devices, line_items, materials, runs, tags
from .catalog import async_announce as async_announce_catalog
from .runs import async_announce

__all__ = ["async_announce", "async_announce_catalog", "async_setup"]


@callback
def async_setup(hass: HomeAssistant) -> None:
    for module in (runs, line_items, devices, materials, catalog, tags):
        for handler in module.COMMANDS:
            websocket_api.async_register_command(hass, handler)
