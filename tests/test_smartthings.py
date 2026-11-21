"""The SmartThings Integration Profile: Samsung washers, dryers, dishwashers and ovens."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import add_hub, configure, start_add_device, start_reconfigure
from .registry import add_smartthings
from .test_device_flow import fields, suggested
from .test_integration_profiles import accepted
from .test_measured import electricity
from .test_quick_start import offered, open_add_device, pick, quick_start
from .test_runs import stored_runs
from .test_washer_profiles import walk_pre_filled

LAUNDRY_MAPPING = {
    "running": ["run"],
    "paused": ["pause"],
    "finished": ["stop"],
    "cancelled": [],
    "ended": [],
    "fault": [],
    "ignored": [],
}


def energy_meter(entity_id: str) -> dict[str, Any]:
    return {
        "source": "energy",
        "entity_id": entity_id,
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }


@pytest.mark.parametrize(
    ("kind", "device_type", "prices"),
    [
        ("washer", "washing_machine", {"price": 0.3, "water_price": 4.0}),
        ("dryer", "tumble_dryer", {"price": 0.3}),
        ("dishwasher", "dishwasher", {"price": 0.3, "water_price": 4.0}),
    ],
)
async def test_a_smartthings_laundry_or_dish_appliance_is_added_as_what_it_is(
    hass: HomeAssistant, kind: str, device_type: str, prices: dict[str, Any]
) -> None:
    appliance = add_smartthings(hass, kind, name="Appliance")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, appliance.device.id, **prices)

    assert data["device_type"] == device_type
    assert data["status"] == {
        "entity_id": "sensor.appliance_machine_state",
        "attribute": None,
    }
    assert data["mapping"] == LAUNDRY_MAPPING
    assert data["consumption"] == energy_meter("sensor.appliance_energy")
    assert data["program"] == {"entity_id": None, "attribute": None}


async def test_a_smartthings_oven_is_an_oven_read_from_its_main_cavity(
    hass: HomeAssistant,
) -> None:
    oven = add_smartthings(
        hass, "oven", name="Oven", energy=False, component="cavity-01"
    )
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, oven.device.id, price=0.3)

    assert data["device_type"] == "oven"
    assert data["status"] == {"entity_id": oven["machine_state"], "attribute": None}
    assert data["mapping"] == {
        "running": ["running"],
        "paused": ["paused"],
        "finished": ["ready"],
        "cancelled": [],
        "ended": [],
        "fault": [],
        "ignored": [],
    }
    assert data["consumption"] == {"source": "per_program"}


async def test_a_smartthings_washer_with_an_upper_washer_is_read_from_its_main_one(
    hass: HomeAssistant,
) -> None:
    washer = add_smartthings(hass, "washer", component="sub")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, washer.device.id, price=0.3, water_price=4.0)

    assert data["device_type"] == "washing_machine"
    assert data["status"] == {"entity_id": washer["machine_state"], "attribute": None}


@pytest.mark.parametrize(
    ("kind", "states", "prices"),
    [
        ("washer", ("run", "pause", "stop"), {"water_price": 4.0}),
        ("oven", ("running", "paused", "ready"), {}),
    ],
)
async def test_a_smartthings_load_that_pauses_is_one_run_that_completes(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    kind: str,
    states: tuple[str, str, str],
    prices: dict[str, Any],
) -> None:
    appliance = add_smartthings(hass, kind, name="Appliance")
    running, paused, stopped = states

    async def report(state: str, kwh: float) -> None:
        hass.states.async_set(appliance["machine_state"], state)
        hass.states.async_set(
            appliance["energy"], str(kwh), {"unit_of_measurement": "kWh"}
        )
        await hass.async_block_till_done()

    await report(stopped, 100)
    entry = await add_hub(hass)
    await quick_start(hass, entry, appliance.device.id, price=0.3, **prices)
    await clock.advance(minutes=5)
    await report(running, 100)
    await clock.advance(minutes=30)
    await report(paused, 100.4)
    await clock.advance(minutes=5)
    await report(running, 100.4)
    await clock.advance(minutes=30)
    await report(stopped, 101)
    await clock.advance(hours=1)
    # Idle again after the appliance was offline.
    await report("unavailable", 101)
    await clock.advance(minutes=5)
    await report(stopped, 101)
    await clock.advance(hours=1)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert electricity(run)["quantity"] == pytest.approx(1)


async def test_smartthings_devices_that_are_no_device_type_are_not_offered(
    hass: HomeAssistant,
) -> None:
    add_smartthings(hass, "tv", name="TV", device_id="tv", energy=False)
    add_smartthings(hass, "refrigerator", name="Fridge", device_id="fridge")
    # It has a dryer's machine state, but it freshens clothes.
    add_smartthings(hass, "steam_closet", name="AirDresser", device_id="closet")
    dishwasher = add_smartthings(hass, "dishwasher", name="Dishwasher")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert offered(result) == [
        {"value": dishwasher.device.id, "label": "Dishwasher · SmartThings"},
        {"value": "manual", "label": "manual"},
    ]


async def test_a_smartthings_appliance_whose_machine_state_is_disabled_is_not_offered(
    hass: HomeAssistant,
) -> None:
    add_smartthings(hass, "washer", device_id="washer", disabled=("machine_state",))
    dishwasher = add_smartthings(hass, "dishwasher", name="Dishwasher")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert offered(result) == [
        {"value": dishwasher.device.id, "label": "Dishwasher · SmartThings"},
        {"value": "manual", "label": "manual"},
    ]


@pytest.mark.parametrize(
    ("energy", "disabled", "asked"),
    [
        (True, (), ["price", "price_entity", "water_price"]),
        (False, (), ["optional_meter", "price", "price_entity", "water_price"]),
        (True, ("energy",), ["optional_meter", "price", "price_entity", "water_price"]),
    ],
)
async def test_a_smartthings_appliance_is_asked_for_a_meter_only_without_its_own(
    hass: HomeAssistant, energy: bool, disabled: tuple[str, ...], asked: list[str]
) -> None:
    washer = add_smartthings(hass, "washer", energy=energy, disabled=disabled)
    entry = await add_hub(hass)

    result = await pick(hass, entry, washer.device.id)
    assert fields(result) == asked
    result = await configure(hass, result, {"price": 0.3, "water_price": 4.0})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"] == (
        energy_meter(washer["energy"])
        if "optional_meter" not in asked
        else {"source": "per_program"}
    )


@pytest.mark.parametrize(
    "device_type", ["washing_machine", "tumble_dryer", "dishwasher", "oven"]
)
async def test_manual_setup_pre_fills_every_device_type_smartthings_serves(
    hass: HomeAssistant, device_type: str
) -> None:
    # The kind its machine state tells isn't asked: a washer as an oven too.
    washer = add_smartthings(hass, "washer")
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, washer, device_type)

    assert "program" in shown
    data = subentry.data
    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": washer["machine_state"], "attribute": None}
    assert data["mapping"] == LAUNDRY_MAPPING
    assert data["program"] == {"entity_id": None, "attribute": None}
    assert data["consumption"] == energy_meter(washer["energy"])


async def test_manual_setup_of_a_coffee_machine_pre_fills_nothing_from_smartthings(
    hass: HomeAssistant,
) -> None:
    washer = add_smartthings(hass, "washer")
    entry = await add_hub(hass)

    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=washer.device.id, device_type="coffee_machine"
        ),
        {"name": "Coffee"},
    )

    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") is None


async def test_detect_again_re_applies_status_and_mapping_and_leaves_meters_alone(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    dishwasher = add_smartthings(hass, "dishwasher", name="Dishwasher")
    entry = await add_hub(hass)
    before = await quick_start(
        hass, entry, dishwasher.device.id, price=0.3, water_price=4.0
    )
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            dishwasher[key], new_entity_id=dishwasher[key].replace("dishwasher", "dw")
        ).entity_id
        for key in ("machine_state", "energy")
    }

    result = await configure(
        hass, await start_reconfigure(hass, entry, subentry), {"next_step_id": "detect"}
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    assert shown == ["status", "mapping"]
    data = entry.subentries[subentry.subentry_id].data
    assert data["status"]["entity_id"] == renamed["machine_state"]
    assert data["mapping"] == LAUNDRY_MAPPING
    # Still the old entity id: the electricity source is the user's to change.
    assert (
        data["consumption"]
        == before["consumption"]
        == energy_meter(dishwasher["energy"])
    )
    for section in ("price", "water", "water_price"):
        assert data[section] == before[section]
