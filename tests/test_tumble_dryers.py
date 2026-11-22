"""Tumble dryers: a Program, Doses and electricity per Program, but no water."""

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
    add_hub,
    add_washing_machine,
    answer_progress,
    configure,
    start_reconfigure,
    walk_to_mapping,
)
from .stored import place_materials
from .test_doses import doses
from .test_program_consumption import approx, consumed
from .test_run_event import record_events
from .test_runs import stored_runs
from .washing import add_washer, laundry, set_energy, washed
from .websocket import PanelClient

# 0.05 per sheet, 0.02 per ml.
SHEETS = laundry(
    "sheets",
    "pcs",
    form="laundry_additive",
    type="Dryer sheets",
    density=None,
    price={"pack_price": 4.0, "pack_size": 80.0},
)
FRAGRANCE = laundry(
    "fragrance",
    "ml",
    form="laundry_additive",
    type="Dryer fragrance",
    density=1.0,
    price={"pack_price": 5.0, "pack_size": 250.0},
)
DOSES = [
    {"id": "dose-sheets", "material_id": "sheets"},
    {"id": "dose-fragrance", "material_id": "fragrance"},
]
ROWS = {
    "default": {"doses": {"dose-sheets": 1}, "kwh": 2.0},
    "programs": {
        "Cupboard dry": {
            "doses": {"dose-sheets": 2, "dose-fragrance": 5},
            "kwh": 2.4,
        }
    },
}


async def add_dryer(
    hass: HomeAssistant, hass_storage: dict[str, Any], **options: Any
) -> ConfigSubentry:
    """A Tumble dryer with a Program input at 0.30 per kWh, with the dryer's
    Materials but no Dose list yet; on an energy meter unless `options` pick
    another source."""
    place_materials(hass_storage, SHEETS, FRAGRANCE)
    return await add_washer(
        hass, name="Tumble dryer", device_type="tumble_dryer", water=None, **options
    )


async def dose(panel: PanelClient, dryer: ConfigSubentry) -> None:
    """Give the Tumble dryer the Doses and ROWS above."""
    await panel.call(
        "coinop/devices/update_settings",
        device_id=dryer.subentry_id,
        settings={"doses": DOSES, "program_defaults": ROWS},
    )


async def test_a_tumble_dryer_walks_the_washing_machines_steps_without_water(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass,
        entry,
        name="Tumble dryer",
        status=WASHER_STATUS,
        device_type="tumble_dryer",
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

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [dryer] = entry.subentries.values()
    assert dryer.data["device_type"] == "tumble_dryer"
    assert sorted(dryer.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "progress",
        "status",
    ]


async def test_reconfiguring_a_tumble_dryer_offers_no_water(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    dryer = await add_washing_machine(
        hass, entry, device_type="tumble_dryer", water=None
    )

    result = await start_reconfigure(hass, entry, dryer)

    assert result["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "save",
    ]


async def test_a_tumble_dryer_run_gets_a_line_item_per_dose_and_no_water(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await dose(panel, await add_dryer(hass, hass_storage))

    await washed(hass, clock, "Cupboard dry", kwh=2.5)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"], run["outcome"], run["part_count"]) == (
        "Cupboard dry",
        "Cupboard dry",
        "completed",
        None,
    )
    assert consumed(run) == approx([("electricity", "measured", 2.5, "kWh", 0.75)])
    assert doses(run) == [
        ("dose-sheets", "program_default", "sheets", 2, "pcs", 0.05, 0.10),
        ("dose-fragrance", "program_default", "fragrance", 5, "ml", 0.02, 0.10),
    ]
    assert run["flags"] == []


async def test_a_tumble_dryer_without_doses_adds_nothing_to_a_run(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    dryer = await add_dryer(hass, hass_storage, source="per_program")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=dryer.subentry_id,
        settings={"program_defaults": {"default": {"doses": {}, "kwh": 2.0}}},
    )

    await washed(hass, clock, "Cupboard dry")

    [run] = stored_runs(hass_storage)
    assert [
        (item["kind"], item["method"], item["quantity"], item["amount"])
        for item in run["line_items"]
    ] == approx([("electricity", "program_default", 2.0, 0.60)])
    assert run["flags"] == []


async def test_the_devices_command_sends_a_tumble_dryers_capabilities(
    hass: HomeAssistant, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await dose(panel, await add_dryer(hass, hass_storage))

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["capabilities"]) == (
        "tumble_dryer",
        ["doses", "per_run_meters", "program", "program_consumption"],
    )
    assert device["settings"]["doses"] == DOSES
    assert "water" not in device["ha_settings"]


async def test_a_tumble_dryer_has_no_water_sensors_and_no_litres_in_its_ended_event(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    await dose(panel, await add_dryer(hass, hass_storage))
    fired = record_events(hass, "event.tumble_dryer_run")

    await washed(hass, clock, "Cupboard dry", kwh=2.5)

    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.tumble_dryer_run",
        "sensor.tumble_dryer_current_run_cost",
        "sensor.tumble_dryer_electricity_cost",
        "sensor.tumble_dryer_energy_in_runs",
        "sensor.tumble_dryer_flagged_runs",
        "sensor.tumble_dryer_last_run_cost",
        "sensor.tumble_dryer_material_cost",
        "sensor.tumble_dryer_other_cost",
        "sensor.tumble_dryer_projected_run_cost",
        "sensor.tumble_dryer_running_time",
        "sensor.tumble_dryer_runs",
        "sensor.tumble_dryer_total_cost",
    ]
    [_, ended] = fired
    assert (ended["event_type"], ended["program"], ended["outcome"]) == (
        "ended",
        "Cupboard dry",
        "completed",
    )
    assert ended["energy_kwh"] == pytest.approx(2.5)
    assert ended["total_cost"] == pytest.approx(0.95)
    assert {
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)
