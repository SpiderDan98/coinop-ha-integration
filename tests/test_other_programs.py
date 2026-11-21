"""The choice Program on an Other Device: a Program input, Program Defaults that are
just the kWh per Program, and electricity "per Program" in place of the estimate."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    add_hub,
    add_other_device,
    basic_entities,
    coinop_entities,
    configure,
    other_input,
    price_choice,
    price_input,
    start_reconfigure,
)
from .test_device_flow import fields
from .test_manual_runs import create
from .test_other_devices import add_kiln, choose_other, fire
from .test_program_consumption import approx
from .test_run_event import record_events
from .test_runs import stored_runs
from .websocket import PanelClient

BREAD_MAKER_STATUS = "sensor.bread_maker_status"
BREAD_MAKER_PROGRAM = "sensor.bread_maker_program"
BREAD_MAKER_ENERGY = "sensor.bread_maker_plug_energy"
BREAD_MAKER_MAPPING = {
    "running": ["baking"],
    "finished": ["done"],
    "cancelled": ["cancelled"],
}
ROWS = {
    "default": {"doses": {}, "kwh": 0.4},
    "programs": {"Whole wheat": {"doses": {}, "kwh": 0.5}},
}


async def set_bread_maker(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(BREAD_MAKER_STATUS, status)
    await hass.async_block_till_done()


async def set_bread_program(
    hass: HomeAssistant, program: str, attributes: dict[str, Any] | None = None
) -> None:
    hass.states.async_set(BREAD_MAKER_PROGRAM, program, attributes)
    await hass.async_block_till_done()


async def set_bread_energy(hass: HomeAssistant, kwh: float) -> None:
    hass.states.async_set(BREAD_MAKER_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()


async def add_bread_maker(
    hass: HomeAssistant,
    panel: PanelClient,
    entry: ConfigEntry | None = None,
    **options: Any,
) -> ConfigSubentry:
    """A bread maker, off, in EUR at 0.30 per kWh: an Other Device with the Type Name
    "Bread maker" that has a Program, on its Program input (with no Program yet) and
    with the ROWS above, its electricity per Program unless `options` say otherwise;
    `source="energy"` is its plug's energy meter, at 100 kWh."""
    hass.config.currency = "EUR"
    await set_bread_maker(hass, "off")
    await set_bread_program(hass, "unknown")
    bread_maker: dict[str, Any] = {
        "type_name": "Bread maker",
        "name": "Bread maker",
        "status": BREAD_MAKER_STATUS,
        "mapping": BREAD_MAKER_MAPPING,
        "has": ["program"],
        "program": {"entity_id": BREAD_MAKER_PROGRAM},
        "source": "per_program",
    } | options
    if bread_maker["source"] == "energy":
        await set_bread_energy(hass, 100)
        bread_maker.setdefault("meter", {"entity_id": BREAD_MAKER_ENERGY})
    subentry = await add_other_device(hass, entry or await add_hub(hass), **bread_maker)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={"program_defaults": ROWS},
    )
    return subentry


async def bake(
    hass: HomeAssistant,
    clock: Clock,
    program: str | None = None,
    *,
    outcome: str = "done",
    kwh: float | None = None,
) -> None:
    """A loaf of three hours ended as `outcome`, on `program` if given; with `kwh` the
    energy meter counts it and reports it at the end, which finalises the Run."""
    if program is not None:
        await set_bread_program(hass, program)
    reading = None
    if kwh is not None:
        meter = hass.states.get(BREAD_MAKER_ENERGY)
        assert meter is not None
        reading = float(meter.state) + kwh
    await set_bread_maker(hass, "baking")
    await clock.advance(hours=3)
    if reading is not None:
        await set_bread_energy(hass, reading)
    await set_bread_maker(hass, outcome)
    # Older Home Assistant needs a second pass for the Run event's listeners.
    await hass.async_block_till_done()


async def bake_from_zero(hass: HomeAssistant, clock: Clock, kwh: float) -> None:
    """A loaf of `kwh` on a meter that counts it from 0 and drops back to 0 ten
    seconds after the end, before it reported the end."""
    await set_bread_energy(hass, 0)
    await set_bread_maker(hass, "baking")
    await clock.advance(hours=3)
    await set_bread_energy(hass, kwh)
    await clock.advance(minutes=1)
    await set_bread_maker(hass, "done")
    await clock.advance(seconds=10)
    await set_bread_energy(hass, 0)


def line_items(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    return approx(
        [
            (i["kind"], i["method"], i["quantity"], i["unit"], i["amount"])
            for i in run["line_items"]
        ]
    )


async def test_picking_program_adds_the_program_step_and_electricity_per_program(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)
    assert fields(result)[:2] == ["type_name", "program"]
    steps = []
    for user_input in (
        other_input("Bread maker", ["program"]),
        {},
        {"name": "Bread maker"},
        {"entity_id": BREAD_MAKER_STATUS},
        BREAD_MAKER_MAPPING,
        {"entity_id": BREAD_MAKER_PROGRAM},
    ):
        result = await configure(hass, result, user_input)
        steps.append(result["step_id"])

    assert steps == [
        "device_without_profile",
        "name",
        "status",
        "mapping",
        "program",
        "consumption",
    ]
    assert result["menu_options"] == ["energy", "power", "per_program", "none"]
    result = await configure(hass, result, {"next_step_id": "per_program"})
    assert result["step_id"] == "price"
    result = await configure(hass, result, price_choice(0.30))
    result = await configure(hass, result, price_input(0.30))
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_has_the_program_section_and_per_program_for_the_estimate(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    bread_maker = await add_bread_maker(hass, panel, entry)

    result = await start_reconfigure(hass, entry, bread_maker)

    assert result["menu_options"] == [
        "status",
        "program",
        "consumption",
        "price",
        "save",
    ]
    result = await configure(hass, result, {"next_step_id": "consumption"})
    assert result["menu_options"] == ["energy", "power", "per_program", "none"]


@pytest.mark.parametrize(
    ("program", "recorded", "kwh", "cost"),
    [
        ("Whole wheat", "Whole wheat", 0.5, 0.15),
        ("Gluten free", "Gluten free", 0.4, 0.12),
        (None, None, 0.4, 0.12),
    ],
)
async def test_a_run_takes_its_kwh_from_its_programs_row_or_the_default_row(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    program: str | None,
    recorded: str | None,
    kwh: float,
    cost: float,
) -> None:
    await add_bread_maker(hass, panel)

    await bake(hass, clock, program)

    [run] = stored_runs(hass_storage)
    assert (run.get("program"), run["name"], run["outcome"]) == (
        recorded,
        recorded,
        "completed",
    )
    assert line_items(run) == [("electricity", "program_default", kwh, "kWh", cost)]
    assert (run["flags"], run["part_count"]) == ([], None)


async def test_the_ended_event_carries_the_program_and_no_entity_is_added(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    await add_bread_maker(hass, panel)
    fired = record_events(hass, "event.bread_maker_run")

    await bake(hass, clock, "Whole wheat")

    assert coinop_entities(entity_registry) == basic_entities("bread_maker")
    [_, ended] = fired
    assert (ended["event_type"], ended["program"], ended["outcome"]) == (
        "ended",
        "Whole wheat",
        "completed",
    )
    assert ended["energy_kwh"] == pytest.approx(0.5)
    assert {
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)


async def test_a_metered_run_is_named_after_its_program(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_bread_maker(hass, panel, source="energy")

    await bake(hass, clock, "Whole wheat", kwh=0.6)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"]) == ("Whole wheat", "Whole wheat")
    assert line_items(run) == [("electricity", "measured", 0.6, "kWh", 0.18)]
    assert run["flags"] == []


async def test_a_manual_run_takes_its_programs_row(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    bread_maker = await add_bread_maker(hass, panel)
    await clock.advance(hours=5)

    run = await create(panel, bread_maker.subentry_id, name=None, program="Whole wheat")

    assert (run["device_name"], run["program"], run["name"]) == (
        "Bread maker",
        "Whole wheat",
        "Whole wheat",
    )
    assert line_items(run) == [("electricity", "program_default", 0.5, "kWh", 0.15)]


async def test_correcting_a_runs_program_takes_the_new_programs_row(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_bread_maker(hass, panel)
    await bake(hass, clock, "Gluten free")
    [run] = stored_runs(hass_storage)

    result = await panel.call(
        "coinop/runs/update", run_id=run["id"], program="Whole wheat"
    )

    assert result["run"]["program"] == "Whole wheat"
    assert line_items(result["run"]) == [
        ("electricity", "program_default", 0.5, "kWh", 0.15)
    ]


async def test_a_run_of_an_other_device_without_a_program_takes_none(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_kiln(hass)
    await fire(hass, clock)
    [run] = stored_runs(hass_storage)

    error = await panel.error("coinop/runs/update", run_id=run["id"], program="Glaze")

    assert error["code"] == "not_allowed"


async def test_the_devices_command_sends_what_it_has_and_the_programs_it_knows(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_bread_maker(hass, panel)
    await bake(hass, clock, "Gluten free")
    await set_bread_program(hass, "unknown", {"options": ["Basic", "Whole wheat"]})

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["type_name"], device["capabilities"]) == (
        "other",
        "Bread maker",
        ["program", "program_consumption"],
    )
    assert device["known_programs"] == ["Basic", "Whole wheat", "Gluten free"]
    assert device["settings"]["program_defaults"] == ROWS
    assert device["ha_settings"]["program"]["entity_id"] == BREAD_MAKER_PROGRAM
    assert device["ha_settings"]["consumption"] == {"source": "per_program"}


async def test_metered_runs_suggest_each_programs_kwh(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    bread_maker = await add_bread_maker(hass, panel, source="energy")
    loaves = [
        ("Whole wheat", 100, 0.44),
        ("Whole wheat", 100.44, 0.48),
        ("Basic", 100.92, 0.3),
    ]
    for program, reading, kwh in loaves:
        await clock.advance(minutes=10)
        # Reported at the start, so the meter isn't interpolated from the last Run's end.
        await set_bread_energy(hass, reading)
        await bake(hass, clock, program, kwh=kwh)

    result = await panel.call(
        "coinop/devices/measured_suggestions", device_id=bread_maker.subentry_id
    )

    assert result["suggestions"] == {
        "default": {"kwh": {"mean": 0.3, "runs": 1}},
        "programs": {
            "Whole wheat": {"kwh": {"mean": 0.46, "runs": 2}},
            "Basic": {"kwh": {"mean": 0.3, "runs": 1}},
        },
    }


@pytest.mark.parametrize(
    ("has", "flags"),
    [(["program", "per_run_meters"], []), (["program"], ["meter_reset"])],
    ids=["meters count each Run from 0", "Program alone"],
)
async def test_a_program_goes_with_meters_that_count_each_run_from_0_and_without(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    has: list[str],
    flags: list[str],
) -> None:
    await add_bread_maker(hass, panel, has=has, source="energy")
    await set_bread_program(hass, "Whole wheat")

    await bake_from_zero(hass, clock, 0.6)
    await clock.advance(hours=20)
    await bake_from_zero(hass, clock, 0.7)

    first, second = stored_runs(hass_storage)
    assert (first["program"], second["program"]) == ("Whole wheat", "Whole wheat")
    assert line_items(first) == [("electricity", "measured", 0.6, "kWh", 0.18)]
    assert line_items(second) == [("electricity", "measured", 0.7, "kWh", 0.21)]
    assert (first["flags"], second["flags"]) == (flags, flags)


async def test_its_runs_are_totalled_by_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_bread_maker(hass, panel)
    await bake(hass, clock)
    for _ in range(2):
        await clock.advance(hours=1)
        await bake(hass, clock, "Whole wheat")

    result = await panel.call("coinop/aggregates/get", group_by=["program"])

    assert [
        (group["program"], group["runs"], group["cost"]) for group in result["groups"]
    ] == [("Whole wheat", 2, 0.3), (None, 1, 0.12)]
