"""Fetch from WattBill's HTTP views the way the panel does, as a given user."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from aiohttp import FormData, web
from aiohttp.test_utils import TestClient
from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from multidict import CIMultiDictProxy
from pytest_homeassistant_custom_component.common import CLIENT_ID
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


class HttpClient:
    """Starts the test HTTP server on first use, so set WattBill up before."""

    def __init__(
        self, connect: Callable[[], Awaitable[TestClient[web.Request, web.Application]]]
    ) -> None:
        self._connect = connect
        self._client: TestClient[web.Request, web.Application] | None = None

    async def _session(self) -> TestClient[web.Request, web.Application]:
        if self._client is None:
            self._client = await self._connect()
        return self._client

    async def get(self, path: str) -> tuple[int, bytes]:
        status, _, body = await self.download(path)
        return status, body

    async def download(self, path: str) -> tuple[int, CIMultiDictProxy[str], bytes]:
        response = await (await self._session()).get(path)
        return response.status, response.headers, await response.read()

    async def upload(
        self, path: str, *files: bytes | tuple[bytes, str]
    ) -> tuple[int, Any]:
        """POST files as the panel's upload does: each a `file` part, JPEG unless typed."""
        form = FormData()
        for n, file in enumerate(files):
            content, content_type = (
                file if isinstance(file, tuple) else (file, "image/jpeg")
            )
            form.add_field(
                "file", content, filename=f"photo-{n}", content_type=content_type
            )
        response = await (await self._session()).post(path, data=form)
        is_json = response.content_type == "application/json"
        return response.status, await (response.json() if is_json else response.read())

    async def content(self, path: str) -> bytes:
        status, body = await self.get(path)
        assert status == 200, (status, path)
        return body


def http_client(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, user: User
) -> HttpClient:
    async def connect() -> TestClient[web.Request, web.Application]:
        # Long-lived, as tests move the clock by hours.
        refresh_token = await hass.auth.async_create_refresh_token(
            user, CLIENT_ID, access_token_expiration=timedelta(days=365)
        )
        token = hass.auth.async_create_access_token(refresh_token)
        client: TestClient[web.Request, web.Application] = await hass_client(token)
        return client

    return HttpClient(connect)
