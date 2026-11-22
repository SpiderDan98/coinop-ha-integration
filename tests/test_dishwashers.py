"""Dishwashers: a Device Type of its own with the washing machine's Capabilities."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_STATUS,
    WASHER_WATER,
    add_hub,
    add_washing_machine,
    answer_progress,
    configure,
    start_reconfigure,
    walk_to_mapping,
)
from .stored import place_materials, stored_material
from .test_doses import doses
from .test_manual_runs import create
from .test_program_consumption import approx, consumed
from .test_run_event import record_events
from .test_runs import stored_runs
from .test_water import set_water
from .washing import add_washer, set_energy, washed
from .websocket import PanelClient

# 0.15 per tab, 0.005 per ml.
TABS = stored_material(
    "tabs",
    form="dishwasher_product",
    type="Dishwasher tabs",
    density=None,
    diameter=None,
    price={
        "source": "fixed",
        "pack_price": 9.0,
        "pack_size": 60.0,
        "pack_unit": "pcs",
    },
)
RINSE_AID = stored_material(
    "rinse-aid",
    form="dishwasher_product",
    type="Rinse aid",
    density=1.02,
    diameter=None,
    price={
        "source": "fixed",
        "pack_price": 4.0,
        "pack_size": 800.0,
        "pack_unit": "ml",
    },
)
DOSES = [
    {"id": "dose-tabs", "material_id": "tabs"},
    {"id": "dose-rinse-aid", "material_id": "rinse-aid"},
]
ROWS = {
    "default": {"doses": {"dose-tabs": 1}, "kwh": 1.2, "litres": 14},
    "programs": {
        "Eco 50°": {
            "doses": {"dose-tabs": 1, "dose-rinse-aid": 3},
            "kwh": 0.8,
            "litres": 9.5,
        }
    },
}


async def add_dishwasher(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    **options: Any,
) -> ConfigSubentry:
    """A Dishwasher with the Doses and ROWS above and water per Program, at 0.30 per
    kWh and 4.00 per m³; on an energy meter unless `options` pick another source."""
    place_materials(hass_storage, TABS, RINSE_AID)
    dishwasher = await add_washer(
        hass,
        name="Dishwasher",
        device_type="dishwasher",
        water="per_program",
        **options,
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=dishwasher.subentry_id,
        settings={"doses": DOSES, "program_defaults": ROWS},
    )
    return dishwasher


async def test_a_dishwasher_walks_the_washing_machines_steps(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, name="Dishwasher", status=WASHER_STATUS, device_type="dishwasher"
    )
    result = await configure(hass, result, WASHER_MAPPING)
    assert result["step_id"] == "program"
    result = await configure(hass, result, {})
    result = await answer_progress(hass, result)
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "per_program", "none"],
    )
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": WASHER_ENERGY})
    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.30})
    assert (result["step_id"], result["menu_options"]) == (
        "water",
        ["water_meter", "water_flow", "water_per_program", "water_none"],
    )
    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": WASHER_WATER})
    assert result["step_id"] == "water_price"
    result = await configure(hass, result, {"next_step_id": "water_fixed_price"})
    result = await configure(hass, result, {"price": 4.0})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [dishwasher] = entry.subentries.values()
    assert dishwasher.data["device_type"] == "dishwasher"
    assert sorted(dishwasher.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "progress",
        "status",
        "water",
        "water_price",
    ]


async def test_reconfiguring_a_dishwasher_offers_the_washing_machines_sections(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    entry = await add_hub(hass)
    dishwasher = await add_washing_machine(
        hass, entry, device_type="dishwasher", water="meter"
    )

    result = await start_reconfigure(hass, entry, dishwasher)

    assert result["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "water",
        "water_price",
        "save",
    ]


async def test_a_dishwasher_run_records_its_program_electricity_water_and_doses(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_dishwasher(hass, hass_storage, panel)

    await washed(hass, clock, "Eco 50°", kwh=0.9)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"], run["outcome"], run["part_count"]) == (
        "Eco 50°",
        "Eco 50°",
        "completed",
        None,
    )
    assert consumed(run) == approx(
        [
            ("electricity", "measured", 0.9, "kWh", 0.27),
            ("water", "program_default", 9.5, "L", 0.038),
        ]
    )
    assert doses(run) == [
        ("dose-tabs", "program_default", "tabs", 1, "pcs", 0.15, 0.15),
        ("dose-rinse-aid", "program_default", "rinse-aid", 3, "ml", 0.005, 0.015),
    ]
    assert run["flags"] == []


async def test_a_manual_dishwasher_run_takes_its_programs_row(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    dishwasher = await add_dishwasher(hass, hass_storage, panel, source="per_program")
    await clock.advance(hours=3)

    run = await create(panel, dishwasher.subentry_id, name=None, program="Eco 50°")

    assert (run["program"], run["name"], run["part_count"]) == (
        "Eco 50°",
        "Eco 50°",
        None,
    )
    assert consumed(run) == approx(
        [
            ("electricity", "program_default", 0.8, "kWh", 0.24),
            ("water", "program_default", 9.5, "L", 0.04),
        ]
    )
    assert [(dose[0], dose[3], dose[4]) for dose in doses(run)] == [
        ("dose-tabs", 1, "pcs"),
        ("dose-rinse-aid", 3, "ml"),
    ]


async def test_the_devices_command_sends_a_dishwashers_capabilities(
    hass: HomeAssistant, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await add_dishwasher(hass, hass_storage, panel)

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["capabilities"]) == (
        "dishwasher",
        ["doses", "per_run_meters", "program", "program_consumption", "water"],
    )
    assert device["settings"]["doses"] == DOSES


async def test_a_dishwasher_has_a_washing_machines_entities_and_ended_event(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    await add_dishwasher(hass, hass_storage, panel)
    fired = record_events(hass, "event.dishwasher_run")

    await washed(hass, clock, "Eco 50°", kwh=0.9)

    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.dishwasher_run",
        "sensor.dishwasher_current_run_cost",
        "sensor.dishwasher_electricity_cost",
        "sensor.dishwasher_energy_in_runs",
        "sensor.dishwasher_flagged_runs",
        "sensor.dishwasher_last_run_cost",
        "sensor.dishwasher_material_cost",
        "sensor.dishwasher_other_cost",
        "sensor.dishwasher_running_time",
        "sensor.dishwasher_runs",
        "sensor.dishwasher_total_cost",
        "sensor.dishwasher_water_cost",
        "sensor.dishwasher_water_in_runs",
    ]
    [_, ended] = fired
    assert (ended["event_type"], ended["program"], ended["outcome"]) == (
        "ended",
        "Eco 50°",
        "completed",
    )
    assert ended["energy_kwh"] == pytest.approx(0.9)
    assert ended["water_litres"] == pytest.approx(9.5)
    assert {"part_count", "cost_per_part", "material_grams"}.isdisjoint(ended)
