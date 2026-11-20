"""Electricity and water per Program: the kWh and litres of the Program Defaults."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    WASHER_MAPPING,
    WASHER_STATUS,
    WATER_PRICE,
    add_hub,
    add_washing_machine,
    configure,
    walk_to_mapping,
)
from .test_runs import stored_runs
from .test_water import set_water, set_water_price
from .washing import (
    add_washer,
    set_energy,
    set_program,
    set_washer,
    washed,
)
from .websocket import PanelClient


async def test_electricity_and_water_can_come_per_program(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass, entry, status=WASHER_STATUS, device_type="washing_machine"
    )
    result = await configure(hass, result, WASHER_MAPPING)
    result = await configure(hass, result, {})
    assert result["menu_options"] == ["energy", "power", "per_program"]
    result = await configure(hass, result, {"next_step_id": "per_program"})
    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["menu_options"] == [
        "water_meter",
        "water_flow",
        "water_per_program",
        "water_none",
    ]
    result = await configure(hass, result, {"next_step_id": "water_per_program"})
    assert result["step_id"] == "water_price"
    result = await configure(hass, result, {"next_step_id": "water_fixed_price"})
    result = await configure(hass, result, {"price": 4.0})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data: dict[str, Any] = result["data"]
    assert (data["consumption"], data["water"]) == (
        {"source": "per_program"},
        {"source": "per_program"},
    )
    assert data["water_price"] == {"source": "fixed", "value": 4.0}


ROWS = {
    "default": {"doses": {}, "kwh": 0.8, "litres": 40},
    "programs": {
        "Cotton 60°": {"doses": {}, "kwh": 1.5, "litres": 60},
        "Wool": {"doses": {}},
    },
}


async def set_rows(
    panel: PanelClient, washer: ConfigSubentry, rows: dict[str, Any] = ROWS
) -> Any:
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"program_defaults": rows},
    )
    return result["settings"]


@pytest.fixture
async def washer(hass: HomeAssistant, clock: Clock) -> ConfigSubentry:
    """A washing machine with electricity and water per Program and a Program
    input, at 0.30 per kWh and 4.00 per m³."""
    return await add_washer(hass, source="per_program", water="per_program")


def consumed(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (i["kind"], i["method"], i["quantity"], i["unit"], i["amount"])
        for i in run["line_items"]
        if i["kind"] in ("electricity", "water")
    ]


def approx(items: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [
        tuple(pytest.approx(v) if isinstance(v, float | int) else v for v in item)
        for item in items
    ]


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        (
            "Cotton 60°",
            [
                ("electricity", "program_default", 1.5, "kWh", 0.45),
                ("water", "program_default", 60, "L", 0.24),
            ],
        ),
        (
            "Eco 40-60",
            [
                ("electricity", "program_default", 0.8, "kWh", 0.24),
                ("water", "program_default", 40, "L", 0.16),
            ],
        ),
    ],
)
async def test_a_run_gets_electricity_and_water_from_its_programs_row(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    program: str,
    expected: list[tuple[Any, ...]],
) -> None:
    await set_rows(panel, washer)
    await set_program(hass, program)

    await washed(hass, clock)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == approx(expected)
    assert run["flags"] == []


async def test_a_program_row_without_kwh_and_litres_leaves_them_empty_and_flagged(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await set_program(hass, "Wool")

    await washed(hass, clock)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == [
        ("electricity", "program_default", None, "kWh", 0.0),
        ("water", "program_default", None, "L", 0.0),
    ]
    assert run["flags"] == ["default_missing"]


async def test_entering_the_missing_quantities_clears_the_flag(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_program(hass, "Wool")
    await washed(hass, clock)
    [run] = stored_runs(hass_storage)

    for item in run["line_items"]:
        await panel.call(
            "coinop/line_items/update",
            run_id=run["id"],
            line_item_id=item["id"],
            quantity=1.0,
        )

    [run] = stored_runs(hass_storage)
    assert run["flags"] == []
    assert consumed(run) == approx(
        [
            ("electricity", "program_default", 1.0, "kWh", 0.30),
            ("water", "program_default", 1.0, "L", 0.004),
        ]
    )


async def test_an_open_runs_defaults_follow_its_program_live(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer)
    await set_washer(hass, "running")
    await clock.advance(minutes=10)
    [running] = (await panel.call("coinop/runs/list"))["runs"]
    assert running["total"] == pytest.approx(0.24 + 0.16)

    await set_program(hass, "Cotton 60°")

    [running] = (await panel.call("coinop/runs/list"))["runs"]
    assert running["total"] == pytest.approx(0.45 + 0.24)


async def test_a_default_is_priced_across_a_price_change_by_running_time(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    hass.config.currency = "EUR"
    await set_washer(hass, "off")
    await set_water_price(hass, 4.0)
    washer = await add_washing_machine(
        hass,
        await add_hub(hass),
        source="per_program",
        water="per_program",
        water_price={"entity_id": WATER_PRICE},
    )
    await set_rows(panel, washer)
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_water_price(hass, 5.0)
    await clock.advance(minutes=10)

    await set_washer(hass, "finished")

    [run] = stored_runs(hass_storage)
    item = next(i for i in run["line_items"] if i["kind"] == "water")
    assert [(s["kwh"], s["unit_price"]) for s in item["segments"]] == [
        (pytest.approx(30), pytest.approx(0.004)),
        (pytest.approx(10), pytest.approx(0.005)),
    ]
    assert item["amount"] == pytest.approx(30 * 0.004 + 10 * 0.005)


async def test_a_meter_silent_for_the_whole_run_falls_back_to_the_default(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    await set_washer(hass, "off")
    washer = await add_washing_machine(hass, await add_hub(hass), water="meter")
    await set_rows(panel, washer)
    await set_energy(hass, STATE_UNAVAILABLE)
    await set_water(hass, STATE_UNAVAILABLE)

    await washed(hass, clock)
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == approx(
        [
            ("electricity", "program_default", 0.8, "kWh", 0.24),
            ("water", "program_default", 40, "L", 0.16),
        ]
    )
    assert run["flags"] == ["consumption_gap"]


async def test_a_silent_meter_without_a_default_leaves_the_quantity_empty(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, STATE_UNAVAILABLE)
    await set_washer(hass, "off")
    await add_washing_machine(hass, await add_hub(hass))

    await washed(hass, clock)
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == [("electricity", "program_default", None, "kWh", 0.0)]
    assert run["flags"] == ["consumption_gap", "default_missing"]


async def test_a_meter_that_reported_keeps_measuring_through_a_gap(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    washer = await add_washing_machine(hass, await add_hub(hass))
    await set_rows(panel, washer)
    await set_washer(hass, "running")
    await clock.advance(minutes=1)
    await set_energy(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=89)
    await set_energy(hass, 101)

    await set_washer(hass, "finished")
    await set_energy(hass, 101)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == approx([("electricity", "measured", 1.0, "kWh", 0.30)])
    assert run["flags"] == ["consumption_gap"]


async def test_a_cancelled_run_is_flagged_for_its_default_water(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)

    await washed(hass, clock, outcome="cancelled")

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["ended_early_defaults"]


async def test_a_cancelled_run_is_not_flagged_for_default_electricity_alone(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer, {"default": {"doses": {}, "kwh": 0.8}})

    await washed(hass, clock, outcome="cancelled")

    [run] = stored_runs(hass_storage)
    assert [item[:3] for item in consumed(run)] == [
        ("electricity", "program_default", 0.8),
        ("water", "program_default", None),
    ]
    assert run["flags"] == ["default_missing"]
