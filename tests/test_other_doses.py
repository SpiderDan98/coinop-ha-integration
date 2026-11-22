"""Doses on an Other Device: the choice "Doses" brings a Dose list whose amounts are
per Program on a Device with a Program and in the Default row alone on one without."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    OTHER_MAPPING,
    add_hub,
    add_other_device,
    basic_entities,
    coinop_entities,
    configure,
    other_input,
    report_status,
    run_once,
    start_reconfigure,
)
from .stored import place_materials, stored_material
from .test_device_flow import fields
from .test_doses import doses
from .test_manual_runs import create
from .test_other_devices import choose_other
from .test_program_consumption import approx, consumed
from .test_program_correction import costs
from .test_run_event import record_events
from .test_runs import stored_runs, value
from .test_water import set_water
from .websocket import PanelClient

SODA_MAKER_STATUS = "sensor.soda_maker_status"
CO2_SCALE = "sensor.co2_scale"


def other_material(
    material_id: str, name: str, density: float, price: float, size: float, unit: str
) -> dict[str, Any]:
    """A Material of the form Other, bought as a pack of `size` `unit` at `price`."""
    return stored_material(
        material_id,
        name=name,
        form="other",
        type=name,
        density=density,
        diameter=None,
        price={
            "source": "fixed",
            "pack_price": price,
            "pack_size": size,
            "pack_unit": unit,
        },
    )


# 0.02 per g, 0.01 per ml; 0.002 per g, 0.05 per g.
CO2 = other_material("co2", "CO₂", 0.77, 8.5, 425.0, "g")
SYRUP = other_material("syrup", "Cola syrup", 1.3, 5.0, 500.0, "ml")
MALT = other_material("malt", "Pale malt", 0.6, 50.0, 25000.0, "g")
HOPS = other_material("hops", "Hop pellets", 0.5, 5.0, 100.0, "g")
DOSE_MATERIALS = (CO2, SYRUP, MALT, HOPS)
SODA_DOSES = [
    {"id": "dose-co2", "material_id": "co2"},
    {"id": "dose-syrup", "material_id": "syrup"},
]


async def set_soda_maker(hass: HomeAssistant, status: str) -> None:
    await report_status(hass, SODA_MAKER_STATUS, status)


async def set_co2_scale(hass: HomeAssistant, grams: float | str) -> None:
    hass.states.async_set(CO2_SCALE, str(grams), {"unit_of_measurement": "g"})
    await hass.async_block_till_done()


async def add_soda_maker(
    hass: HomeAssistant,
    hass_storage: dict[str, Any] | None = None,
    *,
    entry: ConfigEntry | None = None,
    **options: Any,
) -> ConfigSubentry:
    """A soda maker, off, in EUR: an Other Device with the Type Name "Soda maker" that
    has Doses and no Program, with the electricity source none unless `options` say
    otherwise. `hass_storage` places the `DOSE_MATERIALS`, which the hub reads when it
    is set up; `SODA_DOSES` are the Doses of its `CO2` and `SYRUP`."""
    hass.config.currency = "EUR"
    if hass_storage is not None:
        place_materials(hass_storage, *DOSE_MATERIALS)
    await set_soda_maker(hass, "off")
    soda_maker: dict[str, Any] = {
        "type_name": "Soda maker",
        "name": "Soda maker",
        "status": SODA_MAKER_STATUS,
        "has": ["doses"],
        "source": "none",
    }
    return await add_other_device(
        hass, entry or await add_hub(hass), **soda_maker | options
    )


async def dose(
    panel: PanelClient,
    device: ConfigSubentry,
    default: dict[str, float],
    programs: dict[str, dict[str, float]] | None = None,
    dose_list: list[dict[str, Any]] = SODA_DOSES,
) -> Any:
    """Save the Device's Dose list with the Default row's amounts and those of each
    of `programs`."""
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=device.subentry_id,
        settings={
            "doses": dose_list,
            "program_defaults": {
                "default": {"doses": default},
                "programs": {
                    program: {"doses": amounts}
                    for program, amounts in (programs or {}).items()
                },
            },
        },
    )
    return result["settings"]


async def weigh_the_co2(panel: PanelClient, soda_maker: ConfigSubentry) -> None:
    """The CO₂'s Dose on its stock input `CO2_SCALE`, with 8 g in the Default row."""
    await dose(
        panel,
        soda_maker,
        {"dose-co2": 8, "dose-syrup": 40},
        dose_list=[SODA_DOSES[0] | {"stock": {"entity_id": CO2_SCALE}}, SODA_DOSES[1]],
    )


async def carbonate(hass: HomeAssistant, clock: Clock, *, ended: str = "off") -> None:
    """A bottle carbonated in a minute, after which the soda maker is `ended`."""
    await run_once(hass, clock, SODA_MAKER_STATUS, ended=ended, minutes=1)


async def test_doses_without_a_program_bring_no_step_and_no_section(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)
    assert fields(result)[:4] == ["type_name", "program", "doses", "water"]
    steps = []
    for user_input in (
        other_input("Soda maker", ["doses"]),
        {},
        {"name": "Soda maker"},
        {"entity_id": SODA_MAKER_STATUS},
        OTHER_MAPPING,
        {},
    ):
        result = await configure(hass, result, user_input)
        steps.append(result["step_id"])

    assert steps == [
        "device_without_profile",
        "name",
        "status",
        "mapping",
        "progress",
        "consumption",
    ]
    assert result["menu_options"] == ["energy", "power", "estimate", "none"]
    result = await configure(hass, result, {"next_step_id": "none"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [soda_maker] = entry.subentries.values()
    result = await start_reconfigure(hass, entry, soda_maker)
    assert result["menu_options"] == [
        "other",
        "status",
        "progress",
        "consumption",
        "save",
    ]


async def test_without_a_program_every_run_takes_the_default_rows_amounts(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    soda_maker = await add_soda_maker(hass, hass_storage)
    await dose(panel, soda_maker, {"dose-co2": 8, "dose-syrup": 40})

    await carbonate(hass, clock)

    [run] = stored_runs(hass_storage)
    assert (run["device_name"], run["name"], run.get("program")) == (
        "Soda maker",
        None,
        None,
    )
    assert [item["kind"] for item in run["line_items"]] == ["material", "material"]
    assert doses(run) == [
        ("dose-co2", "default_row", "co2", 8, "g", 0.02, 0.16),
        ("dose-syrup", "default_row", "syrup", 40, "ml", 0.01, 0.40),
    ]
    assert (run["finalised"], run["flags"]) == (True, [])


async def test_program_rows_stored_for_a_device_without_a_program_are_never_used(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    soda_maker = await add_soda_maker(hass, hass_storage)

    settings = await dose(
        panel, soda_maker, {"dose-co2": 8}, {"Strong": {"dose-co2": 12}}
    )
    await carbonate(hass, clock)

    assert settings["program_defaults"]["programs"] == {
        "Strong": {"doses": {"dose-co2": 12}}
    }
    [run] = stored_runs(hass_storage)
    assert doses(run) == [("dose-co2", "default_row", "co2", 8, "g", 0.02, 0.16)]


async def test_a_manual_run_without_a_program_takes_the_default_rows_amounts(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    soda_maker = await add_soda_maker(hass, hass_storage)
    await dose(panel, soda_maker, {"dose-co2": 8, "dose-syrup": 40})
    await clock.advance(hours=5)

    run = await create(panel, soda_maker.subentry_id, name="Party bottles")

    assert (run["program"], run["flags"]) == (None, [])
    assert doses(run) == [
        ("dose-co2", "default_row", "co2", 8, "g", 0.02, 0.16),
        ("dose-syrup", "default_row", "syrup", 40, "ml", 0.01, 0.40),
    ]
    error = await panel.error("coinop/runs/update", run_id=run["id"], program="Strong")
    assert error["code"] == "not_allowed"


@pytest.mark.parametrize(
    ("ended", "outcome", "flags"),
    [
        ("cancelled", "cancelled", ["ended_early_defaults"]),
        ("done", "completed", []),
    ],
)
async def test_a_cancelled_run_is_flagged_for_its_default_amounts(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    ended: str,
    outcome: str,
    flags: list[str],
) -> None:
    soda_maker = await add_soda_maker(
        hass,
        hass_storage,
        mapping={"running": ["on"], "finished": ["done"], "cancelled": ["cancelled"]},
    )
    await dose(panel, soda_maker, {"dose-co2": 8})

    await carbonate(hass, clock, ended=ended)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["flags"]) == (outcome, flags)
    assert doses(run) == [("dose-co2", "default_row", "co2", 8, "g", 0.02, 0.16)]


async def test_a_stock_input_doses_what_it_lost_during_the_run(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_co2_scale(hass, 400)
    soda_maker = await add_soda_maker(hass, hass_storage)
    await weigh_the_co2(panel, soda_maker)

    await set_soda_maker(hass, "on")
    await clock.advance(minutes=1)
    await set_co2_scale(hass, 391)
    await set_soda_maker(hass, "off")
    await set_co2_scale(hass, 391)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-co2", "stock_input", "co2", 9, "g", 0.02, 0.18),
        ("dose-syrup", "default_row", "syrup", 40, "ml", 0.01, 0.40),
    ]
    assert run["flags"] == []


async def test_an_unavailable_stock_input_falls_back_to_the_default_row_with_a_flag(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_co2_scale(hass, STATE_UNAVAILABLE)
    soda_maker = await add_soda_maker(hass, hass_storage)
    await weigh_the_co2(panel, soda_maker)

    await carbonate(hass, clock)
    await clock.advance(minutes=4, seconds=59)
    assert stored_runs(hass_storage) == []
    await clock.advance(seconds=1)

    [run] = stored_runs(hass_storage)
    assert doses(run)[0] == ("dose-co2", "default_row", "co2", 8, "g", 0.02, 0.16)
    assert run["flags"] == ["stock_input_unavailable"]


async def test_doses_and_water_without_a_program_take_no_water_per_program(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    water_meter = "sensor.soda_maker_water"
    await set_water(hass, 1000, entity=water_meter)
    soda_maker = await add_soda_maker(
        hass,
        hass_storage,
        has=["doses", "water"],
        water="meter",
        water_meter={"entity_id": water_meter},
    )
    [entry] = hass.config_entries.async_entries("coinop")
    result = await start_reconfigure(hass, entry, soda_maker)
    result = await configure(hass, result, {"next_step_id": "water"})
    assert result["menu_options"] == ["water_meter", "water_flow", "water_none"]
    await dose(panel, soda_maker, {"dose-co2": 8})

    await set_soda_maker(hass, "on")
    await clock.advance(minutes=1)
    await set_water(hass, 1001, entity=water_meter)
    await set_soda_maker(hass, "off")
    await set_water(hass, 1001, entity=water_meter)

    [run] = stored_runs(hass_storage)
    assert approx(costs(run)) == [
        ("water", "measured", 1, 0.004),
        ("dose-co2", "default_row", 8, 0.16),
    ]
    assert run["flags"] == []


@pytest.mark.parametrize(
    ("has", "accepted"),
    [
        (["doses"], True),
        (["program", "doses"], True),
        (["doses", "water"], True),
        (["program"], False),
        ([], False),
    ],
    ids=[
        "Doses",
        "Program and Doses",
        "Doses and water",
        "Program alone",
        "nothing picked",
    ],
)
async def test_a_dose_list_is_saved_only_on_a_device_with_doses(
    hass: HomeAssistant,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    has: list[str],
    accepted: bool,
) -> None:
    device = await add_soda_maker(hass, hass_storage, has=has)
    change = {
        "device_id": device.subentry_id,
        "settings": {
            "doses": SODA_DOSES,
            "program_defaults": {"default": {"doses": {"dose-co2": 8}}},
        },
    }

    if accepted:
        await panel.call("coinop/devices/update_settings", **change)
    else:
        error = await panel.error("coinop/devices/update_settings", **change)
        assert error["code"] == "not_allowed"

    [listed] = (await panel.call("coinop/devices/list"))["devices"]
    assert ("doses" in listed["capabilities"]) is accepted
    assert listed["settings"]["doses"] == (SODA_DOSES if accepted else [])
    assert listed["settings"]["program_defaults"]["default"] == {
        "doses": {"dose-co2": 8} if accepted else {}
    }


async def test_doses_bring_no_entity_and_nothing_to_the_ended_event(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    entity_registry: er.EntityRegistry,
) -> None:
    soda_maker = await add_soda_maker(hass, hass_storage)
    await dose(panel, soda_maker, {"dose-co2": 8, "dose-syrup": 40})
    fired = record_events(hass, "event.soda_maker_run")

    await carbonate(hass, clock)

    assert coinop_entities(entity_registry) == basic_entities("soda_maker")
    assert value(hass, "sensor.soda_maker_material_cost") == pytest.approx(0.56)
    assert value(hass, "sensor.soda_maker_total_cost") == pytest.approx(0.56)
    [_, ended] = fired
    assert (ended["event_type"], ended["energy_kwh"]) == ("ended", 0)
    assert ended["total_cost"] == pytest.approx(0.56)
    assert {"program", "water_litres", "part_count", "material_grams"}.isdisjoint(ended)


async def test_the_devices_command_sends_the_dose_list_and_the_default_row(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    soda_maker = await add_soda_maker(hass, hass_storage)
    await dose(panel, soda_maker, {"dose-co2": 8, "dose-syrup": 40})

    [listed] = (await panel.call("coinop/devices/list"))["devices"]

    assert (listed["type"], listed["type_name"], listed["capabilities"]) == (
        "other",
        "Soda maker",
        ["average_power", "doses"],
    )
    assert listed["settings"]["doses"] == SODA_DOSES
    assert listed["settings"]["program_defaults"] == {
        "default": {"doses": {"dose-co2": 8, "dose-syrup": 40}},
        "programs": {},
    }
    assert listed["known_programs"] == []
    assert "program" not in listed["ha_settings"]


BREW_KETTLE_STATUS = "sensor.brew_kettle_status"
BREW_KETTLE_PROGRAM = "sensor.brew_kettle_program"
BREW_KETTLE_MAPPING = {
    "running": ["brewing"],
    "finished": ["done"],
    "cancelled": ["cancelled"],
}
BREW_DOSES = [
    {"id": "dose-malt", "material_id": "malt"},
    {"id": "dose-hops", "material_id": "hops"},
]
BREW_ROWS = {
    "default": {
        "doses": {"dose-malt": 4000, "dose-hops": 30},
        "kwh": 3.0,
        "litres": 25,
    },
    "programs": {
        "Pale ale": {"doses": {"dose-malt": 4500}, "kwh": 3.6, "litres": 30},
    },
}


async def set_brew_kettle(hass: HomeAssistant, status: str) -> None:
    await report_status(hass, BREW_KETTLE_STATUS, status)


async def set_brew_program(hass: HomeAssistant, program: str) -> None:
    hass.states.async_set(BREW_KETTLE_PROGRAM, program)
    await hass.async_block_till_done()


async def add_brew_kettle(
    hass: HomeAssistant,
    panel: PanelClient,
    hass_storage: dict[str, Any] | None = None,
    *,
    entry: ConfigEntry | None = None,
    **options: Any,
) -> ConfigSubentry:
    """A brew kettle, off, in EUR at 0.30 per kWh and 4.00 per m³: an Other Device
    with the Type Name "Brew kettle" that has a Program (on its Program input, with
    no Program yet), Doses and water, its electricity and its water per Program
    unless `options` say otherwise. `hass_storage` places the `DOSE_MATERIALS`, as for
    `add_soda_maker`; the Doses of its `MALT` and `HOPS` are saved as `BREW_DOSES`,
    with the Program Defaults `BREW_ROWS`."""
    hass.config.currency = "EUR"
    if hass_storage is not None:
        place_materials(hass_storage, *DOSE_MATERIALS)
    await set_brew_kettle(hass, "off")
    await set_brew_program(hass, "unknown")
    brew_kettle: dict[str, Any] = {
        "type_name": "Brew kettle",
        "name": "Brew kettle",
        "status": BREW_KETTLE_STATUS,
        "mapping": BREW_KETTLE_MAPPING,
        "has": ["program", "doses", "water"],
        "program": {"entity_id": BREW_KETTLE_PROGRAM},
        "source": "per_program",
        "water": "per_program",
    }
    subentry = await add_other_device(
        hass, entry or await add_hub(hass), **brew_kettle | options
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={"doses": BREW_DOSES, "program_defaults": BREW_ROWS},
    )
    return subentry


async def brew(
    hass: HomeAssistant,
    clock: Clock,
    program: str | None = None,
    *,
    outcome: str = "done",
) -> None:
    """A brew of four hours ended as `outcome`, on `program` if given."""
    if program is not None:
        await set_brew_program(hass, program)
    await run_once(
        hass, clock, BREW_KETTLE_STATUS, running="brewing", ended=outcome, minutes=240
    )


async def test_program_doses_and_water_bring_the_program_step_and_water_per_program(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)
    steps = []
    menus = {}
    for user_input in (
        other_input("Brew kettle", ["program", "doses", "water"]),
        {},
        {"name": "Brew kettle"},
        {"entity_id": BREW_KETTLE_STATUS},
        BREW_KETTLE_MAPPING,
        {"entity_id": BREW_KETTLE_PROGRAM},
        {},
        {"next_step_id": "per_program"},
        {"next_step_id": "fixed_price"},
        {"price": 0.30},
        {"next_step_id": "water_per_program"},
        {"next_step_id": "water_fixed_price"},
        {"price": 4.0},
    ):
        result = await configure(hass, result, user_input)
        steps.append(result.get("step_id"))
        if "menu_options" in result:
            menus[result["step_id"]] = result["menu_options"]

    assert steps == [
        "device_without_profile",
        "name",
        "status",
        "mapping",
        "program",
        "progress",
        "consumption",
        "price",
        "fixed_price",
        "water",
        "water_price",
        "water_fixed_price",
        None,
    ]
    assert menus["consumption"] == ["energy", "power", "per_program", "none"]
    assert menus["water"] == [
        "water_meter",
        "water_flow",
        "water_per_program",
        "water_none",
    ]
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [brew_kettle] = entry.subentries.values()
    result = await start_reconfigure(hass, entry, brew_kettle)
    assert result["menu_options"] == [
        "other",
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "water",
        "water_price",
        "save",
    ]
    result = await configure(hass, result, {"next_step_id": "water"})
    assert result["menu_options"] == menus["water"]


@pytest.mark.parametrize(
    ("program", "source", "kwh", "litres", "dosed"),
    [
        (
            "Pale ale",
            "program_default",
            (3.6, 1.08),
            (30, 0.12),
            [("dose-malt", "program_default", "malt", 4500, "g", 0.002, 9.0)],
        ),
        (
            "Stout",
            "default_row",
            (3.0, 0.90),
            (25, 0.10),
            [
                ("dose-malt", "default_row", "malt", 4000, "g", 0.002, 8.0),
                ("dose-hops", "default_row", "hops", 30, "g", 0.05, 1.5),
            ],
        ),
        (
            None,
            "default_row",
            (3.0, 0.90),
            (25, 0.10),
            [
                ("dose-malt", "default_row", "malt", 4000, "g", 0.002, 8.0),
                ("dose-hops", "default_row", "hops", 30, "g", 0.05, 1.5),
            ],
        ),
    ],
    ids=["a Program with a row", "a Program without a row", "no Program"],
)
async def test_with_a_program_a_run_takes_its_programs_row_else_the_default_row(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    program: str | None,
    source: str,
    kwh: tuple[float, float],
    litres: tuple[float, float],
    dosed: list[tuple[Any, ...]],
) -> None:
    await add_brew_kettle(hass, panel, hass_storage)

    await brew(hass, clock, program)

    [run] = stored_runs(hass_storage)
    assert (run.get("program"), run["name"]) == (program, program)
    assert approx(consumed(run)) == [
        ("electricity", "program_default", *kwh[:1], "kWh", kwh[1]),
        ("water", "program_default", *litres[:1], "L", litres[1]),
    ]
    assert doses(run) == dosed
    assert {item["dose_source"] for item in run["line_items"][2:]} == {source}
    assert (run["outcome"], run["flags"]) == ("completed", [])


async def test_correcting_the_program_takes_the_new_programs_doses_and_litres(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await add_brew_kettle(hass, panel, hass_storage)
    await brew(hass, clock, "Stout")
    [run] = stored_runs(hass_storage)

    result = await panel.call(
        "coinop/runs/update", run_id=run["id"], program="Pale ale"
    )

    corrected = result["run"]
    assert approx(consumed(corrected)) == [
        ("electricity", "program_default", 3.6, "kWh", 1.08),
        ("water", "program_default", 30, "L", 0.12),
    ]
    assert doses(corrected) == [
        ("dose-malt", "program_default", "malt", 4500, "g", 0.002, 9.0)
    ]


async def test_the_devices_command_sends_program_doses_and_water(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_brew_kettle(hass, panel, hass_storage)

    [listed] = (await panel.call("coinop/devices/list"))["devices"]

    assert (listed["type_name"], listed["capabilities"]) == (
        "Brew kettle",
        ["doses", "program", "program_consumption", "water"],
    )
    assert listed["settings"]["doses"] == BREW_DOSES
    assert listed["settings"]["program_defaults"] == BREW_ROWS
    settings = listed["ha_settings"]
    assert (settings["consumption"], settings["water"]) == (
        {"source": "per_program"},
        {"source": "per_program"},
    )
    assert settings["water_price"] == {"source": "fixed", "value": 4.0}
