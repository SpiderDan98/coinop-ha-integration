"""Spoolman for the Materials tab: its Filaments.

Reading them also brings linked Materials up to date, so opening the tab
refreshes their prices. Linking a Material is `materials/update` with a Spoolman
price; `materials/create_from_spoolman` creates one from a Filament.
"""

from collections.abc import Awaitable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol
from custom_components.coinop.spoolman import SpoolmanUnreachable

from .command import command, found

ERR_SPOOLMAN_UNREACHABLE = "spoolman_unreachable"


async def spoolman_call[T](
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    call: Awaitable[T | None],
) -> T | None:
    """The call's result; None (after answering the error) if Spoolman or the Filament is missing."""
    try:
        result = await call
    except SpoolmanUnreachable:
        connection.send_error(
            msg["id"], ERR_SPOOLMAN_UNREACHABLE, "Spoolman can't be reached"
        )
        return None
    return found(connection, msg, result, "Spoolman Filament")


@command({vol.Required("type"): "coinop/spoolman/filaments"})
async def _filaments(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """`status` is "ok", "unreachable" or "not_configured" (no URL in the options)."""
    if coinop.spoolman.url is None:
        connection.send_result(msg["id"], {"status": "not_configured", "filaments": []})
        return
    try:
        filaments = await coinop.spoolman.async_filaments()
    except SpoolmanUnreachable:
        connection.send_result(msg["id"], {"status": "unreachable", "filaments": []})
        return
    connection.send_result(
        msg["id"],
        {"status": "ok", "filaments": [filament.as_dict() for filament in filaments]},
    )


COMMANDS = (_filaments,)
