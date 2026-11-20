"""Slot attribution: a multi-material unit's loaded Slots pick the Materials a Run used."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub, configure, start_reconfigure
from .stored import place_materials, stored_material
from .test_device_flow import suggested
from .test_lifecycle import start_coinop, stop_coinop
from .test_material_usage import (
    GRAMS_PER_METRE,
    MATERIAL_USED,
    PETG,
    PETG_GRAMS_PER_METRE,
    add_measuring_device,
    material_items,
    print_one_metre,
    set_usage,
)
from .test_runs import set_status, stored_runs, value
from .websocket import PanelClient

SLOTS = [f"sensor.ace_slot_{number}" for number in range(1, 5)]
LOADED = "sensor.ace_loaded_slot"
RED_PLA = stored_material("red-pla", name="Red PLA", colour="#ff0000")


async def load(hass: HomeAssistant, number: int | str) -> None:
    hass.states.async_set(LOADED, str(number))
    await hass.async_block_till_done()


async def fill(
    hass: HomeAssistant, number: int, material_type: str, colour: Any = None
) -> None:
    """Put a spool into the Slot, as the integration reports it."""
    hass.states.async_set(SLOTS[number - 1], material_type, {"color_hex": colour})
    await hass.async_block_till_done()


async def add_ace_device(
    hass: HomeAssistant, panel: PanelClient, *, default: str | None = "pla"
) -> ConfigEntry:
    """A measuring Device with a four-Slot unit whose colour attribute is color_hex."""
    return await add_measuring_device(
        hass,
        panel,
        default=default,
        slots=SLOTS,
        colour_attribute="color_hex",
        loaded_slot=LOADED,
    )


def evidence(item: dict[str, Any]) -> list[tuple[int, str | None, str | None]]:
    return [(slot["number"], slot["type"], slot["colour"]) for slot in item["slots"]]


async def test_the_slots_are_stored_in_order_with_the_job(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    device = await add_device(
        hass,
        entry,
        slots=[SLOTS[2], SLOTS[0]],
        colour_attribute="color_hex",
        loaded_slot=LOADED,
    )

    assert device.data["job"] == {
        "entity_id": None,
        "attribute": None,
        "material": None,
        "slots": [SLOTS[2], SLOTS[0]],
        "colour_attribute": "color_hex",
        "loaded_slot": LOADED,
    }


async def test_reconfigure_offers_the_slots_as_stored(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    device = await add_device(
        hass, entry, slots=SLOTS, colour_attribute="color", loaded_slot=LOADED
    )

    menu = await start_reconfigure(hass, entry, device)
    result = await configure(hass, menu, {"next_step_id": "job"})

    assert suggested(result, "slots") == SLOTS
    assert suggested(result, "colour_attribute") == "color"
    assert suggested(result, "loaded_slot") == LOADED
    result = await configure(hass, result, {"slots": SLOTS[:2], "loaded_slot": LOADED})
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()
    job = entry.subentries[device.subentry_id].data["job"]
    assert (job["slots"], job["colour_attribute"]) == (SLOTS[:2], None)


async def test_a_loaded_slot_is_matched_by_type_and_colour(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"), RED_PLA)
    await fill(hass, 1, "PETG", "#000000")
    await fill(hass, 2, "pla", "#FF0000")
    await load(hass, 2)
    await add_ace_device(hass, panel)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_usage(hass, 1000)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["material_id"] == "red-pla"
    assert item["quantity"] == pytest.approx(GRAMS_PER_METRE)
    assert evidence(item) == [(2, "pla", "#ff0000")]
    assert run["flags"] == []


async def test_a_type_without_its_colour_takes_the_types_default_material(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(
        hass_storage,
        stored_material("pla"),
        RED_PLA,
        stored_material("any-petg", type="PETG", density=1.27, default_for_type=True),
    )
    await fill(hass, 1, "PETG ", "#123456")
    await load(hass, 1)
    await add_ace_device(hass, panel)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["material_id"] == "any-petg"
    assert run["flags"] == []


async def test_an_unmatched_slot_falls_back_to_the_default_material_with_a_flag(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(
        hass_storage,
        stored_material("pla"),
        stored_material("old-tpu", type="TPU", default_for_type=True, archived=True),
    )
    await fill(hass, 3, "TPU", [0, 0, 255])
    await load(hass, 3)
    await add_ace_device(hass, panel)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["material_id"] == "pla"
    assert evidence(item) == [(3, "TPU", "#0000ff")]
    assert run["flags"] == ["slot_fallback"]


async def test_without_a_match_or_default_the_material_is_missing(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await fill(hass, 1, "ASA")
    await load(hass, 1)
    await add_ace_device(hass, panel, default=None)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["material_id"], item["quantity"], item["length"]) == (None, None, 1000)
    assert evidence(item) == [(1, "ASA", None)]
    assert run["flags"] == ["material_missing"]


@pytest.mark.parametrize("loaded", ["0", "5", "-1", "none"])
async def test_a_loaded_slot_outside_the_slots_is_no_slot(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    loaded: str,
) -> None:
    place_materials(hass_storage, stored_material("pla"), RED_PLA)
    await fill(hass, 1, "PLA", "#ff0000")
    await load(hass, loaded)
    await add_ace_device(hass, panel)

    await print_one_metre(hass, clock)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["material_id"], item["slots"]) == ("pla", [])
    assert run["flags"] == []


async def split_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> dict[str, Any]:
    """1 m printed: 40 running minutes from a PETG Slot, 60 from a red PLA one."""
    place_materials(
        hass_storage, stored_material("pla"), RED_PLA, PETG | {"default_for_type": True}
    )
    await fill(hass, 1, "PETG", "#000000")
    await fill(hass, 2, "PLA", "#ff0000")
    await fill(hass, 3, "PLA", "#ffffff")
    await load(hass, 1)
    await add_ace_device(hass, panel)

    await set_status(hass, "printing")
    await clock.advance(minutes=20)
    await set_status(hass, "paused")
    await clock.advance(minutes=10)
    # Only loaded while paused: it printed nothing.
    await load(hass, 3)
    await clock.advance(minutes=10)
    await load(hass, 2)
    await clock.advance(minutes=10)
    await set_status(hass, "printing")
    await clock.advance(minutes=60)
    await load(hass, 1)
    await clock.advance(minutes=20)
    await set_usage(hass, 1000)
    await set_status(hass, "finished")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail: dict[str, Any] = (await panel.call("coinop/runs/get", run_id=run["id"]))[
        "run"
    ]
    return detail


async def test_several_slots_split_the_measured_total_by_running_time(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await split_run(hass, clock, panel, hass_storage)

    petg, red = material_items(run)
    assert (petg["material_id"], petg["share"], petg["length"]) == (
        "petg",
        pytest.approx(0.4),
        pytest.approx(400),
    )
    assert petg["quantity"] == pytest.approx(0.4 * PETG_GRAMS_PER_METRE)
    assert evidence(petg) == [(1, "PETG", "#000000")]
    assert (red["material_id"], red["share"], red["length"]) == (
        "red-pla",
        pytest.approx(0.6),
        pytest.approx(600),
    )
    assert evidence(red) == [(2, "PLA", "#ff0000")]
    assert run["flags"] == ["estimated_split"]
    assert run["usage"]["value"] == 1000
    assert value(hass, MATERIAL_USED) == pytest.approx(
        0.4 * PETG_GRAMS_PER_METRE + 0.6 * GRAMS_PER_METRE
    )


async def test_slots_holding_the_same_material_make_one_line_item(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await fill(hass, 1, "PLA", "#000000")
    await fill(hass, 2, "PLA", "#ffffff")
    await load(hass, 1)
    await add_ace_device(hass, panel)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await load(hass, 2)

    await clock.advance(minutes=30)
    await set_usage(hass, 1000)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["material_id"], item["share"], item["length"]) == ("pla", None, 1000)
    assert evidence(item) == [(1, "PLA", "#000000"), (2, "PLA", "#ffffff")]
    assert run["flags"] == ["slot_fallback"]


async def test_split_line_items_are_corrected_independently(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await split_run(hass, clock, panel, hass_storage)
    petg, red = material_items(run)

    result = await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=red["id"],
        quantity=1,
    )

    after_petg, after_red = material_items(result["run"])
    assert after_petg == petg
    assert after_red["quantity"] == 1
    assert after_red["computed"]["quantity"] == pytest.approx(0.6 * GRAMS_PER_METRE)
    assert result["run"]["usage"] == run["usage"]


async def test_the_loaded_slots_survive_a_restart(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"), RED_PLA)
    await fill(hass, 1, "PLA", "#ff0000")
    await fill(hass, 2, "ASA")
    await load(hass, 1)
    entry = await add_ace_device(hass, panel)
    await set_status(hass, "printing")
    await clock.advance(minutes=45)
    await stop_coinop(hass, entry)

    await load(hass, 2)
    await clock.advance(minutes=1)
    await start_coinop(hass, entry)
    await clock.advance(minutes=14)
    await set_usage(hass, 1000)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    red, fallback = material_items(run)
    assert (red["material_id"], red["share"]) == ("red-pla", pytest.approx(0.75))
    assert (fallback["material_id"], fallback["share"]) == ("pla", pytest.approx(0.25))
    assert run["flags"] == ["estimated_split", "slot_fallback"]
    assert run["loaded_slots"] == []


async def test_a_slot_without_a_report_yet_counts_from_its_first_one(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"), RED_PLA)
    await fill(hass, 2, STATE_UNAVAILABLE)
    await load(hass, 2)
    await add_ace_device(hass, panel)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await fill(hass, 2, "PLA", "#FF0000")
    await clock.advance(minutes=10)
    await fill(hass, 2, STATE_UNAVAILABLE)
    await load(hass, STATE_UNAVAILABLE)

    await clock.advance(minutes=20)
    await set_usage(hass, 1000)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["material_id"], item["share"]) == ("red-pla", None)
    assert run["flags"] == []
