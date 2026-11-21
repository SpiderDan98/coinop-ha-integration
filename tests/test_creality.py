"""The Creality profile: a K1C added from 3dg1luk43/ha_creality_ws."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from .clock import Clock
from .creality import add_creality
from .devices import (
    ENERGY,
    POWER,
    PRICE,
    add_device,
    add_hub,
    configure,
    start_reconfigure,
)
from .registry import HaDevice
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

GEAR_SET = "/usr/data/printer_data/gcodes/Gear_Set.gcode"

MAPPING = {
    "running": ["printing"],
    "paused": ["paused"],
    "finished": ["completed"],
    "cancelled": ["stopped"],
    "ended": [],
    "fault": ["error"],
    "ignored": ["processing", "self-testing", "idle", "off", "unknown"],
}


async def test_quick_start_adds_a_creality_printer_with_every_input(
    hass: HomeAssistant,
) -> None:
    printer = add_creality(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": printer.device.id, "label": "K1C · Creality"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"] == {
        "entity_id": printer["print_status"],
        "attribute": "file",
        "material": {
            "entity_id": printer["used_material_length"],
            "attribute": None,
            "unit": "cm",
        },
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert data["images"] == {
        "thumbnail": printer["current_print_preview"],
        "camera": printer["camera"],
        "snapshot": True,
    }


async def set_print(
    hass: HomeAssistant, printer: HaDevice, status: str, file: str = ""
) -> None:
    hass.states.async_set(printer["print_status"], status, {"file": file})
    await hass.async_block_till_done()


async def test_a_creality_print_is_one_run_named_after_its_file(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_creality(hass)
    await set_print(hass, printer, "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await set_print(hass, printer, "processing", GEAR_SET)
    await clock.advance(seconds=1)
    await set_print(hass, printer, "printing", GEAR_SET)
    await clock.advance(hours=1)
    hass.states.async_set(
        printer["used_material_length"], "412.5", {"unit_of_measurement": "cm"}
    )
    await set_print(hass, printer, "completed", GEAR_SET)
    await clock.advance(minutes=10)
    await set_print(hass, printer, "idle")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at(seconds=1)
    assert run["ended"] == at(hours=1, seconds=1)
    assert run["outcome"] == "completed"
    assert run["job_name"] == GEAR_SET
    assert run["name"] == "Gear Set"
    assert (run["usage"]["value"], run["usage"]["unit"]) == (4125.0, "mm")


async def test_a_stopped_creality_print_is_cancelled_and_its_idling_opens_no_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_creality(hass)
    await set_print(hass, printer, "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await set_print(hass, printer, "printing", GEAR_SET)
    await clock.advance(minutes=30)
    await set_print(hass, printer, "paused", GEAR_SET)
    await clock.advance(minutes=10)
    await set_print(hass, printer, "stopped", GEAR_SET)
    await clock.advance(seconds=5)
    # A cancelled job idles in `processing` until the next one.
    await set_print(hass, printer, "processing", GEAR_SET)
    await clock.advance(hours=1)

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [{"start": at(minutes=30), "end": at(minutes=40)}]
    assert run["ended"] == at(minutes=40)
    assert run["outcome"] == "cancelled"


async def test_manual_setup_comes_pre_filled_from_a_creality_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_creality(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    # The material length reports cm itself, so no unit step.
    assert shown == ["status", "mapping", "job", "images"]
    data = subentry.data
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert (data["job"]["entity_id"], data["job"]["attribute"]) == (
        printer["print_status"],
        "file",
    )
    assert data["job"]["material"] == {
        "entity_id": printer["used_material_length"],
        "attribute": None,
        "unit": "cm",
    }
    assert data["images"] == {
        "thumbnail": printer["current_print_preview"],
        "camera": printer["camera"],
        "snapshot": True,
    }


async def test_a_creality_printer_without_a_camera_entity_has_no_snapshot(
    hass: HomeAssistant,
) -> None:
    printer = add_creality(hass, camera=False)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["images"] == {
        "thumbnail": printer["current_print_preview"],
        "camera": None,
        "snapshot": False,
    }


async def test_a_disabled_material_length_is_left_out_and_the_rest_pre_filled(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_creality(hass)
    entity_registry.async_update_entity(
        printer["used_material_length"], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "images"]
    assert subentry.data["job"]["material"] is None
    assert subentry.data["job"]["entity_id"] == printer["print_status"]
    assert subentry.data["images"]["thumbnail"] == printer["current_print_preview"]


async def test_detect_again_re_applies_a_creality_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_creality(hass)
    hass.states.async_set(ENERGY, "1", {"unit_of_measurement": "kWh"})
    hass.states.async_set(PRICE, "0.25", {"unit_of_measurement": "EUR/kWh"})
    entry = await add_hub(hass)
    subentry = await add_device(
        hass,
        entry,
        printer=printer.device.id,
        status="sensor.something_else",
        mapping={"running": ["on"], "ended": ["off"]},
        source="energy",
        meter={"entity_id": ENERGY},
        price={"entity_id": PRICE},
    )
    before = dict(entry.subentries[subentry.subentry_id].data)
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "detect"})
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "job", "images"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"]["entity_id"] == printer["print_status"]
    assert data["mapping"] == MAPPING
    assert (data["job"]["entity_id"], data["job"]["attribute"]) == (
        printer["print_status"],
        "file",
    )
    assert data["job"]["material"]["entity_id"] == printer["used_material_length"]
    assert data["images"] == {
        "thumbnail": printer["current_print_preview"],
        "camera": printer["camera"],
        "snapshot": True,
    }
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
