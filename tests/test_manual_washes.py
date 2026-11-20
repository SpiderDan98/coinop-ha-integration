"""Manual washing machine Runs: a forgotten load added by hand."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub, add_washing_machine
from .stored import place_materials
from .test_doses import DOSES, LIQUID, PODS, SCALE, WHITENER, doses, set_scale
from .test_manual_runs import at, create
from .test_program_consumption import approx, consumed
from .test_programs import WASHER_PROGRAM, set_program
from .test_washing_machines import set_washer
from .websocket import PanelClient

ROWS = {
    "default": {"doses": {"dose-liquid": 75}, "kwh": 0.8, "litres": 40},
    "programs": {
        "Cotton 60°": {
            "doses": {"dose-liquid": 60, "dose-whitener": 20},
            "kwh": 1.5,
            "litres": 60,
        },
        "Wool": {"doses": {"dose-pods": 1}},
    },
}


@pytest.fixture
async def washer(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], panel: PanelClient
) -> ConfigSubentry:
    """A washing machine with electricity and water per Program, the laundry
    Doses and ROWS, at 0.30 per kWh and 4.00 per m³."""
    hass.config.currency = "EUR"
    place_materials(hass_storage, LIQUID, PODS, WHITENER)
    await set_washer(hass, "off")
    await set_program(hass, "unknown")
    washer = await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": WASHER_PROGRAM},
        source="per_program",
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES, "program_defaults": ROWS},
    )
    await clock.advance(hours=3)
    return washer


async def test_a_manual_wash_takes_electricity_water_and_doses_from_its_programs_row(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    run = await create(panel, washer.subentry_id, name=None, program=" Cotton 60° ")

    assert (run["program"], run["name"], run["part_count"]) == (
        "Cotton 60°",
        "Cotton 60°",
        None,
    )
    assert consumed(run) == approx(
        [
            ("electricity", "program_default", 1.5, "kWh", 0.45),
            ("water", "program_default", 60, "L", 0.24),
        ]
    )
    assert doses(run) == [
        ("dose-liquid", "program_default", "liquid", 60, "ml", 0.006, 0.36),
        ("dose-whitener", "program_default", "whitener", 20, "g", 0.004, 0.08),
    ]
    assert run["flags"] == []


async def test_a_program_without_a_row_takes_the_default_row(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    run = await create(panel, washer.subentry_id, program="Eco 40-60")

    assert consumed(run) == approx(
        [
            ("electricity", "program_default", 0.8, "kWh", 0.24),
            ("water", "program_default", 40, "L", 0.16),
        ]
    )
    assert doses(run) == [
        ("dose-liquid", "default_row", "liquid", 75, "ml", 0.006, 0.45)
    ]


async def test_a_row_without_kwh_and_litres_leaves_them_empty_and_flagged(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    run = await create(panel, washer.subentry_id, program="Wool")

    assert consumed(run) == [
        ("electricity", "program_default", None, "kWh", 0.0),
        ("water", "program_default", None, "L", 0.0),
    ]
    assert doses(run) == [("dose-pods", "program_default", "pods", 1, "pcs", 0.3, 0.3)]
    assert run["flags"] == ["default_missing"]


async def test_a_cancelled_manual_wash_is_flagged_for_its_defaults(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    run = await create(
        panel, washer.subentry_id, program="Cotton 60°", outcome="cancelled"
    )

    assert run["flags"] == ["ended_early_defaults"]


async def test_a_manual_wash_does_not_read_stock_inputs(
    hass: HomeAssistant, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_scale(hass, 500)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": [*DOSES[:2], DOSES[2] | {"stock": {"entity_id": SCALE}}]},
    )
    await set_scale(hass, 450)

    run = await create(panel, washer.subentry_id, program="Cotton 60°")

    assert [(d[0], d[1], d[3]) for d in doses(run)] == [
        ("dose-liquid", "program_default", 60),
        ("dose-whitener", "program_default", 20),
    ]
    assert run["flags"] == []


async def test_only_a_device_with_programs_takes_a_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    printer = await add_device(hass, await add_hub(hass))
    await clock.advance(hours=3)

    error = await panel.error(
        "coinop/runs/create",
        device_id=printer.subentry_id,
        started=at(0),
        ended=at(2),
        outcome="completed",
        program="Cotton 60°",
    )

    assert error["code"] == "not_allowed"
