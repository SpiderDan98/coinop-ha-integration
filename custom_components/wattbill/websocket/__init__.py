"""The panel's backend API: `wattbill/<area>/<verb>` websocket commands.

Each area module lists its handlers in `COMMANDS`, built with `command.command`.
"""

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import (
    catalog,
    devices,
    images,
    line_items,
    materials,
    runs,
    spoolman,
    tags,
    templates,
)
from .catalog import async_announce as async_announce_catalog
from .runs import async_announce

__all__ = ["async_announce", "async_announce_catalog", "async_setup"]


@callback
def async_setup(hass: HomeAssistant) -> None:
    for module in (
        runs,
        line_items,
        images,
        devices,
        materials,
        spoolman,
        catalog,
        tags,
        templates,
    ):
        for handler in module.COMMANDS:
            websocket_api.async_register_command(hass, handler)
