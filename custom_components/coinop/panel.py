"""The admin-only sidebar panel, served from the bundle built into `frontend/`."""

import hashlib
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.frontend import async_panel_exists, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, NAME

URL_PATH = DOMAIN
ELEMENT = "coinop-panel"
BUNDLE = Path(__file__).parent / "frontend" / f"{ELEMENT}.js"
BUNDLE_URL = f"/{DOMAIN}_static/{ELEMENT}.js"
_SERVED: HassKey[bool] = HassKey(f"{DOMAIN}_panel_served")


def _bundle_hash() -> str | None:
    try:
        return hashlib.sha256(BUNDLE.read_bytes()).hexdigest()[:12]
    except FileNotFoundError:
        return None


async def async_register(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Show the panel while the hub entry is loaded."""
    # aiohttp can't remove a route, so the bundle stays served across reloads.
    if not hass.data.get(_SERVED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(BUNDLE_URL, str(BUNDLE), cache_headers=True)]
        )
        hass.data[_SERVED] = True
    version = await hass.async_add_executor_job(_bundle_hash) or str(
        (await async_get_integration(hass, DOMAIN)).version
    )
    if not async_panel_exists(hass, URL_PATH):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=URL_PATH,
            webcomponent_name=ELEMENT,
            sidebar_title=NAME,
            sidebar_icon="mdi:hand-coin-outline",
            module_url=f"{BUNDLE_URL}?v={version}",
            require_admin=True,
            config_panel_domain=DOMAIN,
        )
    entry.async_on_unload(
        lambda: async_remove_panel(hass, URL_PATH, warn_if_unknown=False)
    )
