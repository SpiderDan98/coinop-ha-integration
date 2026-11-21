"""Dev container only: test data the Coin-op panel loads, a Preset or a selection of
Pieces at a time."""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from custom_components.coinop.device_config import DEVICE_TYPES
from custom_components.coinop.schema import vol

from .scenarios import PIECES, PRESETS, async_load, ordered

DOMAIN = "coinop_dev"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # The selection loaded last, with the Preset's name if it came from one.
    store = Store[dict[str, Any]](hass, 1, DOMAIN)
    loaded = await store.async_load() or {}

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/scenarios"})
    @websocket_api.require_admin
    @callback
    def scenarios(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        connection.send_result(
            msg["id"],
            {
                "groups": [
                    {
                        "device_type": device_type,
                        "pieces": [
                            {
                                "name": name,
                                "title": piece.title,
                                "description": piece.description,
                                "section": piece.section,
                            }
                            for name, piece in PIECES.items()
                            if piece.group == device_type
                        ],
                    }
                    for device_type in DEVICE_TYPES
                    if any(piece.group == device_type for piece in PIECES.values())
                ],
                "presets": [
                    {
                        "name": name,
                        "title": preset.title,
                        "description": preset.description,
                        "selection": {"pieces": ordered(preset.pieces)},
                    }
                    for name, preset in PRESETS.items()
                ],
                "preset": loaded.get("preset"),
                "selection": loaded.get("selection"),
            },
        )

    async def load(call: ServiceCall) -> None:
        user_id = call.context.user_id
        user = await hass.auth.async_get_user(user_id) if user_id else None
        preset = call.data.get("preset")
        selection = await async_load(hass, preset or call.data, user)
        loaded.update(preset=preset, selection=selection)
        await store.async_save(loaded)

    websocket_api.async_register_command(hass, scenarios)
    async_register_admin_service(
        hass,
        DOMAIN,
        "load",
        load,
        vol.Schema(
            vol.Any(
                {vol.Required("preset"): vol.In(list(PRESETS))},
                {vol.Required("pieces"): [vol.In(list(PIECES))]},
            )
        ),
    )
    return True
