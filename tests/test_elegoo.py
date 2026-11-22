"""The Elegoo profile: a Centauri Carbon and a Saturn added from
danielcherubini/elegoo-homeassistant."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .clock import Clock
from .devices import (
    ENERGY,
    POWER,
    PRICE,
    add_device,
    add_hub,
    configure,
    report_status,
    start_reconfigure,
)
from .registry import add_elegoo
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": [
        "printing",
        "printing_recovery",
        "recovery",
        "homing",
        "dropping",
        "lifting",
        "preheating",
        "leveling",
        "loading",
        "printers_checking",
        "print_started",
        "resuming",
        "resonance_testing",
        "auto_leveling_completed",
        "preheating_completed",
        "homing_completed",
        "resonance_testing_completed",
        "auto_feeding",
        "filament_unloading",
    ],
    "paused": [
        "pausing",
        "paused",
        "filament_unload_paused",
        "filament_unload_abnormal",
    ],
    "finished": ["complete"],
    "cancelled": ["stopping", "stopped"],
    "ended": [],
    "fault": ["error"],
    "ignored": ["idle", "file_checking", "unrecognized"],
}


async def test_quick_start_adds_an_elegoo_printer_with_every_input(
    hass: HomeAssistant,
) -> None:
    printer = add_elegoo(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": printer.device.id, "label": "Centauri Carbon · Elegoo"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"] == {
        "entity_id": printer["filename"],
        "attribute": None,
        "material": {
            "entity_id": printer["current_extrusion"],
            "attribute": None,
            "unit": "mm",
        },
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["chamber_camera"],
        "snapshot": True,
    }


async def test_a_resin_elegoo_printer_has_no_material_used(
    hass: HomeAssistant,
) -> None:
    printer = add_elegoo(hass, resin=True)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["filename"]
    assert data["job"]["material"] is None
    assert data["images"]["thumbnail"] == printer["cover_image"]


async def test_an_elegoo_printer_without_a_cover_image_has_the_rest_pre_filled(
    hass: HomeAssistant,
) -> None:
    printer = add_elegoo(hass, cover_image=False)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "images", "progress"]
    assert subentry.data["job"]["material"]["entity_id"] == printer["current_extrusion"]
    assert subentry.data["images"] == {
        "thumbnail": None,
        "camera": printer["chamber_camera"],
        "snapshot": True,
    }


async def test_manual_setup_comes_pre_filled_from_an_elegoo_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_elegoo(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    # The extrusion reports mm itself, so no unit step.
    assert shown == ["status", "mapping", "job", "images", "progress"]
    data = subentry.data
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["filename"]
    assert data["job"]["material"] == {
        "entity_id": printer["current_extrusion"],
        "attribute": None,
        "unit": "mm",
    }
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["chamber_camera"],
        "snapshot": True,
    }


async def test_an_elegoo_print_parked_on_its_milestones_is_one_finished_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_elegoo(hass)
    await report_status(hass, printer["print_status"], "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["print_status"], "file_checking")
    hass.states.async_set(printer["filename"], "Gear_Set.gcode")
    await clock.advance(seconds=5)
    await report_status(hass, printer["print_status"], "print_started")
    await clock.advance(minutes=5)
    # The Centauri Carbon may stay on a milestone like this for the whole print.
    await report_status(hass, printer["print_status"], "preheating_completed")
    await clock.advance(hours=1)
    hass.states.async_set(
        printer["current_extrusion"], "5230.5", {"unit_of_measurement": "mm"}
    )
    await report_status(hass, printer["print_status"], "complete")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "idle")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at(seconds=5)
    assert run["ended"] == at(hours=1, minutes=5, seconds=5)
    assert run["outcome"] == "completed"
    assert run["job_name"] == "Gear_Set.gcode"
    assert (run["usage"]["value"], run["usage"]["unit"]) == (5230.5, "mm")


async def test_a_stopped_elegoo_print_is_cancelled(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_elegoo(hass, resin=True)
    await report_status(hass, printer["print_status"], "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["print_status"], "printing")
    await clock.advance(minutes=30)
    await report_status(hass, printer["print_status"], "pausing")
    await clock.advance(seconds=10)
    await report_status(hass, printer["print_status"], "paused")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "lifting")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "stopping")
    await clock.advance(seconds=20)
    await report_status(hass, printer["print_status"], "stopped")
    await clock.advance(minutes=1)
    await report_status(hass, printer["print_status"], "idle")

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [
        {"start": at(minutes=30), "end": at(minutes=40, seconds=10)}
    ]
    assert run["ended"] == at(minutes=50, seconds=10)
    assert run["outcome"] == "cancelled"


async def test_detect_again_re_applies_an_elegoo_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_elegoo(hass)
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
    assert data["job"]["entity_id"] == printer["filename"]
    assert data["job"]["material"]["entity_id"] == printer["current_extrusion"]
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["chamber_camera"],
        "snapshot": True,
    }
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
