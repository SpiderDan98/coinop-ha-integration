"""Dev container only: Scenarios of test data the Coin-op panel switches between."""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from custom_components.coinop.schema import vol

from .scenarios import SCENARIOS, async_load

DOMAIN = "coinop_dev"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    store = Store[dict[str, str]](hass, 1, DOMAIN)
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
                "scenarios": [
                    {"name": name, "title": s.title, "description": s.description}
                    for name, s in SCENARIOS.items()
                ],
                "current": loaded.get("scenario"),
            },
        )

    async def load(call: ServiceCall) -> None:
        user_id = call.context.user_id
        user = await hass.auth.async_get_user(user_id) if user_id else None
        await async_load(hass, call.data["scenario"], user)
        loaded["scenario"] = call.data["scenario"]
        await store.async_save(loaded)

    websocket_api.async_register_command(hass, scenarios)
    async_register_admin_service(
        hass,
        DOMAIN,
        "load",
        load,
        vol.Schema({vol.Required("scenario"): vol.In(list(SCENARIOS))}),
    )
    return True
