"""`command(...)`: the decorator every WattBill websocket command is built with."""

from collections.abc import Awaitable, Callable
import functools
import inspect
from typing import Any, cast

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.const import DOMAIN
from custom_components.wattbill.runtime import WattBill, WattBillConfigEntry

type Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], WattBill],
    Awaitable[None] | None,
]


def found[T](
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    value: T | None,
    thing: str,
    by: str = "id",
) -> T | None:
    """`value`; when it is None, the command answers `not_found` for `thing`."""
    if value is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, f"No {thing} with this {by}"
        )
    return value


def command(
    schema: dict[Any, Any],
) -> Callable[[Handler], websocket_api.const.WebSocketCommandHandler]:
    """Admin-only command whose handler (sync or async) gets the loaded WattBill."""

    def decorate(handler: Handler) -> websocket_api.const.WebSocketCommandHandler:
        @functools.wraps(handler)
        async def run(
            hass: HomeAssistant,
            connection: websocket_api.ActiveConnection,
            msg: dict[str, Any],
        ) -> None:
            entries = hass.config_entries.async_loaded_entries(DOMAIN)
            if not entries:
                connection.send_error(msg["id"], "not_loaded", "WattBill is not loaded")
                return
            wattbill = cast(WattBillConfigEntry, entries[0]).runtime_data
            if inspect.isawaitable(result := handler(hass, connection, msg, wattbill)):
                await result

        return websocket_api.websocket_command(schema)(
            websocket_api.require_admin(websocket_api.async_response(run))
        )

    return decorate
