"""The PrusaLink profile: an MK4 added from Home Assistant's PrusaLink integration."""

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
from .registry import add_prusalink
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": ["printing"],
    "paused": ["paused", "attention"],
    "finished": ["finished"],
    "cancelled": ["stopped"],
    "ended": [],
    "fault": ["error"],
    "ignored": ["idle", "ready", "busy"],
}
PROGRESS = {
    "remaining_time": "sensor.prusa_mk4_job_finish",
    "progress": "sensor.prusa_mk4_job_progress",
    "expected_energy": None,
}


async def test_quick_start_adds_a_prusalink_printer_with_its_job_preview(
    hass: HomeAssistant,
) -> None:
    printer = add_prusalink(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": printer.device.id, "label": "Prusa MK4 · PrusaLink"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)
    assert data["progress"] == PROGRESS

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["printer.state"], "attribute": None}
    assert data["mapping"] == MAPPING
    # The integration reports no Material used.
    assert data["job"] == {
        "entity_id": printer["job.filename"],
        "attribute": None,
        "material": None,
        "planned_material": None,
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    # The job preview is a camera, so the Thumbnail; there is no webcam.
    assert data["images"] == {
        "thumbnail": printer["job_preview"],
        "camera": None,
        "snapshot": False,
    }


async def test_manual_setup_comes_pre_filled_from_a_prusalink_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_prusalink(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "images", "progress"]
    data = subentry.data
    assert data["progress"] == PROGRESS
    assert data["status"] == {"entity_id": printer["printer.state"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["job.filename"]
    assert data["job"]["material"] is None
    assert data["images"] == {
        "thumbnail": printer["job_preview"],
        "camera": None,
        "snapshot": False,
    }


async def test_a_disabled_job_preview_is_not_pre_filled(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_prusalink(hass)
    entity_registry.async_update_entity(
        printer["job_preview"], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    assert subentry.data["images"]["thumbnail"] is None


async def test_a_prusalink_print_that_asks_for_attention_pauses_and_continues(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_prusalink(hass)
    await report_status(hass, printer["printer.state"], "idle")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["printer.state"], "busy")
    await clock.advance(minutes=1)
    hass.states.async_set(printer["job.filename"], "Benchy.bgcode")
    await report_status(hass, printer["printer.state"], "printing")
    await clock.advance(minutes=30)
    # A filament runout.
    await report_status(hass, printer["printer.state"], "attention")
    await clock.advance(minutes=10)
    await report_status(hass, printer["printer.state"], "printing")
    await clock.advance(minutes=20)
    await report_status(hass, printer["printer.state"], "finished")
    await clock.advance(minutes=10)
    await report_status(hass, printer["printer.state"], "idle")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at(minutes=1)
    assert run["pauses"] == [{"start": at(minutes=31), "end": at(minutes=41)}]
    assert run["ended"] == at(minutes=61)
    assert run["outcome"] == "completed"
    assert run["job_name"] == "Benchy.bgcode"


async def test_a_stopped_prusalink_print_is_cancelled(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_prusalink(hass)
    await report_status(hass, printer["printer.state"], "ready")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    await report_status(hass, printer["printer.state"], "printing")
    await clock.advance(minutes=30)
    await report_status(hass, printer["printer.state"], "paused")
    await clock.advance(minutes=10)
    await report_status(hass, printer["printer.state"], "stopped")
    await clock.advance(minutes=10)
    await report_status(hass, printer["printer.state"], "idle")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(minutes=40)
    assert run["outcome"] == "cancelled"


async def test_detect_again_re_applies_a_prusalink_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_prusalink(hass)
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
    assert shown == ["status", "mapping", "job", "images", "progress"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["progress"] == PROGRESS
    assert data["status"]["entity_id"] == printer["printer.state"]
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["job.filename"]
    assert data["images"]["thumbnail"] == printer["job_preview"]
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
