"""Integration Profiles of the HACS integrations for Home Connect appliances: Home
Connect Local and Home Connect Alt."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import WASHER_ENERGY, add_hub, configure, start_reconfigure
from .registry import HaDevice, add_home_connect_alt, add_home_connect_local
from .test_appliance_kinds import HOME_CONNECT_MAPPING
from .test_integration_profiles import accepted
from .test_lifecycle import at
from .test_quick_start import offered, open_add_device, quick_start
from .test_runs import stored_runs
from .test_washer_profiles import walk_pre_filled

DEVICE_TYPES = [
    "washing_machine",
    "dishwasher",
    "tumble_dryer",
    "coffee_machine",
    "oven",
]

STATE = "BSH.Common.EnumType.OperationState"
HOME_CONNECT_ALT_MAPPING = {
    "running": [f"{STATE}.Run"],
    "paused": [f"{STATE}.Pause", f"{STATE}.ActionRequired"],
    "finished": [f"{STATE}.Finished"],
    "cancelled": [f"{STATE}.Aborting"],
    "ended": [],
    "fault": [f"{STATE}.Error"],
    "ignored": [f"{STATE}.Inactive", f"{STATE}.Ready", f"{STATE}.DelayedStart"],
}


async def test_quick_start_asks_a_home_connect_local_appliance_its_device_type(
    hass: HomeAssistant,
) -> None:
    appliance = add_home_connect_local(hass)
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    assert offered(result)[0] == {
        "value": appliance.device.id,
        "label": "Bosch Dishwasher · Home Connect Local",
    }

    result = await configure(hass, result, {"device": appliance.device.id})

    assert result["step_id"] == "quick_start_device_type"
    assert offered(result) == [*DEVICE_TYPES, "pick_another_device"]
    result = await configure(hass, result, {"device_type": "dishwasher"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["device_type"] == "dishwasher"
    assert subentry.data["status"] == {
        "entity_id": "sensor.bosch_dishwasher_operation_state",
        "attribute": None,
    }
    assert subentry.data["mapping"] == HOME_CONNECT_MAPPING
    assert subentry.data["program"] == {
        "entity_id": "sensor.bosch_dishwasher_active_program",
        "attribute": None,
    }


async def test_a_home_connect_local_run_opens_pauses_and_ends_as_with_home_connect(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    appliance = add_home_connect_local(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, appliance.device.id, "dishwasher", price=0.3)

    async def report(state: str, minutes: float) -> None:
        hass.states.async_set(appliance["sensor_operation_state"], state)
        await hass.async_block_till_done()
        await clock.advance(minutes=minutes)

    hass.states.async_set(
        appliance["sensor_active_program"], "dishcare_dishwasher_program_eco50"
    )
    for state, minutes in [
        ("ready", 5),
        ("delayedstart", 5),
        ("run", 30),
        ("actionrequired", 10),
        ("run", 60),
        ("finished", 5),
        ("ready", 5),
    ]:
        await report(state, minutes)

    [run] = stored_runs(hass_storage)
    assert run["started"] == at(minutes=10)
    assert run["pauses"] == [{"start": at(minutes=40), "end": at(minutes=50)}]
    assert run["ended"] == at(minutes=110)
    assert run["outcome"] == "completed"
    assert run["program"] == "dishcare_dishwasher_program_eco50"


async def test_quick_start_asks_a_home_connect_alt_appliance_its_device_type(
    hass: HomeAssistant,
) -> None:
    appliance = add_home_connect_alt(hass)
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    assert offered(result)[0] == {
        "value": appliance.device.id,
        "label": "Washer · Home Connect Alt",
    }

    result = await configure(hass, result, {"device": appliance.device.id})

    assert result["step_id"] == "quick_start_device_type"
    assert offered(result) == [*DEVICE_TYPES, "pick_another_device"]
    result = await configure(hass, result, {"device_type": "washing_machine"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["device_type"] == "washing_machine"
    assert subentry.data["status"] == {
        "entity_id": "sensor.washer_operation_state",
        "attribute": None,
    }
    assert subentry.data["mapping"] == HOME_CONNECT_ALT_MAPPING
    # The active program, not the one picked for the next start.
    assert subentry.data["program"] == {
        "entity_id": "sensor.washer_active_program",
        "attribute": None,
    }


async def test_a_home_connect_alt_run_opens_and_ends_by_the_enumeration_keys(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    appliance = add_home_connect_alt(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, appliance.device.id, "washing_machine", price=0.3)

    async def report(state: str, minutes: float) -> None:
        hass.states.async_set(
            appliance["BSH.Common.Status.OperationState"], f"{STATE}.{state}"
        )
        await hass.async_block_till_done()
        await clock.advance(minutes=minutes)

    hass.states.async_set(
        appliance["active_program"], "LaundryCare.Washer.Program.Cotton"
    )
    for state, minutes in [
        ("Ready", 5),
        ("Run", 30),
        ("Pause", 10),
        ("Run", 60),
        ("Finished", 5),
        ("Inactive", 5),
        ("Run", 20),
        ("Aborting", 5),
        ("Ready", 5),
    ]:
        await report(state, minutes)

    cotton, aborted = stored_runs(hass_storage)
    assert cotton["started"] == at(minutes=5)
    assert cotton["pauses"] == [{"start": at(minutes=35), "end": at(minutes=45)}]
    assert cotton["ended"] == at(minutes=105)
    assert cotton["outcome"] == "completed"
    assert cotton["program"] == "LaundryCare.Washer.Program.Cotton"
    assert aborted["outcome"] == "cancelled"


async def test_a_home_connect_alt_appliance_that_has_run_no_program_yet_has_none(
    hass: HomeAssistant,
) -> None:
    appliance = add_home_connect_alt(hass, active_program=False)
    entry = await add_hub(hass)

    data = await quick_start(
        hass, entry, appliance.device.id, "washing_machine", price=0.3
    )

    assert data["status"]["entity_id"] == "sensor.washer_operation_state"
    # Not the program picked for the next start.
    assert data["program"] == {"entity_id": None, "attribute": None}


@pytest.mark.parametrize("device_type", DEVICE_TYPES)
@pytest.mark.parametrize(
    ("add", "status", "mapping", "program"),
    [
        (
            add_home_connect_local,
            "sensor.bosch_dishwasher_operation_state",
            HOME_CONNECT_MAPPING,
            "sensor.bosch_dishwasher_active_program",
        ),
        (
            add_home_connect_alt,
            "sensor.washer_operation_state",
            HOME_CONNECT_ALT_MAPPING,
            "sensor.washer_active_program",
        ),
    ],
    ids=["local", "alt"],
)
async def test_manual_setup_pre_fills_every_device_type_they_serve(
    hass: HomeAssistant,
    add: Callable[[HomeAssistant], HaDevice],
    status: str,
    mapping: dict[str, list[str]],
    program: str,
    device_type: str,
) -> None:
    appliance = add(hass)
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(
        hass, entry, appliance, device_type, consumption={"next_step_id": "per_program"}
    )

    data = subentry.data
    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": status, "attribute": None}
    assert data["mapping"] == mapping
    assert data["program"] == {"entity_id": program, "attribute": None}


@pytest.mark.parametrize(
    ("add", "keys"),
    [
        (add_home_connect_local, ("sensor_operation_state", "sensor_active_program")),
        (add_home_connect_alt, ("BSH.Common.Status.OperationState", "active_program")),
    ],
    ids=["local", "alt"],
)
async def test_detect_again_re_applies_status_mapping_and_program_only(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    add: Callable[[HomeAssistant], HaDevice],
    keys: tuple[str, str],
) -> None:
    appliance = add(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    before = await quick_start(
        hass,
        entry,
        appliance.device.id,
        "washing_machine",
        optional_meter=WASHER_ENERGY,
        price=0.3,
        water_price=4.0,
    )
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    status, program = (
        entity_registry.async_update_entity(
            appliance[key], new_entity_id=f"sensor.renamed_{index}"
        ).entity_id
        for index, key in enumerate(keys)
    )

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
    assert data["status"]["entity_id"] == status
    assert data["mapping"] == before["mapping"]
    assert data["program"]["entity_id"] == program
    for section in ("consumption", "price", "water", "water_price"):
        assert data[section] == before[section]
