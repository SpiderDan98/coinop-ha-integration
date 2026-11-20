"""Program Defaults: a Run's Doses from the row of its Program."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_hub, add_washing_machine
from .stored import place_materials
from .test_doses import DOSES, LIQUID, PODS, SCALE, WHITENER, doses, set_scale
from .test_programs import WASHER_PROGRAM, set_program
from .test_runs import stored_runs
from .test_washing_machines import set_energy, set_washer, wash
from .websocket import PanelClient

ROWS = {
    "default": {"doses": {"dose-liquid": 75}},
    "programs": {
        "White 60°": {"doses": {"dose-liquid": 60, "dose-whitener": 20}},
        "Cotton 40°": {"doses": {"dose-pods": 1}},
    },
}


@pytest.fixture
async def washer(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> ConfigSubentry:
    """A washing machine with a Program input and the laundry Materials."""
    hass.config.currency = "EUR"
    place_materials(hass_storage, LIQUID, PODS, WHITENER)
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    await set_program(hass, "unknown")
    return await add_washing_machine(
        hass, await add_hub(hass), program={"entity_id": WASHER_PROGRAM}, price=0.50
    )


async def set_rows(
    panel: PanelClient, washer: ConfigSubentry, rows: dict[str, Any] = ROWS
) -> Any:
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES, "program_defaults": rows},
    )
    return result["settings"]


@pytest.mark.parametrize(
    ("program", "dosed"),
    [
        (
            "White 60°",
            [
                ("dose-liquid", "program_default", "liquid", 60, "ml", 0.006, 0.36),
                ("dose-whitener", "program_default", "whitener", 20, "g", 0.004, 0.08),
            ],
        ),
        (
            "Cotton 40°",
            [("dose-pods", "program_default", "pods", 1, "pcs", 0.30, 0.30)],
        ),
        (
            "Eco 40-60",
            [("dose-liquid", "default_row", "liquid", 75, "ml", 0.006, 0.45)],
        ),
    ],
)
async def test_a_run_is_dosed_from_the_row_of_its_program(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    program: str,
    dosed: list[tuple[Any, ...]],
) -> None:
    await set_rows(panel, washer)
    await set_program(hass, program)

    await wash(hass, clock)

    [run] = stored_runs(hass_storage)
    assert doses(run) == dosed


async def test_a_late_program_switches_the_open_runs_doses_to_its_row(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer)
    await set_washer(hass, "running")
    await clock.advance(minutes=5)

    await set_program(hass, "Cotton 40°")

    [running] = (await panel.call("coinop/runs/list"))["runs"]
    assert (running["program"], running["total"]) == ("Cotton 40°", 0.30)


async def test_the_doses_freeze_with_the_last_program(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await set_program(hass, "White 60°")
    await wash(hass, clock)

    await set_program(hass, "Cotton 40°")
    await set_rows(panel, washer, {"default": {"doses": {}}})

    [run] = stored_runs(hass_storage)
    assert [d[:2] for d in doses(run)] == [
        ("dose-liquid", "program_default"),
        ("dose-whitener", "program_default"),
    ]


async def test_a_cancelled_run_is_flagged_for_its_programs_defaults(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer, ROWS | {"default": {"doses": {}}})
    await set_program(hass, "Cotton 40°")
    await set_washer(hass, "running")
    await clock.advance(minutes=10)

    await set_washer(hass, "cancelled")
    await set_energy(hass, 100.2)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["ended_early_defaults"]


async def test_known_programs_come_from_the_input_and_past_runs(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    for program in ("Wool", " Eco 40-60 ", "Cotton 40°"):
        await set_program(hass, program)
        await wash(hass, clock)

    await set_program(hass, "Cotton 40°", {"options": ["Cotton 40°", "White 60°", " "]})

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["known_programs"] == ["Cotton 40°", "White 60°", "Eco 40-60", "Wool"]


async def test_a_removed_dose_leaves_every_row(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer)

    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES[:2]},
    )

    assert result["settings"]["program_defaults"] == {
        "default": {"doses": {"dose-liquid": 75}},
        "programs": {
            "White 60°": {"doses": {"dose-liquid": 60}},
            "Cotton 40°": {"doses": {"dose-pods": 1}},
        },
    }


async def test_program_rows_are_stored_by_their_trimmed_name(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    settings = await set_rows(
        panel,
        washer,
        {"default": {"doses": {}}, "programs": {" Rinse ": {"doses": {}}}},
    )

    assert settings["program_defaults"]["programs"] == {"Rinse": {"doses": {}}}
    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "program_defaults": {
                "default": {"doses": {}},
                "programs": {" ": {"doses": {}}},
            }
        },
    )
    assert error["code"] == "invalid_format"


async def test_an_unavailable_stock_input_falls_back_to_the_program_s_row(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, "unavailable")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "doses": [DOSES[2] | {"stock": {"entity_id": SCALE}}],
            "program_defaults": ROWS,
        },
    )
    await set_program(hass, "White 60°")

    await wash(hass, clock)
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-whitener", "program_default", "whitener", 20, "g", 0.004, 0.08)
    ]
    assert run["flags"] == ["stock_input_unavailable"]
