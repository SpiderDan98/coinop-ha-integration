"""Measured suggestions: the mean measured kWh and litres per Program row."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import WASHER_ENERGY, WASHER_WATER
from .test_runs import stored_runs
from .test_water import set_water
from .washing import add_washer, set_energy, set_program, set_washer
from .websocket import PanelClient


@pytest.fixture
async def washer(hass: HomeAssistant, clock: Clock) -> ConfigSubentry:
    """A washing machine with energy and water meters and a Program input."""
    await set_water(hass, 1000)
    return await add_washer(hass, water="meter")


def reading(hass: HomeAssistant, entity_id: str) -> float:
    state = hass.states.get(entity_id)
    assert state is not None
    return float(state.state)


async def report(hass: HomeAssistant, readings: dict[str, float]) -> None:
    for entity_id, value in readings.items():
        await (set_water if entity_id == WASHER_WATER else set_energy)(hass, value)


async def load(
    hass: HomeAssistant,
    clock: Clock,
    program: str | None,
    kwh: float | None,
    litres: float,
    outcome: str = "finished",
) -> None:
    """A 90-minute load, finalised at its end; with `kwh` None the energy meter is
    unavailable throughout."""
    meters = [(WASHER_WATER, litres)] + (
        [(WASHER_ENERGY, kwh)] if kwh is not None else []
    )
    starts = {entity_id: reading(hass, entity_id) for entity_id, _ in meters}
    if program is not None:
        await set_program(hass, program)
    await set_washer(hass, "running")
    # Reported at the start, so the meters aren't interpolated from the last Run's end.
    await report(hass, starts)
    await clock.advance(minutes=90)
    ends = {entity_id: starts[entity_id] + used for entity_id, used in meters}
    await report(hass, ends)
    await set_washer(hass, outcome)
    await report(hass, ends)
    await set_program(hass, "unknown")
    await clock.advance(minutes=10)


async def suggestions(panel: PanelClient, washer: ConfigSubentry) -> Any:
    result = await panel.call(
        "coinop/devices/measured_suggestions", device_id=washer.subentry_id
    )
    return result["suggestions"]


async def set_rows(
    panel: PanelClient, washer: ConfigSubentry, programs: dict[str, Any]
) -> Any:
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"program_defaults": {"default": {"doses": {}}, "programs": programs}},
    )
    return result["settings"]


async def test_a_program_suggests_the_mean_of_its_measured_completed_runs(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40)
    await load(hass, clock, "Eco 40-60", kwh=0.9, litres=45)
    await load(hass, clock, "Eco 40-60", kwh=1.3, litres=50)
    await load(hass, clock, "Eco 40-60", kwh=0.2, litres=10, outcome="cancelled")

    assert (await suggestions(panel, washer))["programs"] == {
        "Eco 40-60": {
            "kwh": {"mean": 1.0, "runs": 3},
            "litres": {"mean": 45.0, "runs": 3},
        }
    }


async def test_a_mean_of_under_a_litre_is_suggested_to_the_millilitre(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await load(hass, clock, "Espresso", kwh=0.012, litres=0.04)
    await load(hass, clock, "Espresso", kwh=0.012, litres=0.05)
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40.12)
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40.14)

    assert (await suggestions(panel, washer))["programs"] == {
        "Espresso": {
            "kwh": {"mean": 0.012, "runs": 2},
            "litres": {"mean": 0.045, "runs": 2},
        },
        "Eco 40-60": {
            "kwh": {"mean": 0.8, "runs": 2},
            "litres": {"mean": 40.1, "runs": 2},
        },
    }


async def test_default_sourced_values_are_left_out(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer, {"Eco 40-60": {"doses": {}, "kwh": 0.5}})
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40)
    await set_energy(hass, STATE_UNAVAILABLE)
    await load(hass, clock, "Eco 40-60", kwh=None, litres=50)
    assert [item["method"] for item in stored_runs(hass_storage)[-1]["line_items"]] == [
        "program_default",
        "measured",
    ]

    assert (await suggestions(panel, washer))["programs"] == {
        "Eco 40-60": {
            "kwh": {"mean": 0.8, "runs": 1},
            "litres": {"mean": 45.0, "runs": 2},
        }
    }


async def test_an_overridden_quantity_suggests_what_was_measured(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40)
    await load(hass, clock, "Eco 40-60", kwh=1.0, litres=50)
    run = stored_runs(hass_storage)[-1]
    for item, quantity in zip(run["line_items"], (5, 500), strict=True):
        await panel.call(
            "coinop/line_items/update",
            run_id=run["id"],
            line_item_id=item["id"],
            quantity=quantity,
        )

    assert (await suggestions(panel, washer))["programs"] == {
        "Eco 40-60": {
            "kwh": {"mean": 0.9, "runs": 2},
            "litres": {"mean": 45.0, "runs": 2},
        }
    }


async def test_the_default_row_suggests_from_runs_without_a_program_row(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer, {"Wool": {"doses": {}}})
    await load(hass, clock, "Wool", kwh=0.4, litres=30)
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40)
    await load(hass, clock, None, kwh=1.2, litres=60)

    assert await suggestions(panel, washer) == {
        "default": {
            "kwh": {"mean": 1.0, "runs": 2},
            "litres": {"mean": 50.0, "runs": 2},
        },
        "programs": {
            "Wool": {
                "kwh": {"mean": 0.4, "runs": 1},
                "litres": {"mean": 30.0, "runs": 1},
            },
            "Eco 40-60": {
                "kwh": {"mean": 0.8, "runs": 1},
                "litres": {"mean": 40.0, "runs": 1},
            },
        },
    }


async def test_applying_a_suggestion_leaves_ended_runs_as_they_are(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await load(hass, clock, "Eco 40-60", kwh=0.8, litres=40)
    ended = stored_runs(hass_storage)
    suggested = (await suggestions(panel, washer))["programs"]["Eco 40-60"]

    settings = await set_rows(
        panel, washer, {"Eco 40-60": {"doses": {}, "kwh": suggested["kwh"]["mean"]}}
    )

    assert settings["program_defaults"]["programs"] == {
        "Eco 40-60": {"doses": {}, "kwh": 0.8}
    }
    assert stored_runs(hass_storage) == ended


async def test_suggestions_are_for_a_known_device(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    error = await panel.error("coinop/devices/measured_suggestions", device_id="gone")

    assert error["code"] == "not_found"
