"""Integration Profiles: a known printer integration's Device Inputs pre-filled."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .anycubic import Printer, add_anycubic_cloud, add_anycubic_local
from .clock import Clock
from .devices import add_hub, add_printer, configure, start_add_device
from .test_device_flow import suggested
from .test_runs import stored_runs


def accepted(result: Any) -> dict[str, Any]:
    """The form submitted as pre-filled, the way a user who checks and agrees does."""
    return {
        str(key): value
        for key in result["data_schema"].schema
        if (value := suggested(result, str(key))) is not None
    }


async def walk_pre_filled(
    hass: HomeAssistant, entry: ConfigEntry, printer: Printer
) -> tuple[list[str], ConfigSubentry]:
    """Add Device accepting every pre-filled step; returns the steps shown and the Device."""
    result = await configure(
        hass,
        await start_add_device(hass, entry, printer=printer.device.id),
        {"name": "Kobra S1"},
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
        assert not result.get("errors"), result["errors"]
    assert result["step_id"] == "consumption"
    result = await configure(hass, result, {"next_step_id": "estimate"})
    result = await configure(hass, result, {"running_power": 120})
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return shown, list(entry.subentries.values())[-1]


async def test_the_local_anycubic_status_is_its_print_event(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)

    result = await configure(
        hass,
        await start_add_device(hass, entry, printer=printer.device.id),
        {"name": "Kobra S1"},
    )

    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") == "event.anycubic_kobra_s1_print_event"
    assert suggested(result, "attribute") is None


async def test_the_local_anycubic_fills_every_input(hass: HomeAssistant) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    assert shown == ["status", "mapping", "job", "material_unit", "images"]
    data = subentry.data
    assert data["printer_device_id"] == printer.device.id
    assert data["status"] == {
        "entity_id": "event.anycubic_kobra_s1_print_event",
        "attribute": None,
    }
    assert data["mapping"] == {
        "running": ["started", "resumed"],
        "paused": ["paused"],
        "finished": ["finished"],
        "cancelled": ["stopped"],
        "ended": [],
        "fault": ["error"],
        "ignored": ["clear_ready", "clear_done", "clear_failed"],
    }
    assert data["job"] == {
        "entity_id": "sensor.anycubic_kobra_s1_file_name",
        "attribute": None,
        "material": {
            "entity_id": "sensor.anycubic_kobra_s1_filament_used",
            "attribute": "length_mm",
            "unit": "mm",
        },
        "slots": [
            "sensor.ace_pro_slot_1",
            "sensor.ace_pro_slot_2",
            "sensor.ace_pro_slot_3",
            "sensor.ace_pro_slot_4",
        ],
        "colour_attribute": "color",
        "loaded_slot": "sensor.ace_pro_loaded_slot",
    }
    assert data["images"] == {
        "thumbnail": "image.anycubic_kobra_s1_object_top_view",
        "camera": "camera.anycubic_kobra_s1_camera",
        "snapshot": True,
    }


async def test_a_device_from_the_local_anycubic_records_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, printer)

    async def fire(event_type: str) -> None:
        hass.states.async_set(
            printer["print_event"],
            dt_util.utcnow().isoformat(),
            {"event_type": event_type, "filename": "benchy.gcode"},
        )
        await hass.async_block_till_done()

    hass.states.async_set(printer["filename"], "benchy")
    await fire("started")
    await clock.advance(hours=1)
    hass.states.async_set(
        printer["filament_used"], "10.12", {"length_mm": 3400, "density": 1.24}
    )
    await fire("finished")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["job_name"] == "benchy"
    assert run["usage"]["value"] == 3400
    assert run["usage"]["unit"] == "mm"


async def test_hass_anycubic_fills_every_input(hass: HomeAssistant) -> None:
    printer = add_anycubic_cloud(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, printer)

    # The Material used entity reports mm itself, so no unit step.
    assert shown == ["status", "mapping", "job", "images"]
    data = subentry.data
    assert data["status"] == {"entity_id": "sensor.kobra_s1_job_state", "attribute": None}
    assert data["mapping"] == {
        "running": ["printing", "preheating", "levelling"],
        "paused": ["paused"],
        "finished": ["finished"],
        "cancelled": ["cancelled", "failed"],
        "ended": ["idle"],
        "fault": [],
        "ignored": ["downloading", "checking", "slicing"],
    }
    assert data["job"] == {
        "entity_id": "sensor.kobra_s1_job_name",
        "attribute": None,
        "material": {
            "entity_id": "sensor.kobra_s1_job_filament_used",
            "attribute": None,
            "unit": "mm",
        },
        "slots": [
            "sensor.kobra_s1_ace_pro_ace_slot_1",
            "sensor.kobra_s1_ace_pro_ace_slot_2",
            "sensor.kobra_s1_ace_pro_ace_slot_3",
            "sensor.kobra_s1_ace_pro_ace_slot_4",
        ],
        "colour_attribute": "color_hex",
        "loaded_slot": "sensor.kobra_s1_ace_pro_ace_loaded_slot",
    }
    assert data["images"] == {
        "thumbnail": "image.kobra_s1_job_preview",
        "camera": "camera.kobra_s1_camera",
        "snapshot": True,
    }


async def test_hass_anycubics_own_cost_sensors_are_ignored(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_cloud(hass)
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    stored = str(dict(subentry.data))
    for key in ("job_energy", "job_electricity_cost", "last_job_total_cost"):
        assert printer[key] not in stored


async def test_without_the_cloud_hass_anycubic_has_no_thumbnail(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_cloud(hass, cloud=False)
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    assert subentry.data["images"]["thumbnail"] is None
    assert subentry.data["images"]["camera"] == "camera.kobra_s1_camera"


async def test_the_object_thumbnail_stands_in_for_a_missing_top_view(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass, images=("object_thumbnail",))
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    assert (
        subentry.data["images"]["thumbnail"]
        == "image.anycubic_kobra_s1_object_thumbnail"
    )


async def test_renamed_entities_are_still_found(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_anycubic_cloud(hass)
    entity_registry.async_update_entity(
        printer["job_state"], new_entity_id="sensor.my_printer_state"
    )
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(hass, entry, printer)

    assert subentry.data["status"]["entity_id"] == "sensor.my_printer_state"


async def test_an_unknown_integration_pre_fills_nothing(hass: HomeAssistant) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)

    result = await configure(
        hass,
        await start_add_device(hass, entry, printer=printer.id),
        {"name": "Kobra S1"},
    )

    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") is None
