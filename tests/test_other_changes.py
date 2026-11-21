"""Changing an Other Device later: its Type Name and what it has, in the reconfigure
menu, while no Run of it is still being recorded."""

from copy import deepcopy
from itertools import combinations
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    BASIC_DATA,
    CHOICES,
    OTHER_MAPPING,
    POWER,
    add_hub,
    add_other_device,
    change_other_device,
    configure,
    open_other,
    other_input,
    save,
    start_reconfigure,
    walk_to_mapping,
)
from .images import picture
from .stored import place_materials
from .test_device_flow import fields, offered, suggested
from .test_material_usage import material_items
from .test_measured import electricity, set_power
from .test_other_devices import (
    KILN_STATUS,
    add_kiln,
    add_pump,
    fire,
    pump,
    set_kiln,
)
from .test_other_doses import (
    BREW_DOSES,
    BREW_KETTLE_PROGRAM,
    BREW_ROWS,
    DOSE_MATERIALS,
    add_brew_kettle,
    brew,
)
from .test_other_images_and_parts import (
    KILN_CAMERA,
    KILN_THUMBNAIL,
    add_kiln_camera,
    add_kiln_thumbnail,
)
from .test_other_jobs import (
    MDF,
    PLYWOOD,
    ROUTER_JOB,
    ROUTER_USED,
    add_cnc_router,
    cut,
)
from .test_other_programs import (
    BREAD_MAKER_PROGRAM,
    BREAD_ROWS,
    add_bread_maker,
    bake,
)
from .test_other_water import (
    ON_ITS_METER,
    VALVE_WATER,
    add_irrigation,
    irrigate,
    set_valve,
    set_valve_water,
)
from .test_ovens import line_items
from .test_program_consumption import approx
from .test_program_correction import costs
from .test_runs import stored_runs
from .test_water import water
from .websocket import PanelClient

SECOND_KILN_STATUS = "sensor.second_kiln_status"


async def add_shipped(
    hass: HomeAssistant, entry: ConfigEntry, device_type: str
) -> ConfigSubentry:
    """Walk Add Device for a shipped Device Type, with nothing filled in beyond its
    Status and with no source wherever one is asked for."""
    result = await walk_to_mapping(
        hass,
        entry,
        name=device_type,
        status=f"sensor.{device_type}_status",
        device_type=device_type,
    )
    result = await configure(hass, result, OTHER_MAPPING)
    while result["type"] is not FlowResultType.CREATE_ENTRY:
        result = await configure(
            hass,
            result,
            {"next_step_id": result["menu_options"][-1]}
            if result["type"] is FlowResultType.MENU
            else {},
        )
    return list(entry.subentries.values())[-1]


async def shipped_device_types(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """The Device Types Add Device offers besides Other."""
    add_device = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": "user"}
    )
    return [t for t in offered(add_device, "device_type") if t != "other"]


async def test_only_an_other_devices_reconfigure_menu_offers_its_type_name_and_what_it_has(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    shipped = await shipped_device_types(hass, entry)
    assert len(shipped) == 8

    result = await start_reconfigure(hass, entry, kiln)
    assert result["menu_options"] == ["other", "status", "consumption", "price", "save"]
    for device_type in shipped:
        device = await add_shipped(hass, entry, device_type)
        result = await start_reconfigure(hass, entry, device)
        assert "other" not in result["menu_options"], device_type


async def test_the_entry_shows_the_type_name_and_what_the_device_has_now(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    kettle = await add_other_device(
        hass,
        entry,
        type_name="Brew kettle",
        name="Kettle",
        status="sensor.kettle_status",
        has=["program", "doses", "water", "part_count"],
        source="per_program",
    )
    laser = await add_other_device(
        hass,
        entry,
        type_name="Kiln",
        name="Laser",
        status="sensor.laser_status",
        has=["job", "images", "per_run_meters"],
    )

    nothing = await open_other(hass, entry, kiln)
    much = await open_other(hass, entry, kettle)
    rest = await open_other(hass, entry, laser)

    assert nothing["step_id"] == much["step_id"] == "other"
    assert fields(much) == ["type_name", *CHOICES]
    assert offered(much, "type_name") == ["Kiln", "Brew kettle"]
    assert [choice for choice in CHOICES if suggested(rest, choice)] == [
        "job",
        "images",
        "per_run_meters",
    ]
    assert suggested(nothing, "type_name") == "Kiln"
    assert {choice: suggested(nothing, choice) for choice in CHOICES} == dict.fromkeys(
        CHOICES, False
    )
    assert suggested(much, "type_name") == "Brew kettle"
    assert {choice: suggested(much, choice) for choice in CHOICES} == {
        "program": True,
        "doses": True,
        "water": True,
        "job": False,
        "images": False,
        "part_count": True,
        "per_run_meters": False,
    }


async def test_renaming_the_type_name_alone_moves_the_device_under_the_new_heading(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry, has=["images", "part_count"])
    [before] = (await panel.call("coinop/devices/list"))["devices"]
    assert before["type_name"] == "Kiln"

    result = await open_other(hass, entry, kiln)
    unnamed = await configure(hass, result, other_input(" ", ["images", "part_count"]))
    result = await configure(
        hass, unnamed, other_input(" Pottery kiln ", ["images", "part_count"])
    )
    assert unnamed["step_id"] == "other"
    assert unnamed["errors"] == {"type_name": "type_name_required"}
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "images", "consumption", "price", "save"],
    )
    await save(hass, result)

    [after] = (await panel.call("coinop/devices/list"))["devices"]
    assert after == before | {"type_name": "Pottery kiln"}


async def test_adding_water_walks_its_source_and_price_and_the_next_run_gets_water(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(
        hass, entry=entry, has=[], source="estimate", running_power=10
    )
    await irrigate(hass, clock, start=1000, litres=120)

    result = await open_other(hass, entry, valve)
    steps = []
    for user_input in (other_input("Irrigation", ["water"]), *ON_ITS_METER):
        result = await configure(hass, result, user_input)
        steps.append(result["step_id"])
    assert steps == [
        "water",
        "water_meter",
        "water_price",
        "water_fixed_price",
        "reconfigure",
    ]
    assert result["menu_options"] == [
        "other",
        "status",
        "consumption",
        "price",
        "water",
        "water_price",
        "save",
    ]
    await save(hass, result)
    await irrigate(hass, clock, start=1120, litres=80)

    before, after = stored_runs(hass_storage)
    assert [item["kind"] for item in before["line_items"]] == ["electricity"]
    assert [item["kind"] for item in after["line_items"]] == ["electricity", "water"]
    assert water(after)["quantity"] == pytest.approx(80)
    assert water(after)["amount"] == pytest.approx(0.32)


async def test_removing_water_drops_its_sections_and_the_next_run_records_no_water(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry, source="estimate", running_power=10)
    await irrigate(hass, clock, start=1000, litres=120)

    result = await open_other(hass, entry, valve)
    result = await configure(hass, result, other_input("Irrigation"))
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "consumption", "price", "save"],
    )
    await save(hass, result)
    await irrigate(hass, clock, start=1120, litres=80)

    assert sorted(entry.subentries[valve.subentry_id].data) == sorted(
        [*BASIC_DATA, "capabilities", "type_name"]
    )
    before, after = stored_runs(hass_storage)
    assert [item["kind"] for item in before["line_items"]] == ["electricity", "water"]
    assert [item["kind"] for item in after["line_items"]] == ["electricity"]
    assert after["flags"] == []


async def test_adding_a_program_asks_a_device_on_the_estimate_for_its_electricity_again(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)

    result = await open_other(hass, entry, kiln)
    result = await configure(hass, result, other_input("Kiln", ["program"]))
    assert result["step_id"] == "program"
    result = await configure(hass, result, {})
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "per_program", "none"],
    )
    result = await configure(hass, result, {"next_step_id": "per_program"})
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "program", "consumption", "price", "save"],
    )
    await save(hass, result)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=kiln.subentry_id,
        settings={"program_defaults": {"default": {"doses": {}, "kwh": 5}}},
    )
    await fire(hass, clock)

    data = entry.subentries[kiln.subentry_id].data
    assert data["consumption"] == {"source": "per_program"}
    assert data["price"] == {"source": "fixed", "value": 0.30}
    [run] = stored_runs(hass_storage)
    assert line_items(run) == [("electricity", "program_default", 5, "kWh", 1.50)]


async def test_removing_the_program_asks_for_every_source_that_was_per_program_again(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    hass.config.currency = "EUR"
    hass.states.async_set(KILN_STATUS, "off")
    hass.states.async_set(VALVE_WATER, "1000", {"unit_of_measurement": "L"})
    entry = await add_hub(hass)
    kettle = await add_other_device(
        hass,
        entry,
        type_name="Brew kettle",
        name="Kettle",
        status=KILN_STATUS,
        has=["program", "water"],
        source="per_program",
        water="per_program",
    )

    result = await open_other(hass, entry, kettle)
    result = await configure(hass, result, other_input("Brew kettle", ["water"]))
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "estimate", "none"],
    )
    result = await configure(hass, result, {"next_step_id": "estimate"})
    result = await configure(hass, result, {"running_power": 2000})
    assert (result["step_id"], result["menu_options"]) == (
        "water",
        ["water_meter", "water_flow", "water_none"],
    )
    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": VALVE_WATER})
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "consumption", "price", "water", "water_price", "save"],
    )
    await save(hass, result)
    await set_kiln(hass, "on")
    await clock.advance(minutes=90)
    await set_valve_water(hass, 1025)
    await set_kiln(hass, "off")
    await set_valve_water(hass, 1025)

    data = entry.subentries[kettle.subentry_id].data
    assert "program" not in data
    assert (data["consumption"]["source"], data["water"]["source"]) == (
        "estimate",
        "meter",
    )
    assert data["water_price"] == {"source": "fixed", "value": 4.0}
    [run] = stored_runs(hass_storage)
    assert line_items(run) == [
        ("electricity", "estimated", 3, "kWh", 0.90),
        ("water", "measured", 25, "L", 0.10),
    ]


async def test_a_power_sensors_gaps_are_filled_from_the_average_power_only_without_a_program(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """A kiln that got its Program later and one added with it, on one power sensor."""
    await set_power(hass, 0)
    hass.states.async_set(SECOND_KILN_STATUS, "off")
    entry = await add_hub(hass)
    kiln = await add_kiln(
        hass,
        entry=entry,
        source="power",
        meter={"entity_id": POWER, "running_power": 1800},
    )
    twin = await add_kiln(
        hass,
        entry=entry,
        name="Twin",
        status=SECOND_KILN_STATUS,
        has=["program"],
        source="power",
        meter={"entity_id": POWER},
    )

    await change_other_device(hass, entry, kiln, {}, has=["program"])
    result = await start_reconfigure(hass, entry, kiln)
    result = await configure(hass, result, {"next_step_id": "consumption"})
    result = await configure(hass, result, {"next_step_id": "power"})
    assert fields(result) == ["entity_id", "attribute"]
    await set_power(hass, 1000)
    for status in (KILN_STATUS, SECOND_KILN_STATUS):
        hass.states.async_set(status, "on")
    await clock.advance(minutes=30)
    await set_power(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=30)
    await set_power(hass, 1000)
    await clock.advance(minutes=30)
    for status in (KILN_STATUS, SECOND_KILN_STATUS):
        hass.states.async_set(status, "off")
    await set_power(hass, 0)

    changed, added = (
        next(run for run in stored_runs(hass_storage) if run["device_id"] == device)
        for device in (kiln.subentry_id, twin.subentry_id)
    )
    # Without an average power the gap counts at the last power reported.
    assert electricity(added)["quantity"] == pytest.approx(1.5)
    assert electricity(changed)["quantity"] == pytest.approx(1.5)
    assert changed["flags"] == added["flags"] == ["consumption_gap"]

    await change_other_device(hass, entry, kiln, has=[])
    result = await start_reconfigure(hass, entry, kiln)
    result = await configure(hass, result, {"next_step_id": "consumption"})
    result = await configure(hass, result, {"next_step_id": "power"})
    assert fields(result) == ["entity_id", "attribute", "running_power"]
    assert suggested(result, "running_power") is None


async def test_with_an_open_run_the_entry_is_refused_and_works_once_the_run_ended(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    stored = dict(kiln.data)
    await set_kiln(hass, "on")
    await clock.advance(minutes=30)

    refused = await open_other(hass, entry, kiln)

    assert (refused["type"], refused["reason"]) == (FlowResultType.ABORT, "run_open")
    assert entry.subentries[kiln.subentry_id].data == stored
    await clock.advance(minutes=60)
    await set_kiln(hass, "off")
    [run] = stored_runs(hass_storage)
    assert line_items(run) == [("electricity", "estimated", 3, "kWh", 0.90)]
    await change_other_device(hass, entry, kiln, type_name="Oven", has=["part_count"])
    changed = await open_other(hass, entry, kiln)
    assert suggested(changed, "type_name") == "Oven"
    assert [choice for choice in CHOICES if suggested(changed, choice)] == [
        "part_count"
    ]


async def test_a_run_waiting_for_its_meters_last_report_refuses_the_entry_too(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """Until then the Run still changes: taking the water away would cost it its
    Water Line Item."""
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    await set_valve(hass, "on")
    await clock.advance(minutes=20)
    await set_valve_water(hass, 1120)
    await clock.advance(minutes=10)
    await set_valve(hass, "off")

    refused = await open_other(hass, entry, valve)
    await clock.advance(minutes=5)
    result = await open_other(hass, entry, valve)

    assert (refused["type"], refused["reason"]) == (FlowResultType.ABORT, "run_open")
    assert result["step_id"] == "other"
    [run] = stored_runs(hass_storage)
    assert (run["finalised"], water(run)["quantity"]) == (True, pytest.approx(120))


async def test_a_run_that_starts_while_the_choices_are_changed_refuses_them(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    stored = dict(valve.data)
    form = await open_other(hass, entry, valve)
    menu = await configure(
        hass, await open_other(hass, entry, valve), other_input("Irrigation")
    )
    assert menu["step_id"] == "reconfigure"
    await set_valve(hass, "on")

    submitted = await configure(hass, form, other_input("Irrigation"))
    saved = await save(hass, menu)

    for refused in (submitted, saved):
        assert (refused["type"], refused["reason"]) == (
            FlowResultType.ABORT,
            "run_open",
        )
    assert entry.subentries[valve.subentry_id].data == stored
    await clock.advance(minutes=30)
    await set_valve_water(hass, 1120)
    await set_valve(hass, "off")
    await set_valve_water(hass, 1120)
    [run] = stored_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(120)


async def test_an_open_run_refuses_the_change_while_coinop_is_not_loaded_too(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """The Run goes on when Coin-op loads again, so it must find its water."""
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    stored = dict(valve.data)
    menu = await configure(
        hass, await open_other(hass, entry, valve), other_input("Irrigation")
    )
    await set_valve(hass, "on")
    await clock.advance(minutes=20)
    await hass.config_entries.async_unload(entry.entry_id)

    opened = await open_other(hass, entry, valve)
    saved = await save(hass, menu)

    for refused in (opened, saved):
        assert (refused["type"], refused["reason"]) == (
            FlowResultType.ABORT,
            "run_open_not_loaded",
        )
    assert entry.subentries[valve.subentry_id].data == stored
    assert await hass.config_entries.async_setup(entry.entry_id)
    await clock.advance(minutes=10)
    await set_valve_water(hass, 1120)
    await set_valve(hass, "off")
    await set_valve_water(hass, 1120)
    [run] = stored_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(120)


async def test_without_readable_runs_an_unloaded_coinop_refuses_the_change_in_its_own_words(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    await hass.config_entries.async_unload(entry.entry_id)
    hass_storage["coinop.live"]["version"] += 1

    refused = await open_other(hass, entry, valve)

    assert (refused["type"], refused["reason"]) == (
        FlowResultType.ABORT,
        "runs_unreadable",
    )


async def test_leaving_halfway_through_the_sections_a_change_brings_changes_nothing(
    hass: HomeAssistant,
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry, has=[])
    stored = dict(valve.data)

    result = await open_other(hass, entry, valve)
    result = await configure(hass, result, other_input("Garden", ["water", "images"]))
    assert result["step_id"] == "images"
    result = await configure(hass, result, {})
    assert result["step_id"] == "water"
    await configure(hass, result, {"next_step_id": "water_meter"})

    assert entry.subentries[valve.subentry_id].data == stored
    result = await start_reconfigure(hass, entry, valve)
    assert result["menu_options"] == ["other", "status", "consumption", "save"]


async def test_job_and_material_goes_and_comes_back_with_its_default_material(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, MDF, PLYWOOD)
    entry = await add_hub(hass)
    router = await add_cnc_router(hass, panel, entry=entry)
    await cut(hass, clock, "Sign_Oak.gcode", grams=120)

    result = await open_other(hass, entry, router)
    result = await configure(hass, result, other_input("CNC router"))
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "consumption", "price", "save"],
    )
    await save(hass, result)
    assert "job" not in entry.subentries[router.subentry_id].data
    [without] = (await panel.call("coinop/devices/list"))["devices"]
    await cut(hass, clock, "Tray.gcode", grams=300)

    result = await open_other(hass, entry, router)
    result = await configure(hass, result, other_input("CNC router", ["job"]))
    assert result["step_id"] == "job"
    assert (suggested(result, "entity_id"), suggested(result, "slots")) == (None, None)
    result = await configure(
        hass, result, {"entity_id": ROUTER_JOB, "material_entity_id": ROUTER_USED}
    )
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "job", "consumption", "price", "save"],
    )
    await save(hass, result)
    await cut(hass, clock, "Shelf.gcode", grams=500)

    [again] = (await panel.call("coinop/devices/list"))["devices"]
    assert without["settings"]["default_material"] == "mdf"
    assert again["settings"]["default_material"] == "mdf"
    named, unnamed, named_again = stored_runs(hass_storage)
    assert [run["name"] for run in (named, unnamed, named_again)] == [
        "Sign Oak",
        None,
        "Shelf",
    ]
    assert line_items(named) == [
        ("electricity", "estimated", 0.3, "kWh", 0.09),
        ("material", None, 120, "g", 0.60),
    ]
    assert line_items(unnamed) == [("electricity", "estimated", 0.3, "kWh", 0.09)]
    assert unnamed["flags"] == []
    assert line_items(named_again) == [
        ("electricity", "estimated", 0.3, "kWh", 0.09),
        ("material", None, 500, "g", 2.50),
    ]
    assert material_items(named_again)[0]["material_id"] == "mdf"


async def test_images_added_later_give_a_run_its_thumbnail_and_snapshot_until_removed(
    hass: HomeAssistant,
    clock: Clock,
    files: Path,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await add_kiln_thumbnail(hass, picture("red"))
    camera = await add_kiln_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    await fire(hass, clock)

    result = await open_other(hass, entry, kiln)
    result = await configure(hass, result, other_input("Kiln", ["images"]))
    assert result["step_id"] == "images"
    result = await configure(
        hass, result, {"thumbnail": KILN_THUMBNAIL, "camera": KILN_CAMERA}
    )
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "images", "consumption", "price", "save"],
    )
    await save(hass, result)
    await fire(hass, clock)
    await change_other_device(hass, entry, kiln, has=[])
    await fire(hass, clock)

    assert "images" not in entry.subentries[kiln.subentry_id].data
    taken = [
        (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]["images"]
        for run in stored_runs(hass_storage)
    ]
    assert [[image["kind"] for image in images] for images in taken] == [
        [],
        ["thumbnail", "snapshot"],
        [],
    ]
    assert camera.requests == 1


async def test_a_program_goes_and_comes_back_with_its_program_defaults(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    bread_maker = await add_bread_maker(hass, panel, entry=entry, source="energy")
    await bake(hass, clock, "Whole wheat", kwh=0.6)

    result = await open_other(hass, entry, bread_maker)
    result = await configure(hass, result, other_input("Bread maker"))
    # Its plug's meter is a source with and without a Program, so nothing is asked.
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "consumption", "price", "save"],
    )
    await save(hass, result)
    assert "program" not in entry.subentries[bread_maker.subentry_id].data
    [without] = (await panel.call("coinop/devices/list"))["devices"]
    await bake(hass, clock, kwh=0.6)

    result = await open_other(hass, entry, bread_maker)
    result = await configure(hass, result, other_input("Bread maker", ["program"]))
    assert (result["step_id"], suggested(result, "entity_id")) == ("program", None)
    result = await configure(hass, result, {"entity_id": BREAD_MAKER_PROGRAM})
    assert (result["step_id"], result["menu_options"]) == (
        "reconfigure",
        ["other", "status", "program", "consumption", "price", "save"],
    )
    await save(hass, result)
    await bake(hass, clock, kwh=0.6)

    [again] = (await panel.call("coinop/devices/list"))["devices"]
    assert without["settings"]["program_defaults"] == BREAD_ROWS
    assert again["settings"]["program_defaults"] == BREAD_ROWS
    assert [(run.get("program"), run["name"]) for run in stored_runs(hass_storage)] == [
        ("Whole wheat", "Whole wheat"),
        (None, None),
        ("Whole wheat", "Whole wheat"),
    ]


async def test_doses_and_a_program_go_and_come_back_with_the_dose_list_and_its_amounts(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, *DOSE_MATERIALS)
    entry = await add_hub(hass)
    kettle = await add_brew_kettle(hass, panel, entry=entry)
    [before] = (await panel.call("coinop/devices/list"))["devices"]
    await brew(hass, clock, "Pale ale")

    await change_other_device(
        hass,
        entry,
        kettle,
        {"next_step_id": "none"},
        {"next_step_id": "water_none"},
        has=["water"],
    )
    refused = await panel.error(
        "coinop/devices/update_settings",
        device_id=kettle.subentry_id,
        settings={"doses": BREW_DOSES[:1]},
    )
    [without] = (await panel.call("coinop/devices/list"))["devices"]
    await brew(hass, clock, "Pale ale")
    await change_other_device(
        hass,
        entry,
        kettle,
        {"entity_id": BREW_KETTLE_PROGRAM},
        {"next_step_id": "consumption"},
        {"next_step_id": "per_program"},
        {"next_step_id": "water"},
        {"next_step_id": "water_per_program"},
        has=["program", "doses", "water"],
    )
    [again] = (await panel.call("coinop/devices/list"))["devices"]
    await brew(hass, clock, "Pale ale")

    assert refused["code"] == "not_allowed"
    assert before["settings"]["doses"] == BREW_DOSES
    assert before["settings"]["program_defaults"] == BREW_ROWS
    assert without["settings"] == before["settings"]
    assert again["settings"] == before["settings"]
    assert again["ha_settings"] == before["ha_settings"]
    dosed, plain, dosed_again = stored_runs(hass_storage)
    assert approx(costs(dosed)) == [
        ("electricity", "program_default", 3.6, 1.08),
        ("water", "program_default", 30, 0.12),
        ("dose-malt", "program_default", 4500, 9.0),
    ]
    assert (plain.get("program"), plain["line_items"], plain["flags"]) == (None, [], [])
    assert approx(costs(dosed_again)) == approx(costs(dosed))
    assert dosed_again["program"] == "Pale ale"


async def test_a_part_count_is_given_to_the_runs_started_while_the_device_has_one(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)

    await fire(hass, clock)
    await change_other_device(hass, entry, kiln, has=["part_count"])
    await fire(hass, clock)
    await change_other_device(hass, entry, kiln, has=[])
    await fire(hass, clock)

    assert [run["part_count"] for run in stored_runs(hass_storage)] == [None, 1, None]


async def test_meters_count_each_run_from_0_only_while_the_device_says_so(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    pool_pump = await add_pump(hass, entry=entry)

    await pump(hass, clock, 1.6)
    await clock.advance(hours=20)
    await change_other_device(hass, entry, pool_pump, has=[])
    await pump(hass, clock, 2.4)
    await clock.advance(hours=20)
    await change_other_device(hass, entry, pool_pump, has=["per_run_meters"])
    await pump(hass, clock, 0.8)

    runs = stored_runs(hass_storage)
    assert [electricity(run)["quantity"] for run in runs] == pytest.approx(
        [1.6, 2.4, 0.8]
    )
    assert [run["flags"] for run in runs] == [[], ["meter_reset"], []]


async def test_a_change_that_removes_and_adds_walks_what_is_new_and_asked_again_in_order(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, *DOSE_MATERIALS)
    entry = await add_hub(hass)
    kettle = await add_brew_kettle(hass, panel, entry=entry)
    await brew(hass, clock, "Pale ale")
    ended = deepcopy(stored_runs(hass_storage))

    result = await open_other(hass, entry, kettle)
    steps = []
    for user_input in (
        other_input("Brew kettle", ["water", "job", "images", "part_count"]),
        {"entity_id": ROUTER_JOB},
        {},
        {"next_step_id": "estimate"},
        {"running_power": 2000},
        {"next_step_id": "water_none"},
    ):
        result = await configure(hass, result, user_input)
        steps.append(result["step_id"])
    assert steps == ["job", "images", "consumption", "estimate", "water", "reconfigure"]
    assert result["menu_options"] == [
        "other",
        "status",
        "job",
        "images",
        "consumption",
        "price",
        "water",
        "save",
    ]
    await save(hass, result)
    hass.states.async_set(ROUTER_JOB, "Mash_Paddle.gcode")
    await brew(hass, clock, "Stout")

    # The water price stays stored behind the water source none, as after any
    # switch to it.
    kept = ["capabilities", "type_name", "job", "images", "water", "water_price"]
    assert sorted(entry.subentries[kettle.subentry_id].data) == sorted(
        [*BASIC_DATA, *kept]
    )
    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["capabilities"] == [
        "average_power",
        "images",
        "job",
        "material",
        "part_count",
        "water",
    ]
    was, new = stored_runs(hass_storage)
    assert [was] == ended
    assert (was["program"], was["part_count"]) == ("Pale ale", None)
    assert (new.get("program"), new["name"], new["part_count"]) == (
        None,
        "Mash Paddle",
        1,
    )
    # The Material is left to fill in: the job section names no Material used input.
    assert approx(costs(new)) == [
        ("electricity", "estimated", 8, 2.40),
        ("material", None, None, 0),
    ]
    assert sorted(new["flags"]) == ["material_missing", "usage_missing"]


async def test_job_and_material_is_refused_with_a_program_or_doses_as_in_add_device(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    mixes = [
        mix
        for size in range(len(CHOICES) + 1)
        for mix in combinations(CHOICES, size)
        if "job" in mix and ("program" in mix or "doses" in mix)
    ]
    assert len(mixes) == 48

    result = await open_other(hass, entry, kiln)
    for mix in mixes:
        result = await configure(hass, result, other_input("Kiln", mix))
        assert (result["step_id"], result["errors"]) == (
            "other",
            {"base": "job_with_program_or_doses"},
        ), mix
    assert {choice for choice in CHOICES if suggested(result, choice)} == set(mix)
    result = await configure(hass, result, other_input("Kiln", ["job", "images"]))

    assert result["step_id"] == "job"
    assert entry.subentries[kiln.subentry_id].data == kiln.data
