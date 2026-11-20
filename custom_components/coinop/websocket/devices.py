"""Devices for the Devices tab: HA-side settings (read-only) and panel settings.

Removed Devices are not listed; their Runs keep `device_id` and `device_name`.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.device_settings import (
    AUTOMATIC_TEMPLATES,
    DEFAULT_MATERIAL,
    TAGS_FOR_NEW_RUNS,
)
from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol

from .command import command, found
from .materials import pickable


@command({vol.Required("type"): "coinop/devices/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    connection.send_result(
        msg["id"],
        {
            "devices": [
                {
                    "id": device.device_id,
                    "name": device.name,
                    "type": device.device_type,
                    "ha_settings": {
                        key: value
                        for key, value in device.flow_data.items()
                        if key != "device_type"
                    },
                    "settings": coinop.settings.get(device.device_id),
                }
                for device in coinop.devices
            ]
        },
    )


@command(
    {
        vol.Required("type"): "coinop/devices/update_settings",
        vol.Required("device_id"): str,
        vol.Required("settings"): dict,
    }
)
async def _update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Change the named panel settings; returns all of the Device's panel settings.

    Naming a Tag that doesn't exist yet creates it; automatic templates must exist;
    the default Material must exist and not be archived.
    """
    device = msg["device_id"] if msg["device_id"] in coinop.settings else None
    if found(connection, msg, device, "Device") is None:
        return
    try:
        changes = coinop.settings.validate(msg["settings"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    if (material_id := changes.get(DEFAULT_MATERIAL)) is not None and not pickable(
        connection, msg, coinop, material_id
    ):
        return
    templates = changes.get(AUTOMATIC_TEMPLATES, [])
    complete = len(coinop.catalog.find_templates(templates)) == len(templates)
    if (
        found(connection, msg, templates if complete else None, "Line Item Template")
        is None
    ):
        return
    if TAGS_FOR_NEW_RUNS in changes:
        changes[TAGS_FOR_NEW_RUNS] = await coinop.catalog.async_add_tags(
            changes[TAGS_FOR_NEW_RUNS]
        )
    settings = await coinop.settings.async_update(msg["device_id"], changes)
    connection.send_result(msg["id"], {"settings": settings})


COMMANDS = (_list, _update_settings)
