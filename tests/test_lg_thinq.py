"""The LG ThinQ profile: an LG washer, dryer, dishwasher and oven pre-filled."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import WASHER_ENERGY, add_hub, configure, start_reconfigure
from .registry import add_lg_thinq
from .test_device_flow import fields
from .test_integration_profiles import accepted
from .test_quick_start import offered, open_add_device, pick, quick_start, register
from .test_runs import stored_runs
from .test_washer_profiles import walk_pre_filled

LG_THINQ_MAPPING = {
    "running": [
        "running",
        "detecting",
        "display_loadsize",
        "detergent_amount",
        "dispensing",
        "add_drain",
        "prewash",
        "soaking",
        "softening",
        "steam_softening",
        "rinsing",
        "spinning",
        "refreshing",
        "steam",
        "drying",
        "cool_down",
        "end_cooling",
        "checking_turbidity",
        "night_dry",
        "sterilize",
        "smart_grid_run",
        "preheat",
        "preheating",
        "preheat_complete",
        "preheating_is_done",
        "temperature_stabilization",
        "proofing",
        "cook",
        "cooking_in_progress",
        "cooling",
        "cleaning",
    ],
    "paused": ["pause", "paused", "rinse_hold"],
    "finished": [
        "end",
        "complete",
        "done",
        "running_end",
        "cook_complete",
        "cleaning_is_done",
        "wrinkle_care",
    ],
    "cancelled": ["cancel"],
    "ended": [],
    "fault": ["error", "as_pop_up", "power_fail"],
    "ignored": [
        "power_off",
        "power_on",
        "initial",
        "initializing",
        "standby",
        "sleep",
        "reserved",
        "reservation",
        "macrosector",
        "setdate",
        "preference",
        "change_condition",
        "lock",
        "diagnosis",
        "firmware",
        "fota",
        "frozen_prevent_initial",
        "frozen_prevent_running",
        "frozen_prevent_pause",
    ],
}


@pytest.mark.parametrize(
    ("appliance", "status", "device_type"),
    [
        ("DEVICE_WASHER", "main_current_state", "washing_machine"),
        ("DEVICE_WASHCOMBO_MAIN", "current_state", "washing_machine"),
        ("DEVICE_WASHCOMBO_MINI", "current_state", "washing_machine"),
        ("DEVICE_WASHTOWER_WASHER", "main_current_state", "washing_machine"),
        ("DEVICE_DRYER", "current_state", "tumble_dryer"),
        ("DEVICE_WASHTOWER_DRYER", "current_state", "tumble_dryer"),
        ("DEVICE_OVEN", "oven_current_state", "oven"),
        ("DEVICE_MICROWAVE_OVEN", "current_state", "oven"),
    ],
)
async def test_an_lg_appliance_is_added_as_the_kind_in_its_model(
    hass: HomeAssistant, appliance: str, status: str, device_type: str
) -> None:
    lg = add_lg_thinq(hass, appliance, name="Appliance")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, lg.device.id, price=0.3)

    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": lg[status], "attribute": None}
    assert data["mapping"] == LG_THINQ_MAPPING
    # Only a dishwasher reports what it runs.
    assert data["program"] == {"entity_id": None, "attribute": None}


async def test_an_lg_dishwasher_is_added_with_its_washing_course_as_program(
    hass: HomeAssistant,
) -> None:
    dishwasher = add_lg_thinq(hass, "DEVICE_DISH_WASHER", name="Dishwasher")
    entry = await add_hub(hass)

    data = await quick_start(
        hass, entry, dishwasher.device.id, price=0.3, water_price=4.0
    )

    assert data["device_type"] == "dishwasher"
    assert data["status"] == {
        "entity_id": dishwasher["current_state"],
        "attribute": None,
    }
    assert data["mapping"] == LG_THINQ_MAPPING
    assert data["program"] == {
        "entity_id": dishwasher["current_dish_washing_course"],
        "attribute": None,
    }


async def test_lg_appliances_that_are_no_device_type_are_not_offered(
    hass: HomeAssistant,
) -> None:
    add_lg_thinq(hass, "DEVICE_AIR_CONDITIONER", name="AC", device_id="ac")
    add_lg_thinq(hass, "DEVICE_REFRIGERATOR", name="Fridge", device_id="fridge")
    add_lg_thinq(hass, "DEVICE_STYLER", name="Styler", device_id="styler")
    washer = add_lg_thinq(hass)
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert offered(result) == [
        {"value": washer.device.id, "label": "Washer · LG ThinQ"},
        {"value": "manual", "label": "manual"},
    ]


@pytest.mark.parametrize(
    ("appliance", "status", "device_type"),
    [
        ("TWINWASH", "main_current_state", "washing_machine"),
        ("DOUBLE_OVEN", "upper_current_state", "oven"),
    ],
)
async def test_an_lg_unit_with_two_statuses_is_added_with_its_main_half(
    hass: HomeAssistant, appliance: str, status: str, device_type: str
) -> None:
    """The mini washer or the lower cavity is a Device of its own, set up by hand."""
    lg = add_lg_thinq(hass, appliance, name="Appliance")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, lg.device.id, price=0.3)

    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": lg[status], "attribute": None}
    assert data["mapping"] == LG_THINQ_MAPPING


async def test_each_half_of_an_lg_washtower_is_offered_as_what_it_is(
    hass: HomeAssistant,
) -> None:
    washer = add_lg_thinq(hass, "DEVICE_WASHTOWER", name="WashTower", sub_id="washer")
    dryer = add_lg_thinq(hass, "DEVICE_WASHTOWER", name="WashTower", sub_id="dryer")
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    assert offered(result) == [
        {"value": washer.device.id, "label": "WashTower washer · LG ThinQ"},
        {"value": dryer.device.id, "label": "WashTower dryer · LG ThinQ"},
        {"value": "manual", "label": "manual"},
    ]

    washing_machine = await quick_start(hass, entry, washer.device.id, price=0.3)
    tumble_dryer = await quick_start(hass, entry, dryer.device.id, price=0.3)

    assert washing_machine["device_type"] == "washing_machine"
    assert washing_machine["status"]["entity_id"] == washer["washer_current_state"]
    assert tumble_dryer["device_type"] == "tumble_dryer"
    assert tumble_dryer["status"]["entity_id"] == dryer["dryer_current_state"]


async def test_an_lg_appliances_energy_sensors_are_no_meter_and_one_is_asked_for(
    hass: HomeAssistant,
) -> None:
    washer = add_lg_thinq(hass)
    register(hass, WASHER_ENERGY, "kWh")
    entry = await add_hub(hass)

    result = await pick(hass, entry, washer.device.id)
    assert fields(result) == ["optional_meter", "price", "price_entity", "water_price"]
    result = await configure(
        hass, result, {"optional_meter": WASHER_ENERGY, "price": 0.3}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"]["entity_id"] == WASHER_ENERGY
    for key in ("yesterday", "this_month", "last_month"):
        assert washer[f"energy_{key}"] not in str(dict(subentry.data))


@pytest.mark.parametrize(
    ("states", "outcome", "flags"),
    [
        (
            ["detecting", "running", "rinsing", "spinning", "end"],
            "completed",
            [],
        ),
        (["detecting", "running", "pause", "cancel"], "cancelled", []),
        (["running", "rinsing", "error", "rinsing", "end"], "completed", ["fault"]),
    ],
)
async def test_an_lg_cycle_through_its_phases_is_one_run(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    states: list[str],
    outcome: str,
    flags: list[str],
) -> None:
    washer = add_lg_thinq(hass)
    register(hass, WASHER_ENERGY, "kWh")
    hass.states.async_set(washer["main_current_state"], "power_off")
    hass.states.async_set(WASHER_ENERGY, "10", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    await quick_start(
        hass, entry, washer.device.id, optional_meter=WASHER_ENERGY, price=0.3
    )

    for state in ("power_on", "initial", *states, "power_off"):
        hass.states.async_set(washer["main_current_state"], state)
        await hass.async_block_till_done()
        await clock.advance(minutes=20)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == outcome
    assert run["flags"] == flags


async def test_an_lg_dishwasher_run_is_named_after_its_washing_course(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    dishwasher = add_lg_thinq(hass, "DEVICE_DISH_WASHER", name="Dishwasher")
    hass.states.async_set(dishwasher["current_state"], "standby")
    entry = await add_hub(hass)
    await quick_start(hass, entry, dishwasher.device.id, price=0.3, water_price=4.0)

    hass.states.async_set(dishwasher["current_dish_washing_course"], "eco")
    for state in ("running", "rinsing", "drying", "night_dry", "end"):
        hass.states.async_set(dishwasher["current_state"], state)
        await hass.async_block_till_done()
        await clock.advance(minutes=30)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["program"]) == ("completed", "eco")


@pytest.mark.parametrize(
    ("appliance", "device_type", "status", "program"),
    [
        ("DEVICE_WASHER", "washing_machine", "main_current_state", None),
        ("DEVICE_DRYER", "tumble_dryer", "current_state", None),
        (
            "DEVICE_DISH_WASHER",
            "dishwasher",
            "current_state",
            "current_dish_washing_course",
        ),
        ("DEVICE_OVEN", "oven", "oven_current_state", None),
        # The kind in the model isn't asked: a dryer as a washing machine, and a
        # Styler, which Quick Start doesn't offer.
        ("DEVICE_DRYER", "washing_machine", "current_state", None),
        ("DEVICE_STYLER", "tumble_dryer", "current_state", None),
        ("TWINWASH", "washing_machine", "main_current_state", None),
        ("DOUBLE_OVEN", "oven", "upper_current_state", None),
    ],
)
async def test_manual_setup_pre_fills_every_device_type_lg_thinq_serves(
    hass: HomeAssistant,
    appliance: str,
    device_type: str,
    status: str,
    program: str | None,
) -> None:
    lg = add_lg_thinq(hass, appliance, name="Appliance")
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(
        hass, entry, lg, device_type, consumption={"next_step_id": "per_program"}
    )

    data = subentry.data
    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": lg[status], "attribute": None}
    assert data["mapping"] == LG_THINQ_MAPPING
    assert data["program"] == {
        "entity_id": lg[program] if program else None,
        "attribute": None,
    }
    assert data["consumption"] == {"source": "per_program"}


async def test_detect_again_works_on_a_dishwasher_added_from_lg_thinq(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    dishwasher = add_lg_thinq(hass, "DEVICE_DISH_WASHER", name="Dishwasher")
    register(hass, WASHER_ENERGY, "kWh")
    entry = await add_hub(hass)
    before = await quick_start(
        hass,
        entry,
        dishwasher.device.id,
        optional_meter=WASHER_ENERGY,
        price=0.3,
        water_price=4.0,
    )
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            dishwasher[key], new_entity_id=dishwasher[key].replace("dishwasher", "dw")
        ).entity_id
        for key in ("current_state", "current_dish_washing_course")
    }

    result = await configure(
        hass, await start_reconfigure(hass, entry, subentry), {"next_step_id": "detect"}
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "program"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["device_type"] == "dishwasher"
    assert data["status"]["entity_id"] == renamed["current_state"]
    assert data["mapping"] == LG_THINQ_MAPPING
    assert data["program"]["entity_id"] == renamed["current_dish_washing_course"]
    for section in ("consumption", "price", "water", "water_price"):
        assert data[section] == before[section]
