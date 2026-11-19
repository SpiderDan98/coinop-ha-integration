"""Spoolman as a Material's Cost Source, read over its REST API (mocked here)."""

from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .clock import Clock
from .devices import add_hub
from .stored import place_materials, stored_material
from .test_material_usage import (
    GRAMS_PER_METRE,
    add_measuring_device,
    material_items,
    set_usage,
)
from .test_runs import set_status, stored_runs
from .websocket import PanelClient

SPOOLMAN = "http://spoolman.local:7912"


def serve_spoolman(
    aioclient_mock: AiohttpClientMocker,
    filaments: list[dict[str, Any]] | None = None,
    spools: list[dict[str, Any]] | None = None,
    url: str = SPOOLMAN,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{url}/api/v1/info", json={"version": "0.27.1"})
    aioclient_mock.get(f"{url}/api/v1/filament", json=filaments or [])
    aioclient_mock.get(f"{url}/api/v1/spool", json=spools or [])


def spoolman_down(aioclient_mock: AiohttpClientMocker, url: str = SPOOLMAN) -> None:
    aioclient_mock.clear_requests()
    for path in ("info", "filament", "spool"):
        aioclient_mock.get(f"{url}/api/v1/{path}", exc=ClientError())


async def set_options(hass: HomeAssistant, entry: ConfigEntry, **options: Any) -> Any:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    await hass.async_block_till_done()
    return result


async def test_the_spoolman_url_is_checked_on_save(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    entry = await add_hub(hass)

    result = await set_options(hass, entry, spoolman_url=f"{SPOOLMAN}/")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"spoolman_url": SPOOLMAN}
    assert [str(url) for _, url, *_ in aioclient_mock.mock_calls] == [
        f"{SPOOLMAN}/api/v1/info"
    ]


async def test_a_url_without_spoolman_behind_it_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    spoolman_down(aioclient_mock)
    aioclient_mock.get("http://router.local/api/v1/info", text="<html>")
    entry = await add_hub(hass)

    for url in (SPOOLMAN, "http://router.local", "not a url"):
        result = await set_options(hass, entry, spoolman_url=url)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"spoolman_url": "cannot_connect"}
    assert entry.options == {}


async def test_the_spoolman_url_can_be_cleared(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    entry = await add_hub(hass)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)

    result = await set_options(hass, entry)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {}


def filament(filament_id: int, **fields: Any) -> dict[str, Any]:
    """A Filament as Spoolman's REST API returns it: 1 kg of eSun black PLA for 20."""
    return {
        "id": filament_id,
        "registered": "2026-01-10T09:00:00Z",
        "name": "PLA+ black",
        "vendor": {"id": 1, "registered": "2026-01-10T09:00:00Z", "name": "eSun"},
        "material": "PLA",
        "price": 20.0,
        "density": 1.24,
        "diameter": 1.75,
        "weight": 1000.0,
        "spool_weight": 200.0,
        "color_hex": "1A1A1A",
        "extra": {},
    } | fields


def spool(spool_id: int, of: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "id": spool_id,
        "registered": "2026-02-01T09:00:00Z",
        "filament": of,
        "price": None,
        "initial_weight": None,
        "used_weight": 0.0,
        "archived": False,
        "extra": {},
    } | fields


async def add_spoolman_hub(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, **served: Any
) -> ConfigEntry:
    serve_spoolman(aioclient_mock, **served)
    entry = await add_hub(hass)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    return entry


async def link(
    panel: PanelClient, material_id: str, filament_id: int, **changes: Any
) -> dict[str, Any]:
    result = await panel.call(
        "wattbill/materials/update",
        material_id=material_id,
        material=changes
        | {"price": {"source": "spoolman", "filament_id": filament_id}},
    )
    linked: dict[str, Any] = result["material"]
    return linked


async def test_a_linked_material_is_priced_per_gram_from_its_filament(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla", name="Black PLA"))
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])

    linked = await link(panel, "pla", 7)

    assert linked["price"] == {"source": "spoolman", "filament_id": 7, "per_gram": 0.02}
    assert linked["price_per_gram"] == pytest.approx(0.02)
    assert linked["name"] == "Black PLA"


async def test_without_a_filament_price_the_newest_priced_spool_counts(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    unpriced = filament(7, price=None)
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[unpriced, filament(8)],
        spools=[
            spool(1, unpriced, price=18.0, initial_weight=1000.0),
            spool(
                2,
                unpriced,
                price=22.5,
                initial_weight=750.0,
                registered="2026-02-15T09:00:00Z",
            ),
            spool(3, unpriced, registered="2026-03-01T09:00:00Z"),
            spool(4, filament(8), price=99.0, registered="2026-04-01T09:00:00Z"),
            spool(
                5,
                unpriced,
                price=40.0,
                initial_weight=1000.0,
                archived=True,
                registered="2026-05-01T09:00:00Z",
            ),
        ],
    )

    linked = await link(panel, "pla", 7)

    assert linked["price_per_gram"] == pytest.approx(0.03)


async def test_a_spool_without_its_own_weight_counts_the_filament_weight(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    unpriced = filament(7, price=None, weight=500.0)
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[unpriced],
        spools=[spool(1, unpriced, price=15)],
    )

    linked = await link(panel, "pla", 7)

    assert linked["price_per_gram"] == pytest.approx(0.03)


async def filaments(panel: PanelClient) -> dict[str, Any]:
    listed: dict[str, Any] = await panel.call("wattbill/spoolman/filaments")
    return listed


async def test_the_materials_tab_lists_the_spoolman_filaments(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    unpriced = filament(
        8,
        name=None,
        vendor=None,
        material=None,
        price=None,
        color_hex=None,
        multi_color_hexes="FF0000,00ff00",
    )
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7), unpriced])

    assert await filaments(panel) == {
        "status": "ok",
        "filaments": [
            {
                "id": 7,
                "name": "PLA+ black",
                "vendor": "eSun",
                "type": "PLA",
                "density": 1.24,
                "diameter": 1.75,
                "colour": "#1a1a1a",
                "price_per_gram": 0.02,
            },
            {
                "id": 8,
                "name": None,
                "vendor": None,
                "type": None,
                "density": 1.24,
                "diameter": 1.75,
                "colour": "#ff0000",
                "price_per_gram": None,
            },
        ],
    }


async def test_the_list_says_when_spoolman_is_not_set_up_or_unreachable(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    entry = await add_hub(hass)
    assert await filaments(panel) == {"status": "not_configured", "filaments": []}

    serve_spoolman(aioclient_mock)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)
    assert await filaments(panel) == {"status": "unreachable", "filaments": []}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{SPOOLMAN}/api/v1/filament", json={"detail": "not a list"})
    aioclient_mock.get(f"{SPOOLMAN}/api/v1/spool", json=[])
    assert await filaments(panel) == {"status": "unreachable", "filaments": []}


async def test_a_material_created_from_a_filament_takes_over_its_details(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])

    result = await panel.call("wattbill/materials/create_from_spoolman", filament_id=7)

    created = result["material"]
    assert created == {
        "id": created["id"],
        "name": "eSun PLA+ black",
        "form": "filament",
        "type": "PLA",
        "density": 1.24,
        "vendor": "eSun",
        "colour": "#1a1a1a",
        "diameter": 1.75,
        "default_for_type": False,
        "archived": False,
        "price": {"source": "spoolman", "filament_id": 7, "per_gram": 0.02},
        "price_per_gram": 0.02,
    }
    assert (await panel.call("wattbill/materials/list"))["materials"] == [created]


async def test_linked_materials_follow_their_filament_when_the_tab_opens(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla", name="Black PLA"))
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    await link(panel, "pla", 7, colour="#ffffff")
    await panel.subscribe("wattbill/catalog/subscribe")
    await panel.event()

    serve_spoolman(
        aioclient_mock,
        filaments=[
            filament(
                7,
                name="PETG blue",
                material="PETG",
                price=27.0,
                density=1.27,
                diameter=2.85,
                color_hex="0000FF",
                vendor={"id": 2, "name": "Prusament"},
            )
        ],
    )
    await filaments(panel)

    [material] = (await panel.event())["materials"]
    assert {
        key: material[key]
        for key in (
            "name",
            "type",
            "density",
            "diameter",
            "colour",
            "vendor",
            "price_per_gram",
        )
    } == {
        "name": "Black PLA",
        "type": "PETG",
        "density": 1.27,
        "diameter": 2.85,
        "colour": "#0000ff",
        "vendor": "Prusament",
        "price_per_gram": 0.027,
    }


async def test_linking_needs_spoolman_and_the_filament(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    price = {"source": "spoolman", "filament_id": 9}

    missing = await panel.error(
        "wattbill/materials/update", material_id="pla", material={"price": price}
    )
    not_created = await panel.error(
        "wattbill/materials/create_from_spoolman", filament_id=9
    )
    spoolman_down(aioclient_mock)
    unreachable = await panel.error(
        "wattbill/materials/update",
        material_id="pla",
        material={"price": price | {"filament_id": 7}},
    )

    assert (missing["code"], not_created["code"]) == ("not_found", "not_found")
    assert unreachable["code"] == "spoolman_unreachable"
    [material] = (await panel.call("wattbill/materials/list"))["materials"]
    assert material["price"]["source"] == "fixed"


def linked_material(material_id: str, per_gram: float, **fields: Any) -> dict[str, Any]:
    """A Material linked to Filament 7, last read at `per_gram`."""
    price = {"source": "spoolman", "filament_id": 7, "per_gram": per_gram}
    return stored_material(material_id, price=price, **fields)


async def print_one_metre(hass: HomeAssistant, clock: Clock) -> None:
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_usage(hass, 1000)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)
    await set_usage(hass, 1000)


async def test_a_run_end_reads_the_price_spoolman_has_then(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, linked_material("pla", 0.02))
    serve_spoolman(aioclient_mock, filaments=[filament(7)])
    entry = await add_measuring_device(hass, panel)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    await set_status(hass, "printing")
    await set_usage(hass, 1000)
    serve_spoolman(aioclient_mock, filaments=[filament(7, price=30.0)])

    [open_run] = (await panel.call("wattbill/runs/list"))["runs"]
    detail = (await panel.call("wattbill/runs/get", run_id=open_run["id"]))["run"]
    # While the Run is open, the last price read applies.
    assert material_items(detail)[0]["unit_price"] == 0.02

    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)
    await set_usage(hass, 1000)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["unit_price"] == pytest.approx(0.03)
    assert item["material"]["price_per_gram"] == pytest.approx(0.03)
    assert item["amount"] == pytest.approx(GRAMS_PER_METRE * 0.03)
    assert run["flags"] == []


@pytest.mark.parametrize("spoolman", ["unreachable", "not_configured"])
async def test_without_spoolman_the_last_price_read_applies_and_the_run_is_flagged(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
    spoolman: str,
) -> None:
    place_materials(hass_storage, linked_material("pla", 0.025))
    serve_spoolman(aioclient_mock)
    entry = await add_measuring_device(hass, panel)
    if spoolman == "unreachable":
        await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["unit_price"] == 0.025
    assert run["flags"] == ["spoolman_unreachable"]


async def test_a_run_without_a_spoolman_material_ignores_spoolman(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla"), linked_material("petg", 0.03))
    serve_spoolman(aioclient_mock)
    entry = await add_measuring_device(hass, panel)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    assert material_items(run)[0]["unit_price"] == 0.02
    assert run["flags"] == []
