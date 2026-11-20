"""Talk to Coin-op's websocket commands the way the panel does."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import CLIENT_ID
from pytest_homeassistant_custom_component.typing import (
    MockHAClientWebSocket,
    WebSocketGenerator,
)


class PanelClient:
    """One websocket connection; `call` / `error` / `subscribe` a `coinop/...` command.

    Connects on first use: starting the test HTTP server freezes its routes, so
    Coin-op must be set up before, and the access token must not have expired
    on the test clock.
    """

    def __init__(self, connect: Callable[[], Awaitable[MockHAClientWebSocket]]) -> None:
        self._connect = connect
        self._connection: MockHAClientWebSocket | None = None
        self._events: list[dict[str, Any]] = []

    async def _client(self) -> MockHAClientWebSocket:
        if self._connection is None:
            self._connection = await self._connect()
        return self._connection

    async def _send(self, command: str, data: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        await client.send_json_auto_id({"type": command, **data})
        while (response := await client.receive_json())["type"] == "event":
            # A change the command caused may be pushed before its result.
            self._events.append(response)
        return cast(dict[str, Any], response)

    async def call(self, command: str, **data: Any) -> Any:
        response = await self._send(command, data)
        assert response["success"], response
        return response["result"]

    async def error(self, command: str, **data: Any) -> dict[str, Any]:
        response = await self._send(command, data)
        assert not response["success"], response
        error: dict[str, Any] = response["error"]
        return error

    async def subscribe(self, command: str, **data: Any) -> None:
        await self.call(command, **data)

    async def event(self) -> Any:
        """The next message pushed to a subscription on this connection."""
        if self._events:
            message = self._events.pop(0)
        else:
            message = await (await self._client()).receive_json()
        assert message["type"] == "event", message
        return message["event"]


def panel_client(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, user: User
) -> PanelClient:
    async def connect() -> MockHAClientWebSocket:
        refresh_token = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
        token = hass.auth.async_create_access_token(refresh_token)
        return await hass_ws_client(hass, token)

    return PanelClient(connect)
