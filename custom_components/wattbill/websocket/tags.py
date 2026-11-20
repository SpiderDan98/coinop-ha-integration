"""The Tags tab: create a Tag, rename (or merge) and delete one on every Run and Device.

Naming a Tag on a Run or Device creates it too; the catalogue reaches open panels
through the catalogue subscription (`catalog.py`).
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.tags import tag_name

from .command import command, found


def _found(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> str | None:
    return found(connection, msg, wattbill.catalog.tag(msg["tag"]), "Tag", "name")


@command({vol.Required("type"): "wattbill/tags/create", vol.Required("name"): tag_name})
async def _create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """A name another Tag has, ignoring case, is that Tag; returns the resulting Tag."""
    [tag] = await wattbill.catalog.async_add_tags([msg["name"]])
    connection.send_result(msg["id"], {"tag": tag})


@command(
    {
        vol.Required("type"): "wattbill/tags/rename",
        vol.Required("tag"): str,
        vol.Required("name"): tag_name,
    }
)
async def _rename(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Renaming to another Tag's name merges both; returns the resulting Tag."""
    if (tag := _found(connection, msg, wattbill)) is None:
        return
    new = await wattbill.catalog.async_rename_tag(tag, msg["name"])
    await wattbill.book.async_retag(tag, new)
    await wattbill.settings.async_retag(tag, new)
    connection.send_result(msg["id"], {"tag": new})


@command({vol.Required("type"): "wattbill/tags/delete", vol.Required("tag"): str})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (tag := _found(connection, msg, wattbill)) is None:
        return
    await wattbill.catalog.async_delete_tag(tag)
    await wattbill.book.async_retag(tag, None)
    await wattbill.settings.async_retag(tag, None)
    connection.send_result(msg["id"], {})


COMMANDS = (_create, _rename, _delete)
