"""Devices for the Devices tab: HA-side settings (read-only) and panel settings.

Removed Devices are not listed; their Runs keep `device_id` and `device_name`.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.device_settings import TAGS_FOR_NEW_RUNS
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol

from .command import command


@command({vol.Required("type"): "wattbill/devices/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    connection.send_result(
        msg["id"],
        {
            "devices": [
                {
                    "id": device.device_id,
                    "name": device.name,
                    "ha_settings": dict(device.flow_data),
                    "settings": wattbill.settings.get(device.device_id),
                }
                for device in wattbill.devices
            ]
        },
    )


@command(
    {
        vol.Required("type"): "wattbill/devices/update_settings",
        vol.Required("device_id"): str,
        vol.Required("settings"): dict,
    }
)
async def _update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Change the named panel settings; returns all of the Device's panel settings.

    Naming a Tag that doesn't exist yet creates it.
    """
    if msg["device_id"] not in wattbill.settings:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Device with this id"
        )
        return
    try:
        changes = wattbill.settings.validate(msg["settings"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    if TAGS_FOR_NEW_RUNS in changes:
        changes[TAGS_FOR_NEW_RUNS] = await wattbill.catalog.async_add_tags(
            changes[TAGS_FOR_NEW_RUNS]
        )
    settings = await wattbill.settings.async_update(msg["device_id"], changes)
    connection.send_result(msg["id"], {"settings": settings})


COMMANDS = (_list, _update_settings)
