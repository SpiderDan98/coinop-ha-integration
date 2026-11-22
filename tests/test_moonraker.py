"""The Moonraker profile: a Klipper printer added from moonraker-home-assistant."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

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
from .registry import HaDevice, add_moonraker
from .test_integration_profiles import accepted, walk_pre_filled
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": ["printing"],
    "paused": ["paused"],
    "finished": ["complete"],
    "cancelled": ["cancelled"],
    "ended": ["standby"],
    "fault": ["error"],
    "ignored": [],
}


async def test_quick_start_adds_a_moonraker_printer_with_every_input(
    hass: HomeAssistant,
) -> None:
    printer = add_moonraker(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": printer.device.id, "label": "Voron 2.4 · Moonraker"},
        {"value": "manual", "label": "manual"},
    ]
    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["status"] == {"entity_id": printer["print_state"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"] == {
        "entity_id": printer["filename"],
        "attribute": None,
        "material": {
            "entity_id": printer["filament_used"],
            "attribute": None,
            "unit": "m",
        },
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert data["images"] == {
        "thumbnail": printer["thumbnail"],
        "camera": printer["Chamber_0"],
        "snapshot": True,
    }


async def test_manual_setup_comes_pre_filled_from_a_moonraker_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_moonraker(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    # The filament reports m itself, so no unit step.
    assert shown == ["status", "mapping", "job", "images", "progress"]
    data = subentry.data
    assert data["status"] == {"entity_id": printer["print_state"], "attribute": None}
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["filename"]
    assert data["job"]["material"] == {
        "entity_id": printer["filament_used"],
        "attribute": None,
        "unit": "m",
    }
    assert data["images"] == {
        "thumbnail": printer["thumbnail"],
        "camera": printer["Chamber_0"],
        "snapshot": True,
    }


async def test_a_moonraker_printer_without_a_webcam_has_no_camera(
    hass: HomeAssistant,
) -> None:
    printer = add_moonraker(hass, webcam=False)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    # The preview is a camera too, but never the one that photographs the print.
    assert data["images"] == {
        "thumbnail": printer["thumbnail"],
        "camera": None,
        "snapshot": False,
    }


async def test_a_disabled_moonraker_webcam_is_not_pre_filled(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_moonraker(hass)
    entity_registry.async_update_entity(
        printer["Chamber_0"], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    assert subentry.data["images"]["camera"] is None


async def set_filament(hass: HomeAssistant, printer: HaDevice, metres: float) -> None:
    hass.states.async_set(
        printer["filament_used"], str(metres), {"unit_of_measurement": "m"}
    )
    await hass.async_block_till_done()


async def idle_printer(hass: HomeAssistant, printer: HaDevice) -> None:
    """A printer in standby with the lifetime total far above any one print."""
    await report_status(hass, printer["print_state"], "standby")
    hass.states.async_set(printer["filename"], "")
    hass.states.async_set(printer["state"], "ready")
    hass.states.async_set(
        printer["total_filament_used"], "1523.7", {"unit_of_measurement": "m"}
    )
    await set_filament(hass, printer, 0)


@pytest.mark.parametrize(
    ("ending", "outcome"), [("complete", "completed"), ("cancelled", "cancelled")]
)
async def test_a_moonraker_print_is_one_run_with_its_outcome(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    ending: str,
    outcome: str,
) -> None:
    printer = add_moonraker(hass)
    await idle_printer(hass, printer)
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    hass.states.async_set(printer["filename"], "Gear_Set.gcode")
    await report_status(hass, printer["print_state"], "printing")
    await clock.advance(minutes=30)
    await set_filament(hass, printer, 2.1)
    await report_status(hass, printer["print_state"], "paused")
    await clock.advance(minutes=10)
    await report_status(hass, printer["print_state"], "printing")
    await clock.advance(minutes=30)
    await set_filament(hass, printer, 4.25)
    await report_status(hass, printer["print_state"], ending)
    await clock.advance(minutes=10)
    await idle_printer(hass, printer)

    [run] = stored_runs(hass_storage)
    assert run["started"] == at()
    assert run["ended"] == at(minutes=70)
    assert run["pauses"] == [{"start": at(minutes=30), "end": at(minutes=40)}]
    assert run["outcome"] == outcome
    assert run["job_name"] == "Gear_Set.gcode"
    assert (run["usage"]["value"], run["usage"]["unit"]) == (4250, "mm")


async def test_a_moonraker_print_in_error_is_flagged_and_ended_by_the_standby_after_it(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """Klipper stays in `error` until it is reset, which is `standby`."""
    printer = add_moonraker(hass)
    await idle_printer(hass, printer)
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    hass.states.async_set(printer["filename"], "Benchy.gcode")
    await report_status(hass, printer["print_state"], "printing")
    await clock.advance(minutes=30)
    # The printer's own state goes too, but the Run follows the print's.
    hass.states.async_set(printer["state"], "shutdown")
    await report_status(hass, printer["print_state"], "error")
    await clock.advance(minutes=10)
    await idle_printer(hass, printer)
    await clock.advance(minutes=10)
    hass.states.async_set(printer["filename"], "Cube.gcode")
    await report_status(hass, printer["print_state"], "printing")
    await clock.advance(minutes=30)
    await report_status(hass, printer["print_state"], "complete")
    await clock.advance(minutes=10)

    benchy, cube = stored_runs(hass_storage)
    assert benchy["job_name"] == "Benchy.gcode"
    assert (benchy["ended"], benchy["outcome"]) == (at(minutes=40), "unknown")
    assert benchy["pauses"] == [{"start": at(minutes=30), "end": at(minutes=40)}]
    assert "fault" in benchy["flags"]
    assert (cube["job_name"], cube["outcome"]) == ("Cube.gcode", "completed")
    assert cube["started"] == at(minutes=50)
    assert "fault" not in cube["flags"]


async def test_detect_again_re_applies_a_moonraker_printers_inputs(
    hass: HomeAssistant,
) -> None:
    printer = add_moonraker(hass)
    hass.states.async_set(ENERGY, "1", {"unit_of_measurement": "kWh"})
    hass.states.async_set(PRICE, "0.25", {"unit_of_measurement": "EUR/kWh"})
    entry = await add_hub(hass)
    subentry = await add_device(
        hass,
        entry,
        printer=printer.device.id,
        status=printer["state"],
        mapping={"running": ["ready"], "ended": ["shutdown"]},
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
    assert data["status"]["entity_id"] == printer["print_state"]
    assert data["mapping"] == MAPPING
    assert data["job"]["entity_id"] == printer["filename"]
    assert data["job"]["material"]["entity_id"] == printer["filament_used"]
    assert data["images"] == {
        "thumbnail": printer["thumbnail"],
        "camera": printer["Chamber_0"],
        "snapshot": True,
    }
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
