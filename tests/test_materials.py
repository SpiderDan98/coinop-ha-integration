"""The Materials catalogue: maintained in the panel, priced per gram, pushed live."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import Clock
from .devices import add_hub
from .stored import (
    line_item,
    place_materials,
    place_runs,
    stored_material,
    stored_run,
)
from .websocket import PanelClient

PLA = {
    "name": "eSun PLA+ black",
    "form": "filament",
    "type": "PLA",
    "density": 1.24,
    "price": {"source": "fixed", "pack_price": 19.99, "pack_size": 1000},
}


def run_using(run_id: str, material_id: str, **fields: Any) -> dict[str, Any]:
    run = stored_run(run_id, **fields)
    run["line_items"].append(line_item("material", 0.31, material_id=material_id))
    return run


async def create(panel: PanelClient, **material: Any) -> dict[str, Any]:
    result = await panel.call("wattbill/materials/create", material=material)
    created: dict[str, Any] = result["material"]
    return created


async def materials(panel: PanelClient) -> list[dict[str, Any]]:
    result = await panel.call("wattbill/materials/list")
    listed: list[dict[str, Any]] = result["materials"]
    return listed


async def test_a_filament_is_priced_per_gram_from_its_pack(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    created = await create(panel, **PLA)

    assert created == {
        "id": created["id"],
        "name": "eSun PLA+ black",
        "form": "filament",
        "type": "PLA",
        "density": 1.24,
        "vendor": None,
        "colour": None,
        "diameter": 1.75,
        "default_for_type": False,
        "archived": False,
        "price": {
            "source": "fixed",
            "pack_price": 19.99,
            "pack_size": 1000,
            "pack_unit": "g",
        },
        "price_per_gram": pytest.approx(0.01999),
    }
    assert await materials(panel) == [created]


async def test_resin_bought_by_volume_is_priced_per_gram_through_its_density(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    created = await create(
        panel,
        name="Standard Resin grey",
        form="resin",
        type="Standard resin",
        density=1.1,
        diameter=1.75,
        price={"source": "fixed", "pack_price": 29.99, "pack_size": 1000},
    )

    assert created["price"]["pack_unit"] == "ml"
    assert created["price_per_gram"] == pytest.approx(29.99 / 1100)
    assert created["diameter"] is None


async def test_the_pack_size_can_be_given_in_either_unit(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    price = {"source": "fixed", "pack_price": 24.8}

    by_volume = await create(
        panel, **PLA | {"price": price | {"pack_size": 800, "pack_unit": "ml"}}
    )
    by_weight = await create(
        panel,
        **PLA
        | {"form": "resin", "price": price | {"pack_size": 500, "pack_unit": "g"}},
    )

    assert by_volume["price_per_gram"] == pytest.approx(0.025)
    assert by_weight["price_per_gram"] == pytest.approx(0.0496)


async def test_a_material_keeps_its_optional_details(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    created = await create(panel, **PLA, vendor="eSun", colour="#1A1A1A", diameter=2.85)

    assert {key: created[key] for key in ("vendor", "colour", "diameter")} == {
        "vendor": "eSun",
        "colour": "#1a1a1a",
        "diameter": 2.85,
    }


async def test_built_in_types_give_the_density_to_pre_fill(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    result = await panel.call("wattbill/materials/types")

    types = {entry["type"]: entry for entry in result["types"]}
    assert types["PLA"] == {"type": "PLA", "form": "filament", "density": 1.24}
    assert types["PETG"]["density"] == 1.27
    assert types["Standard resin"]["form"] == "resin"


@pytest.mark.parametrize(
    "invalid",
    [
        {"name": "  "},
        {"form": "pellets"},
        {"type": ""},
        {"density": 0},
        {"colour": "black"},
        {"diameter": -1},
        {"price": {"source": "fixed", "pack_price": 19.99, "pack_size": 0}},
        {"price": {"source": "fixed", "pack_price": -1, "pack_size": 1000}},
        {
            "price": {
                "source": "fixed",
                "pack_price": 1,
                "pack_size": 1,
                "pack_unit": "kg",
            }
        },
        {"price": {"source": "spoolman", "pack_price": 1, "pack_size": 1}},
    ],
)
async def test_invalid_materials_are_rejected(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, invalid: dict[str, Any]
) -> None:
    await add_hub(hass)

    error = await panel.error("wattbill/materials/create", material=PLA | invalid)

    assert error["code"] == "invalid_format"
    assert await materials(panel) == []


async def test_name_and_type_are_trimmed(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    created = await create(panel, **PLA | {"name": " PLA ", "type": "PLA "})

    assert (created["name"], created["type"]) == ("PLA", "PLA")


async def test_one_material_per_type_is_its_default(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    black = await create(panel, **PLA, default_for_type=True)
    petg = await create(panel, **PLA | {"type": "PETG"}, default_for_type=True)

    red = await create(panel, **PLA | {"type": "pla"}, default_for_type=True)

    defaults = {m["id"]: m["default_for_type"] for m in await materials(panel)}
    assert defaults == {black["id"]: False, petg["id"]: True, red["id"]: True}


async def test_editing_changes_only_the_given_fields(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    created = await create(panel, **PLA, vendor="eSun", colour="#1a1a1a")

    result = await panel.call(
        "wattbill/materials/update",
        material_id=created["id"],
        material={
            "name": "eSun PLA+ black 2 kg",
            "colour": None,
            "price": {"source": "fixed", "pack_price": 35, "pack_size": 2000},
        },
    )

    updated = result["material"]
    assert updated == created | {
        "name": "eSun PLA+ black 2 kg",
        "colour": None,
        "price": {
            "source": "fixed",
            "pack_price": 35,
            "pack_size": 2000,
            "pack_unit": "g",
        },
        "price_per_gram": pytest.approx(0.0175),
    }
    assert await materials(panel) == [updated]


async def test_marking_an_edited_material_default_unmarks_the_old_default(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    old = await create(panel, **PLA, default_for_type=True)
    new = await create(panel, **PLA)

    await panel.call(
        "wattbill/materials/update",
        material_id=new["id"],
        material={"default_for_type": True},
    )

    defaults = {m["id"]: m["default_for_type"] for m in await materials(panel)}
    assert defaults == {old["id"]: False, new["id"]: True}


async def test_a_material_switched_to_resin_drops_its_diameter(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    created = await create(panel, **PLA)

    result = await panel.call(
        "wattbill/materials/update",
        material_id=created["id"],
        material={"form": "resin", "type": "Standard resin", "density": 1.1},
    )

    assert result["material"]["diameter"] is None


async def test_archiving_takes_a_material_out_of_use_until_restored(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    created = await create(panel, **PLA, default_for_type=True)

    archived = await panel.call("wattbill/materials/archive", material_id=created["id"])
    restored = await panel.call("wattbill/materials/restore", material_id=created["id"])

    assert archived["material"]["archived"] is True
    # An archived Material leaves Slot matching, so it is no longer its type's default.
    assert archived["material"]["default_for_type"] is False
    assert restored["material"] == archived["material"] | {"archived": False}
    assert await materials(panel) == [restored["material"]]


async def test_deleting_an_unused_material_removes_it(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    kept = await create(panel, **PLA)
    unused = await create(panel, **PLA | {"name": "PLA red"})

    result = await panel.call("wattbill/materials/delete", material_id=unused["id"])

    assert result == {"deleted": True}
    assert await materials(panel) == [kept]


@pytest.mark.parametrize("ended", [True, False])
async def test_deleting_a_material_a_run_uses_archives_it_instead(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    ended: bool,
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    place_runs(
        hass_storage,
        run_using("benchy", "pla", ended=ended),
    )
    await add_hub(hass)

    result = await panel.call("wattbill/materials/delete", material_id="pla")

    assert result == {"deleted": False}
    [material] = await materials(panel)
    assert material["archived"] is True
    run = (await panel.call("wattbill/runs/get", run_id="benchy"))["run"]
    assert run["line_items"][1]["material_id"] == "pla"


async def test_a_used_material_that_is_already_archived_stays_archived(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla", archived=True))
    place_runs(
        hass_storage,
        run_using("benchy", "pla"),
    )
    await add_hub(hass)

    result = await panel.call("wattbill/materials/delete", material_id="pla")

    assert result == {"deleted": False}
    assert [m["id"] for m in await materials(panel)] == ["pla"]


async def test_the_catalogue_survives_a_restart(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kept = await create(panel, **PLA, vendor="eSun")
    archived = await create(panel, **PLA | {"name": "PLA red"})
    await panel.call("wattbill/materials/archive", material_id=archived["id"])
    before = await materials(panel)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert await materials(panel) == before
    assert [m["id"] for m in before] == [kept["id"], archived["id"]]


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("update", {"material": {}}),
        ("archive", {}),
        ("restore", {}),
        ("delete", {}),
    ],
)
async def test_an_unknown_material_is_not_found(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    command: str,
    data: dict[str, Any],
) -> None:
    await add_hub(hass)

    error = await panel.error(
        f"wattbill/materials/{command}", material_id="nope", **data
    )

    assert error["code"] == "not_found"


async def test_every_open_panel_sees_catalogue_changes(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_admin_user: MockUser,
) -> None:
    entry = await add_hub(hass)
    other = connect_panel(hass_admin_user)
    await other.subscribe("wattbill/catalog/subscribe")
    assert await other.event() == {"materials": [], "tags": [], "templates": []}

    created = await create(panel, **PLA)
    assert await other.event() == {"materials": [created]}
    archived = await panel.call("wattbill/materials/archive", material_id=created["id"])
    assert await other.event() == {"materials": [archived["material"]]}
    # Subscriptions outlive a reload of the hub entry.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await panel.call("wattbill/materials/delete", material_id=created["id"])
    assert await other.event() == {"materials": []}


async def test_a_new_subscriber_first_gets_the_whole_catalogue(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"), stored_material("petg"))
    await add_hub(hass)

    await panel.subscribe("wattbill/catalog/subscribe")

    first = await panel.event()
    assert [m["id"] for m in first["materials"]] == ["pla", "petg"]
    assert first["materials"][0]["price_per_gram"] == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("wattbill/catalog/subscribe", {}),
        ("wattbill/materials/list", {}),
        ("wattbill/materials/types", {}),
        ("wattbill/materials/create", {"material": PLA}),
        ("wattbill/materials/update", {"material_id": "pla", "material": {}}),
        ("wattbill/materials/archive", {"material_id": "pla"}),
        ("wattbill/materials/restore", {"material_id": "pla"}),
        ("wattbill/materials/delete", {"material_id": "pla"}),
    ],
)
async def test_only_admins_use_the_catalogue(
    hass: HomeAssistant,
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    hass_storage: dict[str, Any],
    command: str,
    data: dict[str, Any],
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_hub(hass)
    user = connect_panel(hass_read_only_user)

    error = await user.error(command, **data)

    assert error["code"] == "unauthorized"
