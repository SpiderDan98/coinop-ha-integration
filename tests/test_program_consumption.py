"""Electricity and water per Program: the kWh and litres of the Program Defaults."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    WASHER_MAPPING,
    WASHER_STATUS,
    add_hub,
    add_washing_machine,
    configure,
    walk_to_mapping,
)
from .test_programs import WASHER_PROGRAM, set_program
from .test_runs import stored_runs
from .test_washing_machines import set_washer
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
    hass.config.currency = "EUR"
    await set_washer(hass, "off")
    await set_program(hass, "unknown")
    return await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": WASHER_PROGRAM},
        source="per_program",
        water="per_program",
    )


async def run_cycle(
    hass: HomeAssistant, clock: Clock, outcome: str = "finished"
) -> None:
    await set_washer(hass, "running")
    await clock.advance(minutes=90)
    await set_washer(hass, outcome)


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

    await run_cycle(hass, clock)

    [run] = stored_runs(hass_storage)
    assert consumed(run) == approx(expected)
    assert run["flags"] == []
