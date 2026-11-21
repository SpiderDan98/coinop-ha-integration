"""Coffee machines: the washing machine's Capabilities with a drink's small amounts."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_STATUS,
    WASHER_WATER,
    add_hub,
    add_washing_machine,
    configure,
    start_reconfigure,
    walk_to_mapping,
)
from .http import HttpClient
from .stored import place_materials, stored_material
from .test_cost_statement import export
from .test_doses import doses
from .test_program_consumption import consumed
from .test_runs import stored_runs
from .test_water import set_water
from .washing import add_washer, set_energy, set_program, set_washer
from .websocket import PanelClient


def ingredient(material_id: str, pack_unit: str, **fields: Any) -> dict[str, Any]:
    return stored_material(
        material_id,
        form="beverage_ingredient",
        diameter=None,
        price={"source": "fixed", "pack_size": 1000.0, "pack_unit": pack_unit}
        | fields.pop("price"),
        **fields,
    )


# 0.02 per g, 0.0012 per ml.
BEANS = ingredient(
    "beans", "g", type="Coffee beans", density=0.4, price={"pack_price": 20.0}
)
MILK = ingredient("milk", "ml", type="Milk", density=1.03, price={"pack_price": 1.2})
DOSES = [
    {"id": "dose-beans", "material_id": "beans"},
    {"id": "dose-milk", "material_id": "milk"},
]
ROWS = {
    "default": {"doses": {"dose-beans": 8}, "kwh": 0.02, "litres": 0.125},
    "programs": {
        "Espresso": {"doses": {"dose-beans": 8}, "kwh": 0.012, "litres": 0.04},
        "Cappuccino": {
            "doses": {"dose-beans": 9, "dose-milk": 120},
            "kwh": 0.025,
            "litres": 0.06,
        },
    },
}


async def add_coffee_machine(
    hass: HomeAssistant, hass_storage: dict[str, Any], panel: PanelClient
) -> ConfigSubentry:
    """A Coffee machine with the Doses and ROWS above and electricity and water per
    Program, at 0.30 per kWh and 4.00 per m³."""
    place_materials(hass_storage, BEANS, MILK)
    coffee_machine = await add_washer(
        hass,
        name="Coffee machine",
        device_type="coffee_machine",
        source="per_program",
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=coffee_machine.subentry_id,
        settings={"doses": DOSES, "program_defaults": ROWS},
    )
    return coffee_machine


async def brewed(hass: HomeAssistant, clock: Clock, program: str) -> None:
    """A drink of 40 seconds on `program`."""
    await set_program(hass, program)
    await set_washer(hass, "running")
    await clock.advance(seconds=40)
    await set_washer(hass, "finished")


async def test_a_coffee_machine_walks_the_washing_machines_steps(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass,
        entry,
        name="Coffee machine",
        status=WASHER_STATUS,
        device_type="coffee_machine",
    )
    result = await configure(hass, result, WASHER_MAPPING)
    assert result["step_id"] == "program"
    result = await configure(hass, result, {})
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "per_program"],
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
    [coffee_machine] = entry.subentries.values()
    assert coffee_machine.data["device_type"] == "coffee_machine"
    assert sorted(coffee_machine.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "status",
        "water",
        "water_price",
    ]


async def test_reconfiguring_a_coffee_machine_offers_the_washing_machines_sections(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    entry = await add_hub(hass)
    coffee_machine = await add_washing_machine(
        hass, entry, device_type="coffee_machine", water="meter"
    )

    result = await start_reconfigure(hass, entry, coffee_machine)

    assert result["menu_options"] == [
        "status",
        "program",
        "consumption",
        "price",
        "water",
        "water_price",
        "save",
    ]


async def test_a_programs_water_of_a_few_hundredths_of_a_litre_is_stored_unrounded(
    hass: HomeAssistant, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await add_coffee_machine(hass, hass_storage, panel)

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert device["settings"]["program_defaults"] == ROWS
    assert (device["type"], device["capabilities"]) == (
        "coffee_machine",
        ["doses", "per_run_meters", "program", "program_consumption", "water"],
    )


async def test_an_espressos_water_line_item_has_exactly_its_programs_litres(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_coffee_machine(hass, hass_storage, panel)

    await brewed(hass, clock, "Espresso")

    [stored] = stored_runs(hass_storage)
    assert (stored["program"], stored["name"], stored["flags"]) == (
        "Espresso",
        "Espresso",
        [],
    )
    run = (await panel.call("coinop/runs/get", run_id=stored["id"]))["run"]
    # 0.04 L at 4.00 per m³ is 0.00016: the amount rounds away, the quantity stays.
    assert consumed(run) == [
        ("electricity", "program_default", 0.012, "kWh", 0.0),
        ("water", "program_default", 0.04, "L", 0.0),
    ]
    assert run["subtotals"]["water"] == 0.0


async def test_a_cappuccino_costs_more_than_an_espresso(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
) -> None:
    await add_coffee_machine(hass, hass_storage, panel)

    await brewed(hass, clock, "Espresso")
    await clock.advance(minutes=5)
    await brewed(hass, clock, "Cappuccino")

    espresso, cappuccino = stored_runs(hass_storage)
    assert [(i[1], i[2]) for i in consumed(espresso)] == [
        ("program_default", 0.012),
        ("program_default", 0.04),
    ]
    assert [(i[1], i[2]) for i in consumed(cappuccino)] == [
        ("program_default", 0.025),
        ("program_default", 0.06),
    ]
    assert doses(espresso) == [
        ("dose-beans", "program_default", "beans", 8, "g", 0.02, 0.16),
    ]
    assert doses(cappuccino) == [
        ("dose-beans", "program_default", "beans", 9, "g", 0.02, 0.18),
        ("dose-milk", "program_default", "milk", 120, "ml", 0.0012, 0.144),
    ]
    runs = (await panel.call("coinop/runs/list"))["runs"]
    assert {run["name"]: run["total"] for run in runs} == {
        "Espresso": 0.16,
        "Cappuccino": 0.33,
    }


async def test_a_cost_statement_shows_a_drinks_water_to_the_millilitre(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    browser: HttpClient,
) -> None:
    await add_coffee_machine(hass, hass_storage, panel)
    await brewed(hass, clock, "Espresso")
    await clock.advance(minutes=5)
    await brewed(hass, clock, "Americano")
    run_ids = [run["id"] for run in stored_runs(hass_storage)]

    english = await export(panel, browser, run_ids=run_ids)
    german = await export(panel, browser, run_ids=run_ids, language="de")

    assert "Water 0.04 L × €4.00/m³ €0.00" in english.lines  # noqa: RUF001
    assert "Wasser 0,04 L × 4,00 €/m³ 0,00 €" in german.lines  # noqa: RUF001
    # The Default row's 0.125 L.
    assert "Water 0.125 L × €4.00/m³ €0.00" in english.lines  # noqa: RUF001
