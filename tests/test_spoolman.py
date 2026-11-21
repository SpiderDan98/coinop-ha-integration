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
    print_one_metre,
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
    # Setting up again reads Spoolman in the background.
    await hass.async_block_till_done(wait_background_tasks=True)
    return result


async def test_the_spoolman_url_is_checked_on_save(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    serve_spoolman(aioclient_mock)
    entry = await add_hub(hass)

    result = await set_options(hass, entry, spoolman_url=f"{SPOOLMAN}/")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"spoolman_url": SPOOLMAN}
    # Saving checks the URL, and the hub set up again reads Spoolman.
    assert [str(url) for _, url, *_ in aioclient_mock.mock_calls] == [
        f"{SPOOLMAN}/api/v1/{path}" for path in ("info", "filament", "spool")
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


async def read(panel: PanelClient) -> dict[str, Any]:
    answer: dict[str, Any] = await panel.call("coinop/spoolman/read")
    return answer


async def materials(panel: PanelClient) -> list[dict[str, Any]]:
    listed: list[dict[str, Any]] = (await panel.call("coinop/materials/list"))[
        "materials"
    ]
    return listed


async def of_filament(panel: PanelClient, filament_id: int) -> dict[str, Any]:
    """The Material linked to the Filament."""
    [material] = [
        m
        for m in await materials(panel)
        if m["price"]["source"] == "spoolman"
        and m["price"]["filament_id"] == filament_id
    ]
    return material


def merges(answer: dict[str, Any]) -> dict[str, list[int]]:
    """The candidates' ids, by own Material."""
    return {
        merge["material_id"]: [f["id"] for f in merge["candidates"]]
        for merge in answer["merges"]
    }


async def test_reading_spoolman_gives_each_filament_a_linked_material(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock)
    serve_spoolman(aioclient_mock, filaments=[filament(7)])

    assert await read(panel) == {"status": "ok", "merges": []}

    [created] = await materials(panel)
    assert created == {
        "id": created["id"],
        "name": "eSun PLA+ black",
        "form": "filament",
        "type": "PLA",
        "density": 1.24,
        "vendor": "eSun",
        "colour": "#1a1a1a",
        "diameter": 1.75,
        "default_for_type": True,
        "archived": False,
        "price": {
            "source": "spoolman",
            "filament_id": 7,
            "per_gram": 0.02,
            "pack_price": 20.0,
            "pack_weight": 1000.0,
        },
        "price_per_gram": 0.02,
        "price_per_piece": None,
    }
    await read(panel)
    assert await materials(panel) == [created]


async def test_starting_with_spoolman_set_reads_it(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])

    assert [m["name"] for m in await materials(panel)] == ["eSun PLA+ black"]


async def test_without_a_filament_price_the_newest_priced_spool_counts(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
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

    material = await of_filament(panel, 7)

    assert material["price_per_gram"] == pytest.approx(0.03)
    assert (material["price"]["pack_price"], material["price"]["pack_weight"]) == (
        22.5,
        750.0,
    )


async def test_a_spool_without_its_own_weight_counts_the_filament_weight(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    unpriced = filament(7, price=None, weight=500.0)
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[unpriced],
        spools=[spool(1, unpriced, price=15)],
    )

    assert (await of_filament(panel, 7))["price_per_gram"] == pytest.approx(0.03)


async def test_a_filament_without_a_price_or_a_name_still_gets_a_material(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    bare = filament(
        8,
        name=None,
        vendor=None,
        material=None,
        price=None,
        color_hex=None,
        multi_color_hexes="FF0000,00ff00",
    )
    await add_spoolman_hub(hass, aioclient_mock, filaments=[bare])

    material = await of_filament(panel, 8)

    assert {k: material[k] for k in ("name", "type", "colour", "vendor")} == {
        "name": "8",
        "type": "8",
        "colour": "#ff0000",
        "vendor": None,
    }
    assert material["price"] == {
        "source": "spoolman",
        "filament_id": 8,
        "per_gram": None,
        "pack_price": None,
        "pack_weight": None,
    }


async def test_a_new_material_is_default_only_while_its_type_has_none(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(
        hass_storage,
        stored_material("resin", form="resin", type="PETG", default_for_type=True),
        stored_material("old-pla", type="pla", default_for_type=True, archived=True),
    )
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[
            filament(7),
            filament(8, name="PLA red"),
            filament(9, name="PETG grey", material="PETG"),
        ],
    )
    first = await of_filament(panel, 7)
    assert first["default_for_type"] is True
    await panel.call(
        "coinop/materials/update",
        material_id=first["id"],
        material={"default_for_type": False},
    )

    await read(panel)

    assert {
        m["name"]: m["default_for_type"]
        for m in await materials(panel)
        if m["price"]["source"] == "spoolman"
    } == {"eSun PLA+ black": False, "eSun PLA red": False, "eSun PETG grey": False}


async def test_a_filament_gone_from_spoolman_archives_its_material(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(
        hass, aioclient_mock, filaments=[filament(7), filament(8, name="PLA red")]
    )
    kept = await of_filament(panel, 8)
    await panel.call("coinop/materials/archive", material_id=kept["id"])
    serve_spoolman(aioclient_mock, filaments=[filament(8, name="PLA red")])

    await read(panel)
    await read(panel)

    by_filament = {m["price"]["filament_id"]: m for m in await materials(panel)}
    assert {
        f: (m["archived"], m["default_for_type"]) for f, m in by_filament.items()
    } == {
        7: (True, False),
        8: (True, False),
    }


async def test_linked_materials_follow_their_filament_when_the_tab_opens(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    await panel.subscribe("coinop/catalog/subscribe")
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
    await read(panel)

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
        "name": "Prusament PETG blue",
        "type": "PETG",
        "density": 1.27,
        "diameter": 2.85,
        "colour": "#0000ff",
        "vendor": "Prusament",
        "price_per_gram": 0.027,
    }


async def test_a_filament_that_lost_its_price_keeps_the_last_price_read(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    serve_spoolman(aioclient_mock, filaments=[filament(7, price=None)])

    await read(panel)

    material = await of_filament(panel, 7)
    assert material["price"] == {
        "source": "spoolman",
        "filament_id": 7,
        "per_gram": 0.02,
        "pack_price": None,
        "pack_weight": None,
    }


async def test_the_read_says_when_spoolman_is_not_set_up_or_unreachable(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    entry = await add_hub(hass)
    assert await read(panel) == {"status": "not_configured", "merges": []}

    serve_spoolman(aioclient_mock)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)
    assert await read(panel) == {"status": "unreachable", "merges": []}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{SPOOLMAN}/api/v1/filament", json={"detail": "not a list"})
    aioclient_mock.get(f"{SPOOLMAN}/api/v1/spool", json=[])
    assert await read(panel) == {"status": "unreachable", "merges": []}


async def test_clearing_the_url_keeps_linked_materials_and_their_last_price(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    entry = await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    before = await of_filament(panel, 7)

    await set_options(hass, entry)
    await read(panel)

    assert await materials(panel) == [before]


def own(material_id: str, **fields: Any) -> dict[str, Any]:
    """An own black eSun PLA at 0.025 per gram."""
    return (
        stored_material(
            material_id,
            name="My black PLA",
            vendor="eSun",
            colour="#1a1a1a",
            price={
                "source": "fixed",
                "pack_price": 25.0,
                "pack_size": 1000.0,
                "pack_unit": "g",
            },
        )
        | fields
    )


async def test_filaments_matching_an_own_material_wait_to_be_merged(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(
        hass_storage,
        own("black"),
        own("any-pla", name="Any PLA", vendor="Prusament", colour=None),
        own("archived", archived=True),
        own("resin", form="resin"),
        own(
            "pods",
            price={
                "source": "fixed",
                "pack_price": 1,
                "pack_size": 10,
                "pack_unit": "pcs",
            },
            density=None,
        ),
    )
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[
            filament(7),
            filament(
                8,
                name="PLA white",
                color_hex="FFFFFF",
                vendor={"id": 2, "name": "Prusament"},
            ),
            filament(
                9, name="PLA+ black", material="pla", vendor={"id": 3, "name": "Sunlu"}
            ),
            filament(10, material="PETG"),
            filament(11, material=None),
        ],
    )

    answer = await read(panel)

    assert merges(answer) == {"black": [7, 9], "any-pla": [8, 7, 9]}
    assert answer["merges"][0]["candidates"][0] == {
        "id": 7,
        "name": "eSun PLA+ black",
        "vendor": "eSun",
        "type": "PLA",
        "colour": "#1a1a1a",
        "price_per_gram": 0.02,
    }
    linked = [m for m in await materials(panel) if m["price"]["source"] == "spoolman"]
    assert sorted(m["price"]["filament_id"] for m in linked) == [10, 11]


async def test_merging_links_the_own_material_in_place(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(
        hass_storage,
        own("black", default_for_type=True),
        own("white", name="My white PLA", colour="#ffffff"),
    )
    await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[
            filament(7),
            filament(8, name="PLA white", color_hex="FFFFFF", price=None),
            filament(9, name="PLA+ black v2"),
        ],
    )

    answer = await panel.call(
        "coinop/spoolman/merge",
        picks=[
            {"material_id": "black", "filament_id": 7},
            {"material_id": "white", "filament_id": 8},
        ],
    )

    assert answer == {"status": "ok", "merges": []}
    by_id = {m["id"]: m for m in await materials(panel)}
    assert by_id["black"] == {
        "id": "black",
        "name": "eSun PLA+ black",
        "form": "filament",
        "type": "PLA",
        "density": 1.24,
        "vendor": "eSun",
        "colour": "#1a1a1a",
        "diameter": 1.75,
        "default_for_type": True,
        "archived": False,
        "price": {
            "source": "spoolman",
            "filament_id": 7,
            "per_gram": 0.02,
            "pack_price": 20.0,
            "pack_weight": 1000.0,
        },
        "price_per_gram": 0.02,
        "price_per_piece": None,
    }
    # Without a price in Spoolman, its fixed price stays as the last price read.
    assert by_id["white"]["price"] == {
        "source": "spoolman",
        "filament_id": 8,
        "per_gram": 0.025,
        "pack_price": None,
        "pack_weight": None,
    }
    [new] = [m for m in by_id.values() if m["id"] not in ("black", "white")]
    assert (new["price"]["filament_id"], new["default_for_type"]) == (9, False)


async def test_keeping_own_gives_the_candidates_their_own_materials(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, own("black"), own("any", name="Any PLA", colour=None))
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7), filament(8)])

    kept = await panel.call(
        "coinop/spoolman/merge", picks=[{"material_id": "black", "filament_id": None}]
    )

    # Both Filaments are candidates of Any PLA too, which wasn't decided.
    assert merges(kept) == {"black": [7, 8], "any": [7, 8]}
    assert await panel.call(
        "coinop/spoolman/merge",
        picks=[
            {"material_id": "black", "filament_id": None},
            {"material_id": "any", "filament_id": None},
        ],
    ) == {"status": "ok", "merges": []}
    by_id = {m["id"]: m for m in await materials(panel)}
    assert (
        by_id["black"]["price"]["source"] == by_id["any"]["price"]["source"] == "fixed"
    )
    assert sorted(
        m["price"]["filament_id"]
        for m in by_id.values()
        if m["price"]["source"] == "spoolman"
    ) == [7, 8]
    serve_spoolman(aioclient_mock, filaments=[filament(7), filament(8), filament(9)])
    assert merges(await read(panel)) == {"black": [9], "any": [9]}


async def test_a_merge_needs_spoolman_and_picks_still_waiting(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, own("black"), own("other", name="Other black"))
    await add_spoolman_hub(
        hass, aioclient_mock, filaments=[filament(7), filament(8, material="PETG")]
    )
    MERGE = "coinop/spoolman/merge"

    stale = [
        await panel.error(MERGE, picks=[{"material_id": "black", "filament_id": 8}]),
        await panel.error(MERGE, picks=[{"material_id": "gone", "filament_id": None}]),
        await panel.error(
            MERGE,
            picks=[
                {"material_id": "black", "filament_id": 7},
                {"material_id": "other", "filament_id": 7},
            ],
        ),
    ]
    spoolman_down(aioclient_mock)
    unreachable = await panel.error(
        MERGE, picks=[{"material_id": "black", "filament_id": 7}]
    )

    assert [error["code"] for error in stale] == ["not_allowed"] * 3
    assert unreachable["code"] == "spoolman_unreachable"
    assert {m["id"]: m["price"]["source"] for m in await materials(panel)} == {
        "black": "fixed",
        "other": "fixed",
        (await of_filament(panel, 8))["id"]: "spoolman",
    }


async def test_a_linked_material_only_changes_its_default_and_is_never_deleted(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])
    material = await of_filament(panel, 7)
    UPDATE = "coinop/materials/update"

    renamed = await panel.error(
        UPDATE, material_id=material["id"], material={"name": "Mine"}
    )
    fixed = await panel.error(
        UPDATE,
        material_id=material["id"],
        material={"price": {"source": "fixed", "pack_price": 1, "pack_size": 1}},
    )
    relinked = await panel.error(
        UPDATE,
        material_id=material["id"],
        material={"price": {"source": "spoolman", "filament_id": 7}},
    )
    deleted = await panel.error("coinop/materials/delete", material_id=material["id"])
    unstarred = await panel.call(
        UPDATE, material_id=material["id"], material={"default_for_type": False}
    )

    assert [renamed["code"], fixed["code"], deleted["code"]] == ["not_allowed"] * 3
    assert relinked["code"] == "invalid_format"
    assert unstarred["material"] == material | {"default_for_type": False}


async def test_own_materials_of_every_form_can_still_be_created(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await add_spoolman_hub(hass, aioclient_mock, filaments=[filament(7)])

    created = await panel.call(
        "coinop/materials/create",
        material={
            "name": "Cheap PLA",
            "form": "filament",
            "type": "PLA",
            "density": 1.24,
            "price": {"source": "fixed", "pack_price": 15, "pack_size": 1000},
        },
    )

    assert created["material"]["price"]["source"] == "fixed"
    assert merges(await read(panel)) == {}


def linked_material(material_id: str, per_gram: float, **fields: Any) -> dict[str, Any]:
    """A Material linked to Filament 7, last read at `per_gram`."""
    price = {"source": "spoolman", "filament_id": 7, "per_gram": per_gram}
    return stored_material(material_id, price=price, **fields)


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

    [open_run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = (await panel.call("coinop/runs/get", run_id=open_run["id"]))["run"]
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
    serve_spoolman(aioclient_mock, filaments=[filament(7, price=25.0)])
    entry = await add_measuring_device(hass, panel)
    if spoolman == "unreachable":
        await set_options(hass, entry, spoolman_url=SPOOLMAN)
    spoolman_down(aioclient_mock)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["unit_price"] == 0.025
    assert run["flags"] == ["spoolman_unreachable"]


async def test_a_filament_spoolman_never_priced_flags_the_run(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Never a silent zero: the user has to enter the unit price."""
    place_materials(
        hass_storage,
        stored_material(
            "pla", price={"source": "spoolman", "filament_id": 7, "per_gram": None}
        ),
    )
    serve_spoolman(aioclient_mock, filaments=[filament(7, price=None)])
    entry = await add_measuring_device(hass, panel)
    await set_options(hass, entry, spoolman_url=SPOOLMAN)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["unit_price"] == 0
    assert run["flags"] == ["spoolman_no_price"]


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
