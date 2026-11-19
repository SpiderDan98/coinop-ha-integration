"""Shared fixtures: every test gets a fresh Home Assistant instance from `hass`."""

from collections.abc import Callable
from pathlib import Path

from aiohttp.web import WebSocketResponse
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

# Imported first so `custom_components` resolves to this repo, not to the test
# config dir that HA puts on sys.path.
import custom_components.wattbill  # noqa: F401

from .clock import CLOCK_START, Clock
from .http import HttpClient, http_client
from .websocket import PanelClient, panel_client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load `custom_components/wattbill` in every test."""


@pytest.fixture
def clock(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Clock:
    """Clock frozen at `CLOCK_START`; advance it with `await clock.advance(...)`."""
    freezer.move_to(CLOCK_START)
    return Clock(hass, freezer)


@pytest.fixture
def connect_panel(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[MockUser], PanelClient]:
    """Websocket connections for a given user: `connect_panel(hass_read_only_user)`."""
    # Advancing the clock fires the server's heartbeat timers, which would then
    # close the connection for a pong the test client had no chance to send.
    monkeypatch.setattr(WebSocketResponse, "_reset_heartbeat", lambda self: None)
    return lambda user: panel_client(hass, hass_ws_client, user)


@pytest.fixture
def connect_http(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> Callable[[MockUser], HttpClient]:
    """HTTP clients for a given user: `connect_http(hass_read_only_user)`."""
    return lambda user: http_client(hass, hass_client, user)


@pytest.fixture
def http(
    connect_http: Callable[[MockUser], HttpClient], hass_admin_user: MockUser
) -> HttpClient:
    """An admin's HTTP client, as the panel fetches with."""
    return connect_http(hass_admin_user)


@pytest.fixture
def files(hass: HomeAssistant, tmp_path: Path) -> Path:
    """WattBill's file folder, in a config directory of the test's own."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path / "wattbill"


@pytest.fixture
def panel(
    connect_panel: Callable[[MockUser], PanelClient], hass_admin_user: MockUser
) -> PanelClient:
    """An admin's websocket connection, as the panel has one."""
    return connect_panel(hass_admin_user)


@pytest.fixture
def watcher(
    connect_panel: Callable[[MockUser], PanelClient], hass_admin_user: MockUser
) -> PanelClient:
    """A second open panel, subscribed to what the first one changes."""
    return connect_panel(hass_admin_user)
