"""Integration Profiles: a known printer integration's Device Inputs pre-filled."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .clock import Clock
from .devices import (
    ENERGY,
    PRICE,
    add_device,
    add_hub,
    add_printer,
    configure,
    start_add_device,
    start_reconfigure,
)
from .registry import HaDevice, add_anycubic_cloud, add_anycubic_local
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
    hass: HomeAssistant, entry: ConfigEntry, printer: HaDevice
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
    assert data["status"] == {
        "entity_id": "sensor.kobra_s1_job_state",
        "attribute": None,
    }
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


async def test_detect_again_is_offered_for_a_known_integration(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(hass, entry, printer)

    result = await start_reconfigure(hass, entry, subentry)

    assert result["menu_options"] == [
        "status",
        "job",
        "images",
        "consumption",
        "price",
        "detect",
        "save",
    ]


async def test_detect_again_is_not_offered_otherwise(hass: HomeAssistant) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)
    without_printer = await add_device(hass, entry, name="Plain")
    unknown = await add_device(
        hass, entry, name="Other", printer=printer.id, status="sensor.other_status"
    )

    for subentry in (without_printer, unknown):
        result = await start_reconfigure(hass, entry, subentry)
        assert "detect" not in result["menu_options"]


async def test_detect_again_repairs_the_mapping_in_one_go(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(hass, entry, printer)
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            printer[key], new_entity_id=printer[key].replace("anycubic_kobra_s1", "s1")
        ).entity_id
        for key in ("print_event", "filename", "filament_used", "camera")
    }
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "detect"})
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "job", "material_unit", "images"]
    assert result["step_id"] == "reconfigure"
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"]["entity_id"] == renamed["print_event"]
    assert data["job"]["entity_id"] == renamed["filename"]
    assert data["job"]["material"]["entity_id"] == renamed["filament_used"]
    assert data["images"]["camera"] == renamed["camera"]


async def test_detect_again_pre_fills_the_profiles_values(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_cloud(hass)
    entry = await add_hub(hass)
    subentry = await add_device(
        hass,
        entry,
        printer=printer.device.id,
        status="sensor.something_else",
        mapping={"running": ["on"], "ended": ["off"]},
        colour_attribute="colour",
    )
    menu = await start_reconfigure(hass, entry, subentry)

    status = await configure(hass, menu, {"next_step_id": "detect"})
    assert suggested(status, "entity_id") == printer["job_state"]
    mapping = await configure(hass, status, accepted(status))
    assert suggested(mapping, "running") == ["printing", "preheating", "levelling"]
    assert suggested(mapping, "ended") == ["idle"]
    job = await configure(hass, mapping, accepted(mapping))
    assert suggested(job, "colour_attribute") == "color_hex"
    assert suggested(job, "loaded_slot") == printer["ace_loaded_slot"]
    images = await configure(hass, job, accepted(job))
    assert suggested(images, "thumbnail") == printer["job_image_url"]


async def test_detect_again_leaves_consumption_and_price_alone(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_cloud(hass)
    hass.states.async_set(ENERGY, "1", {"unit_of_measurement": "kWh"})
    hass.states.async_set(PRICE, "0.25", {"unit_of_measurement": "EUR/kWh"})
    entry = await add_hub(hass)
    subentry = await add_device(
        hass,
        entry,
        printer=printer.device.id,
        source="energy",
        meter={"entity_id": ENERGY},
        price={"entity_id": PRICE},
    )
    before = dict(entry.subentries[subentry.subentry_id].data)
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "detect"})
    while result["type"] is FlowResultType.FORM:
        result = await configure(hass, result, accepted(result))
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"]["entity_id"] == printer["job_state"]
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]


async def test_an_input_the_profile_cant_find_keeps_its_value(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_cloud(hass, cloud=False)
    entry = await add_hub(hass)
    subentry = await add_device(
        hass, entry, printer=printer.device.id, thumbnail="image.my_thumbnail"
    )
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "detect"})
    while result["step_id"] != "images":
        result = await configure(hass, result, accepted(result))

    assert suggested(result, "thumbnail") == "image.my_thumbnail"
    assert suggested(result, "camera") == printer["camera"]


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
