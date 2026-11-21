"""A Spoolman already in Home Assistant is offered as a repair while none is set."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .devices import add_device, add_hub, add_washing_machine
from .test_spoolman import SPOOLMAN, serve_spoolman, set_options, spoolman_down

INGRESS_ADDON = "http://20c49e40-spoolman-ingress:7912"


def add_spoolman_integration(hass: HomeAssistant, url: str = f"{SPOOLMAN}/") -> None:
    """The Spoolman integration's entry, which keeps the URL with a trailing slash."""
    MockConfigEntry(domain="spoolman", data={"spoolman_url": url}).add_to_hass(hass)


def supervisor(*addons: dict[str, Any]) -> Any:
    """A Supervisor with these add-ons installed, each its `addon_info` fields."""
    client = SimpleNamespace(
        addons=SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    SimpleNamespace(slug=a["slug"], state=a["state"]) for a in addons
                ]
            ),
            addon_info=AsyncMock(
                side_effect=lambda slug: next(
                    SimpleNamespace(**a) for a in addons if a["slug"] == slug
                )
            ),
        )
    )
    return patch(
        "homeassistant.components.hassio.get_supervisor_client", return_value=client
    )


def addon(slug: str, **fields: Any) -> dict[str, Any]:
    return {
        "slug": slug,
        "state": "started",
        "hostname": slug.replace("_", "-"),
        "ingress": False,
        "ingress_port": None,
        "network": None,
    } | fields


def offered(hass: HomeAssistant) -> str | None:
    issue = ir.async_get(hass).async_get_issue("coinop", "spoolman_found")
    return None if issue is None else (issue.translation_placeholders or {})["url"]


async def settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def add_printer_hub(hass: HomeAssistant) -> ConfigEntry:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await settle(hass)
    return entry


async def start_fix(hass: HomeAssistant) -> Any:
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_init("coinop", data={"issue_id": "spoolman_found"})
    assert result["type"] is FlowResultType.FORM
    return manager, result


async def test_the_spoolman_integrations_url_is_offered_for_a_printer(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass)

    await add_printer_hub(hass)

    assert offered(hass) == SPOOLMAN
    issue = ir.async_get(hass).async_get_issue("coinop", "spoolman_found")
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.WARNING


async def test_the_spoolman_ingress_addon_is_reached_on_its_ingress_port(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock, url=INGRESS_ADDON)
    hass.config.components.add("hassio")

    with supervisor(
        addon("a0d7b954_vscode"),
        addon("20c49e40_spoolman_ingress", ingress=True, ingress_port=7912),
    ):
        await add_printer_hub(hass)

    assert offered(hass) == INGRESS_ADDON


async def test_the_spoolman_addon_is_reached_on_its_container_port(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    url = "http://local-spoolman:7920"
    serve_spoolman(aioclient_mock, url=url)
    hass.config.components.add("hassio")

    with supervisor(addon("local_spoolman", network={"7920/tcp": 8000})):
        await add_printer_hub(hass)

    assert offered(hass) == url


async def test_a_stopped_addon_is_not_offered(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock, url=INGRESS_ADDON)
    hass.config.components.add("hassio")

    with supervisor(addon("20c49e40_spoolman_ingress", state="stopped", ingress=True)):
        await add_printer_hub(hass)

    assert offered(hass) is None


async def test_a_spoolman_that_does_not_answer_is_not_offered(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    spoolman_down(aioclient_mock)
    add_spoolman_integration(hass)

    await add_printer_hub(hass)

    assert offered(hass) is None


async def test_nothing_is_offered_without_a_device_that_uses_material(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass)
    entry = await add_hub(hass)

    await add_washing_machine(hass, entry, source="none")
    await settle(hass)

    assert offered(hass) is None
    assert aioclient_mock.call_count == 0


async def test_nothing_is_offered_once_a_spoolman_url_is_set(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass)
    entry = await add_printer_hub(hass)
    assert offered(hass) == SPOOLMAN

    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    await settle(hass)

    assert offered(hass) is None


async def test_connecting_stores_the_url_found(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass)
    entry = await add_printer_hub(hass)
    await set_options(hass, entry, markup=10.0)
    await settle(hass)
    manager, result = await start_fix(hass)
    assert result["description_placeholders"] == {"url": SPOOLMAN}

    result = await manager.async_configure(result["flow_id"], {})
    await settle(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"markup": 10.0, "spoolman_url": SPOOLMAN}
    assert offered(hass) is None


async def test_connecting_a_spoolman_that_went_away_changes_nothing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass)
    entry = await add_printer_hub(hass)
    manager, result = await start_fix(hass)
    spoolman_down(aioclient_mock)

    result = await manager.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert result["description_placeholders"] == {"url": SPOOLMAN}
    assert entry.options == {}


@pytest.mark.parametrize("url", [SPOOLMAN, f"{SPOOLMAN}/"])
async def test_the_integrations_url_is_stored_without_a_trailing_slash(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, url: str
) -> None:
    serve_spoolman(aioclient_mock)
    add_spoolman_integration(hass, url)

    await add_printer_hub(hass)

    assert offered(hass) == SPOOLMAN
