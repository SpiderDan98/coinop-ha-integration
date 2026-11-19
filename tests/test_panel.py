"""The WattBill sidebar panel: registered with the hub entry, gone when it unloads."""

from homeassistant.components.frontend import DATA_PANELS, async_panel_exists
from homeassistant.core import HomeAssistant

from .devices import add_device, add_hub


def panel_config(hass: HomeAssistant) -> dict[str, object]:
    response = hass.data[DATA_PANELS]["wattbill"].to_response()
    return {**response, **(response["config"] or {})["_panel_custom"]}


async def test_the_hub_adds_an_admin_only_panel(hass: HomeAssistant) -> None:
    await add_hub(hass)

    config = panel_config(hass)
    assert config["component_name"] == "custom"
    assert config["require_admin"] is True
    assert config["title"] == "WattBill"
    assert config["url_path"] == "wattbill"
    assert config["name"] == "wattbill-panel"
    assert config["embed_iframe"] is False
    assert str(config["module_url"]).startswith("/wattbill_static/wattbill-panel.js?v=")


async def test_unloading_removes_the_panel(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert not async_panel_exists(hass, "wattbill")


async def test_the_panel_survives_a_reload(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    await add_device(hass, entry)

    assert async_panel_exists(hass, "wattbill")
