"""The OctoPrint profile: a printer added from Home Assistant's `octoprint` integration."""

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
from .octoprint import add_octoprint
from .registry import HaDevice
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": ["printing", "printing_sd", "starting", "starting_sd", "resuming"],
    "paused": ["pausing", "paused"],
    "finished": ["finishing"],
    "cancelled": ["cancelling"],
    "ended": ["operational"],
    "fault": ["error", "offline_after_error"],
    "ignored": [
        "open_serial",
        "detect_serial",
        "connecting",
        "offline",
        "starting_streaming",
        "printing_streaming",
        "transferring_file",
    ],
}


async def test_quick_start_adds_an_octoprint_printer_with_every_input(
    hass: HomeAssistant,
) -> None:
    printer = add_octoprint(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": printer.device.id, "label": "OctoPrint · OctoPrint"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["Current State"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"] == {
        "entity_id": printer["Current File"],
        "attribute": None,
        "material": None,
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert data["images"] == {
        "thumbnail": None,
        "camera": printer["camera"],
        "snapshot": True,
    }


async def test_renamed_octoprint_entities_are_still_found(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_octoprint(hass)
    renamed = {
        key: entity_registry.async_update_entity(
            printer[key], new_entity_id=f"{printer[key].split('.')[0]}.my_{index}"
        ).entity_id
        for index, key in enumerate(["Current State", "Current File", "camera"])
    }
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "images"]
    data = subentry.data
    assert data["status"]["entity_id"] == renamed["Current State"]
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == renamed["Current File"]
    assert data["job"]["material"] is None
    assert data["images"] == {
        "thumbnail": None,
        "camera": renamed["camera"],
        "snapshot": True,
    }


async def test_an_octoprint_printer_without_a_webcam_has_no_snapshot(
    hass: HomeAssistant,
) -> None:
    printer = add_octoprint(hass, camera=False)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["images"] == {"thumbnail": None, "camera": None, "snapshot": False}


async def added(hass: HomeAssistant, printer: HaDevice) -> HaDevice:
    await report_status(hass, printer["Current State"], "operational")
    hass.states.async_set(printer["Current File"], "benchy.gcode")
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)
    return printer


async def test_an_octoprint_print_seen_going_back_to_operational_ends_unknown(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = await added(hass, add_octoprint(hass))

    await report_status(hass, printer["Current State"], "starting")
    await clock.advance(minutes=1)
    await report_status(hass, printer["Current State"], "printing")
    await clock.advance(minutes=30)
    await report_status(hass, printer["Current State"], "pausing")
    await report_status(hass, printer["Current State"], "paused")
    await clock.advance(minutes=10)
    await report_status(hass, printer["Current State"], "resuming")
    await report_status(hass, printer["Current State"], "printing")
    await clock.advance(minutes=20)
    await report_status(hass, printer["Current State"], "operational")

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["pauses"] == [{"start": at(minutes=31), "end": at(minutes=41)}]
    assert run["ended"] == at(minutes=61)
    assert run["outcome"] == "unknown"
    assert run["job_name"] == "benchy.gcode"


async def test_an_octoprint_print_seen_finishing_is_completed(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = await added(hass, add_octoprint(hass))

    await report_status(hass, printer["Current State"], "printing")
    await clock.advance(hours=1)
    await report_status(hass, printer["Current State"], "finishing")
    await clock.advance(seconds=30)
    await report_status(hass, printer["Current State"], "operational")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(hours=1)
    assert run["outcome"] == "completed"


async def test_an_octoprint_print_seen_cancelling_is_cancelled(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = await added(hass, add_octoprint(hass))

    await report_status(hass, printer["Current State"], "printing_sd")
    await clock.advance(minutes=20)
    await report_status(hass, printer["Current State"], "cancelling")
    await clock.advance(seconds=30)
    await report_status(hass, printer["Current State"], "operational")

    [run] = stored_runs(hass_storage)
    assert run["ended"] == at(minutes=20)
    assert run["outcome"] == "cancelled"


async def test_sending_a_file_to_the_sd_card_opens_no_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = await added(hass, add_octoprint(hass))

    await report_status(hass, printer["Current State"], "starting_streaming")
    await report_status(hass, printer["Current State"], "printing_streaming")
    await clock.advance(minutes=5)
    await report_status(hass, printer["Current State"], "transferring_file")
    await clock.advance(minutes=1)
    await report_status(hass, printer["Current State"], "operational")

    assert stored_runs(hass_storage) == []


async def test_detect_again_re_applies_an_octoprint_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_octoprint(hass)
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
    assert data["status"]["entity_id"] == printer["Current State"]
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["Current File"]
    assert data["images"] == {
        "thumbnail": None,
        "camera": printer["camera"],
        "snapshot": True,
    }
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
