"""Ovens: a Program and electricity per Program, without Doses and without water."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
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
from .test_manual_runs import create
from .test_program_consumption import approx
from .test_run_event import record_events
from .test_runs import stored_runs
from .washing import (
    LIQUID,
    WASHER_PROGRAM,
    add_washer,
    set_energy,
    set_program,
    washed,
)
from .websocket import PanelClient

ROWS = {
    "default": {"doses": {}, "kwh": 1.0},
    "programs": {"Fan plus 180°": {"doses": {}, "kwh": 1.6}},
}


async def add_oven(
    hass: HomeAssistant, panel: PanelClient, **options: Any
) -> ConfigSubentry:
    """An Oven with a Program input and the ROWS above at 0.30 per kWh, its
    electricity per Program unless `options` pick another source."""
    oven = await add_washer(
        hass,
        name="Oven",
        device_type="oven",
        water=None,
        **({"source": "per_program"} | options),
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=oven.subentry_id,
        settings={"program_defaults": ROWS},
    )
    return oven


def line_items(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    return approx(
        [
            (i["kind"], i["method"], i["quantity"], i["unit"], i["amount"])
            for i in run["line_items"]
        ]
    )


async def test_an_oven_walks_the_washing_machines_steps_without_water(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, name="Oven", status=WASHER_STATUS, device_type="oven"
    )
    result = await configure(hass, result, WASHER_MAPPING)
    assert result["step_id"] == "program"
    result = await configure(hass, result, {})
    result = await answer_progress(hass, result)
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "per_program", "none"],
    )
    result = await configure(hass, result, {"next_step_id": "per_program"})
    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.30})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [oven] = entry.subentries.values()
    assert oven.data["device_type"] == "oven"
    assert oven.data["consumption"] == {"source": "per_program"}
    assert sorted(oven.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "progress",
        "status",
    ]


async def test_reconfiguring_an_oven_offers_no_water(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    oven = await add_washing_machine(
        hass, entry, device_type="oven", source="per_program", water=None
    )

    result = await start_reconfigure(hass, entry, oven)

    assert result["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "save",
    ]


@pytest.mark.parametrize(
    ("program", "recorded", "kwh", "cost"),
    [
        ("Fan plus 180°", "Fan plus 180°", 1.6, 0.48),
        ("Grill", "Grill", 1.0, 0.30),
        (None, None, 1.0, 0.30),
    ],
)
async def test_an_oven_run_takes_its_kwh_from_its_programs_row_or_the_default_row(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    program: str | None,
    recorded: str | None,
    kwh: float,
    cost: float,
) -> None:
    await add_oven(hass, panel)

    await washed(hass, clock, program)

    [run] = stored_runs(hass_storage)
    assert (run.get("program"), run["outcome"], run["part_count"]) == (
        recorded,
        "completed",
        None,
    )
    assert line_items(run) == [("electricity", "program_default", kwh, "kWh", cost)]
    assert run["flags"] == []


async def test_a_metered_oven_run_is_named_after_its_program(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_oven(hass, panel, source="energy")

    await washed(hass, clock, "Fan plus 180°", kwh=1.4)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"]) == ("Fan plus 180°", "Fan plus 180°")
    assert line_items(run) == [("electricity", "measured", 1.4, "kWh", 0.42)]


async def test_an_oven_refuses_a_dose_list(
    hass: HomeAssistant, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    place_materials(hass_storage, LIQUID)
    oven = await add_oven(hass, panel)

    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=oven.subentry_id,
        settings={"doses": [{"id": "dose-liquid", "material_id": "liquid"}]},
    )

    assert error["code"] == "not_allowed"
    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["settings"]["doses"] == []


async def test_the_devices_command_sends_an_ovens_capabilities_and_known_programs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_oven(hass, panel)
    await washed(hass, clock, "Grill")
    await set_program(
        hass, "unknown", {"options": ["Fan plus 180°", "Conventional heat"]}
    )

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["capabilities"]) == (
        "oven",
        ["per_run_meters", "program", "program_consumption"],
    )
    assert device["known_programs"] == ["Fan plus 180°", "Conventional heat", "Grill"]
    assert device["settings"]["program_defaults"] == ROWS
    assert device["ha_settings"]["program"]["entity_id"] == WASHER_PROGRAM
    assert "water" not in device["ha_settings"]


async def test_a_metered_ovens_runs_suggest_each_programs_kwh(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    oven = await add_oven(hass, panel, source="energy")
    runs = [
        ("Fan plus 180°", 100, 1.4),
        ("Fan plus 180°", 101.4, 1.8),
        ("Grill", 103.2, 0.5),
    ]
    for program, reading, kwh in runs:
        await clock.advance(minutes=10)
        # Reported at the start, so the meter isn't interpolated from the last Run's end.
        await set_energy(hass, reading)
        await washed(hass, clock, program, kwh=kwh)

    result = await panel.call(
        "coinop/devices/measured_suggestions", device_id=oven.subentry_id
    )

    assert result["suggestions"] == {
        "default": {"kwh": {"mean": 0.5, "runs": 1}},
        "programs": {
            "Fan plus 180°": {"kwh": {"mean": 1.6, "runs": 2}},
            "Grill": {"kwh": {"mean": 0.5, "runs": 1}},
        },
    }


async def test_a_manual_oven_run_takes_its_programs_row(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    oven = await add_oven(hass, panel)
    await clock.advance(hours=3)

    run = await create(panel, oven.subentry_id, name=None, program="Fan plus 180°")

    assert (run["program"], run["name"], run["part_count"]) == (
        "Fan plus 180°",
        "Fan plus 180°",
        None,
    )
    assert line_items(run) == [("electricity", "program_default", 1.6, "kWh", 0.48)]


async def test_an_oven_has_no_water_sensors_and_no_litres_in_its_ended_event(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    await add_oven(hass, panel)
    fired = record_events(hass, "event.oven_run")

    await washed(hass, clock, "Fan plus 180°")

    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.oven_run",
        "sensor.oven_current_run_cost",
        "sensor.oven_electricity_cost",
        "sensor.oven_energy_in_runs",
        "sensor.oven_flagged_runs",
        "sensor.oven_last_run_cost",
        "sensor.oven_material_cost",
        "sensor.oven_other_cost",
        "sensor.oven_projected_run_cost",
        "sensor.oven_running_time",
        "sensor.oven_runs",
        "sensor.oven_total_cost",
    ]
    [_, ended] = fired
    assert (ended["event_type"], ended["program"], ended["outcome"]) == (
        "ended",
        "Fan plus 180°",
        "completed",
    )
    assert ended["energy_kwh"] == pytest.approx(1.6)
    assert ended["total_cost"] == pytest.approx(0.48)
    assert {
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)
