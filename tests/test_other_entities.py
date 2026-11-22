"""The HA entities of an Other Device follow a change of what it has: those a removed
choice brought leave the entity registry, those a new one brings are created."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .clock import Clock
from .devices import (
    add_hub,
    add_washing_machine,
    basic_entities,
    change_other_device,
    coinop_entities,
    configure,
    open_other,
    other_input,
    reconfigure,
    save,
)
from .stored import place_materials
from .test_other_changes import add_shipped, shipped_device_types
from .test_other_jobs import (
    MDF,
    PLYWOOD,
    ROUTER_JOB,
    ROUTER_USED,
    add_cnc_router,
    cut,
)
from .test_other_water import (
    ON_ITS_METER,
    add_irrigation,
    irrigate,
    set_valve,
    set_valve_water,
)
from .test_runs import value
from .test_water import set_water
from .washing import set_energy, set_washer
from .websocket import PanelClient

WATER_SENSORS = ["sensor.garden_valve_water_cost", "sensor.garden_valve_water_in_runs"]
MATERIAL_USED = "sensor.cnc_router_material_used"


def registered(
    entity_registry: er.EntityRegistry, *devices: ConfigSubentry
) -> dict[str, er.RegistryEntry]:
    """The registry entries of the Devices' entities, by entity id."""
    ids = [device.subentry_id for device in devices]
    return {
        entity.entity_id: entity
        for entity in entity_registry.entities.values()
        if entity.config_subentry_id in ids
    }


async def test_removing_water_removes_the_water_sensors_from_the_entity_registry(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    await irrigate(hass, clock, start=1000, litres=120)
    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("garden_valve"), *WATER_SENSORS]
    )

    await change_other_device(hass, entry, valve, has=[])

    assert coinop_entities(entity_registry) == basic_entities("garden_valve")
    assert [hass.states.get(entity_id) for entity_id in WATER_SENSORS] == [None, None]


async def test_adding_water_creates_the_water_sensors(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry, has=[])
    await irrigate(hass, clock, start=1000, litres=120)
    assert coinop_entities(entity_registry) == basic_entities("garden_valve")

    await change_other_device(hass, entry, valve, *ON_ITS_METER, has=["water"])
    created = [value(hass, entity_id) for entity_id in WATER_SENSORS]
    await irrigate(hass, clock, start=1120, litres=80)

    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("garden_valve"), *WATER_SENSORS]
    )
    assert created == [0, 0]
    assert [value(hass, entity_id) for entity_id in WATER_SENSORS] == [
        pytest.approx(0.32),
        pytest.approx(80),
    ]


async def test_a_water_sensor_the_user_renamed_or_disabled_is_removed_all_the_same(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    entity_registry.async_update_entity(
        "sensor.garden_valve_water_in_runs", new_entity_id="sensor.lawn_litres"
    )
    entity_registry.async_update_entity(
        "sensor.garden_valve_water_cost", disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert coinop_entities(entity_registry) == sorted(
        [
            *basic_entities("garden_valve"),
            "sensor.garden_valve_water_cost",
            "sensor.lawn_litres",
        ]
    )

    await change_other_device(hass, entry, valve, has=[])

    assert coinop_entities(entity_registry) == basic_entities("garden_valve")
    assert hass.states.get("sensor.lawn_litres") is None


async def test_water_sensors_that_come_back_count_the_runs_that_ended_before(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    await irrigate(hass, clock, start=1000, litres=120)

    await change_other_device(hass, entry, valve, has=[])
    await irrigate(hass, clock, start=1120, litres=80)
    await change_other_device(hass, entry, valve, *ON_ITS_METER, has=["water"])

    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("garden_valve"), *WATER_SENSORS]
    )
    assert [value(hass, entity_id) for entity_id in WATER_SENSORS] == [
        pytest.approx(0.48),
        pytest.approx(120),
    ]
    assert value(hass, "sensor.garden_valve_runs") == 2


async def test_removing_job_and_material_removes_the_material_used_sensor(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    entity_registry: er.EntityRegistry,
) -> None:
    place_materials(hass_storage, MDF, PLYWOOD)
    entry = await add_hub(hass)
    router = await add_cnc_router(hass, panel, entry=entry)
    await cut(hass, clock, "Sign_Oak.gcode", grams=120)
    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("cnc_router"), MATERIAL_USED]
    )

    await change_other_device(hass, entry, router, has=[])

    assert coinop_entities(entity_registry) == basic_entities("cnc_router")
    assert hass.states.get(MATERIAL_USED) is None


async def test_adding_job_and_material_creates_the_material_used_sensor(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    entity_registry: er.EntityRegistry,
) -> None:
    place_materials(hass_storage, MDF, PLYWOOD)
    entry = await add_hub(hass)
    router = await add_cnc_router(hass, panel, entry=entry)
    await cut(hass, clock, "Sign_Oak.gcode", grams=120)
    await change_other_device(hass, entry, router, has=[])
    await cut(hass, clock, "Tray.gcode", grams=300)

    await change_other_device(
        hass,
        entry,
        router,
        {"entity_id": ROUTER_JOB, "material_entity_id": ROUTER_USED},
        has=["job"],
    )
    created = value(hass, MATERIAL_USED)
    await cut(hass, clock, "Shelf.gcode", grams=500)

    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("cnc_router"), MATERIAL_USED]
    )
    assert (created, value(hass, MATERIAL_USED)) == (120, 620)


async def test_one_change_can_remove_the_sensors_of_one_choice_and_create_anothers(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)

    await change_other_device(hass, entry, valve, {}, has=["job", "part_count"])

    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("garden_valve"), "sensor.garden_valve_material_used"]
    )


async def test_the_entities_every_device_has_stay_as_they_are_whatever_is_changed(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry, has=["water", "job"])
    await irrigate(hass, clock, start=1000, litres=120)
    entity_registry.async_update_entity(
        "sensor.garden_valve_total_cost", new_entity_id="sensor.watering_money"
    )
    entity_registry.async_update_entity(
        "sensor.garden_valve_other_cost", disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    brought = {*WATER_SENSORS, "sensor.garden_valve_material_used"}
    with_both = registered(entity_registry, valve)
    common = {
        entity_id: entity
        for entity_id, entity in with_both.items()
        if entity_id not in brought
    }
    assert with_both.keys() == common.keys() | brought

    await change_other_device(hass, entry, valve, has=[])
    without = registered(entity_registry, valve)
    await change_other_device(
        hass, entry, valve, {}, *ON_ITS_METER, has=["water", "job"]
    )

    assert sorted(common) == sorted(
        entity_id.replace("garden_valve_total_cost", "watering_money")
        for entity_id in basic_entities("garden_valve")
    )
    assert without == common
    again = registered(entity_registry, valve)
    assert again.keys() == common.keys() | brought
    assert {entity_id: again[entity_id] for entity_id in common} == common
    assert common["sensor.garden_valve_other_cost"].disabled_by is not None
    assert value(hass, "sensor.watering_money") == pytest.approx(0.48)
    assert value(hass, "sensor.garden_valve_runs") == 1


async def test_renaming_the_type_name_alone_removes_and_creates_no_entity(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry, has=["water", "job"])
    before = registered(entity_registry, valve)

    await change_other_device(
        hass, entry, valve, type_name="Garden", has=["water", "job"]
    )

    assert entry.subentries[valve.subentry_id].data["type_name"] == "Garden"
    assert len(before) == 15
    assert registered(entity_registry, valve) == before


async def test_changing_another_section_or_reloading_the_hub_removes_and_creates_no_entity(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    with_water = await add_irrigation(hass, entry=entry)
    hass.states.async_set("sensor.drip_line_status", "off")
    without = await add_irrigation(
        hass, entry=entry, name="Drip line", status="sensor.drip_line_status", has=[]
    )
    before = registered(entity_registry, with_water, without)

    for valve in (with_water, without):
        await reconfigure(
            hass,
            entry,
            valve,
            {"next_step_id": "status"},
            {"entity_id": valve.data["status"]["entity_id"]},
            {"running": ["on"], "finished": ["off"]},
        )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert sorted(before) == sorted(
        [*basic_entities("garden_valve"), *WATER_SENSORS, *basic_entities("drip_line")]
    )
    assert registered(entity_registry, with_water, without) == before


async def test_a_change_that_is_refused_or_never_saved_removes_no_entity(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    before = registered(entity_registry, valve)
    left = await configure(
        hass, await open_other(hass, entry, valve), other_input("Irrigation")
    )
    menu = await configure(
        hass, await open_other(hass, entry, valve), other_input("Irrigation")
    )
    await set_valve(hass, "on")

    refused = await save(hass, menu)

    assert left["step_id"] == "reconfigure"
    assert (refused["type"], refused["reason"]) == (FlowResultType.ABORT, "run_open")
    assert WATER_SENSORS[0] in before
    assert registered(entity_registry, valve) == before


async def test_a_change_saved_while_the_hub_is_not_loaded_removes_the_sensors_too(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    await hass.config_entries.async_unload(entry.entry_id)

    await change_other_device(hass, entry, valve, has=[])
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert coinop_entities(entity_registry) == basic_entities("garden_valve")


async def test_only_the_device_that_was_changed_loses_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    garden = await add_irrigation(hass, entry=entry)
    hass.states.async_set("sensor.lawn_valve_status", "off")
    lawn = await add_irrigation(
        hass, entry=entry, name="Lawn valve", status="sensor.lawn_valve_status"
    )
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    await set_washer(hass, "off")
    washer = await add_washing_machine(hass, entry, water="meter")
    others = registered(entity_registry, lawn, washer)

    await change_other_device(hass, entry, garden, has=[])

    assert sorted(others) == sorted(
        [
            *basic_entities("lawn_valve"),
            "sensor.lawn_valve_water_cost",
            "sensor.lawn_valve_water_in_runs",
            *basic_entities("washer"),
            "sensor.washer_water_cost",
            "sensor.washer_water_in_runs",
        ]
    )
    assert registered(entity_registry, lawn, washer) == others
    assert sorted(registered(entity_registry, garden)) == basic_entities("garden_valve")


async def test_only_the_sensors_coinop_registered_for_the_choice_are_removed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Not another integration's sensor on Coin-op's HA device, and not an entity of
    another kind, whatever they are registered as."""
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry=entry)
    litres = entity_registry.async_get("sensor.garden_valve_water_in_runs")
    assert litres is not None
    other_integration = MockConfigEntry(domain="other_integration")
    other_integration.add_to_hass(hass)
    foreign = [
        entity_registry.async_get_or_create(
            "sensor",
            "other_integration",
            litres.unique_id,
            config_entry=other_integration,
            device_id=litres.device_id,
        ),
        entity_registry.async_get_or_create(
            "binary_sensor",
            "coinop",
            litres.unique_id,
            config_entry=entry,
            config_subentry_id=valve.subentry_id,
            device_id=litres.device_id,
        ),
    ]

    await change_other_device(hass, entry, valve, has=[])

    assert [entity_registry.async_get(entity.entity_id) for entity in foreign] == (
        foreign
    )
    assert sorted(set(registered(entity_registry, valve)) - {foreign[1].entity_id}) == (
        basic_entities("garden_valve")
    )


async def test_no_entity_of_a_shipped_device_type_is_removed_by_reconfiguring_or_reloading(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Not even a sensor for something its Device Type doesn't have, as a release
    that took it from the Device Type would leave one behind."""
    entry = await add_hub(hass)
    devices = [
        await add_shipped(hass, entry, device_type)
        for device_type in await shipped_device_types(hass, entry)
    ]
    for device in devices:
        for key in ("water_cost", "water_litres", "material_grams"):
            entity_registry.async_get_or_create(
                "sensor",
                "coinop",
                f"{device.subentry_id}_{key}",
                config_entry=entry,
                config_subentry_id=device.subentry_id,
            )
    before = registered(entity_registry, *devices)

    for device in devices:
        await reconfigure(
            hass,
            entry,
            device,
            {"next_step_id": "status"},
            {"entity_id": device.data["status"]["entity_id"]},
            {"running": ["on"], "finished": ["off"]},
        )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert len(before) == len(devices) * 15
    assert {
        "sensor.washing_machine_water_in_runs",
        "sensor.3d_printer_material_used",
    } < before.keys()
    assert registered(entity_registry, *devices) == before
