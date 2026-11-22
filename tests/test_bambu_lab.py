"""The Bambu Lab profile: a P1S with an AMS added from greghesp/ha-bambulab."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

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
from .registry import HaDevice, add_bambu_lab
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": ["running", "prepare"],
    "paused": ["pause"],
    "finished": ["finish"],
    "cancelled": ["failed"],
    "ended": [],
    "fault": [],
    "ignored": ["idle", "init", "slicing", "offline", "unknown"],
}


async def test_quick_start_adds_a_bambu_lab_printer_with_every_input(
    hass: HomeAssistant,
) -> None:
    printer = add_bambu_lab(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    # The AMS has no Status of its own, so it is no Device.
    assert offered(result) == [
        {"value": printer.device.id, "label": "P1S · Bambu Lab"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"] == {
        "entity_id": printer["subtask_name"],
        "attribute": None,
        "material": {
            "entity_id": printer["print_weight"],
            "attribute": None,
            "unit": "g",
        },
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["camera"],
        "snapshot": True,
    }


async def test_manual_setup_comes_pre_filled_from_a_bambu_lab_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_bambu_lab(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    # The weight reports g itself, so no unit step.
    assert shown == ["status", "mapping", "job", "images", "progress"]
    data = subentry.data
    assert data["status"] == {"entity_id": printer["print_status"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["subtask_name"]
    assert data["job"]["material"] == {
        "entity_id": printer["print_weight"],
        "attribute": None,
        "unit": "g",
    }
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["camera"],
        "snapshot": True,
    }


async def test_a_bambu_lab_printer_without_a_camera_entity_has_no_snapshot(
    hass: HomeAssistant,
) -> None:
    printer = add_bambu_lab(hass, camera=False)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    # Its chamber picture as an image entity is neither camera nor Thumbnail.
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": None,
        "snapshot": False,
    }


async def test_a_disabled_print_weight_is_not_pre_filled(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_bambu_lab(hass)
    entity_registry.async_update_entity(
        printer["print_weight"], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "images", "progress"]
    assert subentry.data["job"]["material"] is None


async def set_weight(hass: HomeAssistant, printer: HaDevice, grams: float) -> None:
    hass.states.async_set(
        printer["print_weight"], str(grams), {"unit_of_measurement": "g"}
    )
    await hass.async_block_till_done()


async def test_a_bambu_lab_print_is_one_run_from_its_preparation_to_its_finish(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_bambu_lab(hass)
    await report_status(hass, printer["print_status"], "idle")
    hass.states.async_set(printer["subtask_name"], "Benchy")
    await set_weight(hass, printer, 31.4)
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    # One update of the integration writes the print status before the job's name.
    hass.states.async_set(printer["print_status"], "prepare")
    hass.states.async_set(printer["subtask_name"], "Gear_Set")
    await set_weight(hass, printer, 0)
    await clock.advance(minutes=5)
    # The weight of the 3MF arrives once the printer has downloaded it.
    await set_weight(hass, printer, 12.5)
    await clock.advance(minutes=5)
    await report_status(hass, printer["print_status"], "running")
    await clock.advance(hours=1)
    await report_status(hass, printer["print_status"], "finish")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "idle")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["ended"] == at(minutes=70)
    assert run["outcome"] == "completed"
    assert run["job_name"] == "Gear_Set"
    assert (run["usage"]["value"], run["usage"]["unit"]) == (12.5, "g")


async def test_a_paused_bambu_lab_print_that_is_stopped_is_cancelled(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_bambu_lab(hass)
    await report_status(hass, printer["print_status"], "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["print_status"], "running")
    await clock.advance(minutes=30)
    await report_status(hass, printer["print_status"], "pause")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "running")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "failed")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [{"start": at(minutes=30), "end": at(minutes=40)}]
    assert run["ended"] == at(minutes=50)
    assert run["outcome"] == "cancelled"


async def test_a_bambu_lab_printer_going_offline_doesnt_end_its_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_bambu_lab(hass)
    await report_status(hass, printer["print_status"], "idle")
    hass.states.async_set(printer["subtask_name"], "Benchy")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["print_status"], "running")
    await clock.advance(minutes=30)
    await report_status(hass, printer["print_status"], "offline")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_status"], "running")
    await clock.advance(minutes=30)
    await report_status(hass, printer["print_status"], "finish")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["ended"] == at(minutes=70)
    assert run["outcome"] == "completed"


async def test_detect_again_re_applies_a_bambu_lab_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_bambu_lab(hass)
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
    assert data["job"]["entity_id"] == printer["subtask_name"]
    assert data["job"]["material"]["entity_id"] == printer["print_weight"]
    assert data["images"] == {
        "thumbnail": printer["cover_image"],
        "camera": printer["camera"],
        "snapshot": True,
    }
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
