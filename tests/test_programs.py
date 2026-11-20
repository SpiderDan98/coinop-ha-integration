"""The Program a washing machine Run ran, from its Program Device Input."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_STATUS,
    add_device,
    add_hub,
    add_washing_machine,
    configure,
    reconfigure,
    walk_to_mapping,
)
from .http import HttpClient
from .test_cost_statement import export
from .test_device_flow import fields
from .test_run_event import record_events
from .test_runs import set_status, stored_runs
from .washing import (
    WASHER_PROGRAM,
    add_washer,
    set_energy,
    set_program,
    set_washer,
    washed,
)
from .websocket import PanelClient


async def test_the_program_step_follows_the_status_mapping(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, status=WASHER_STATUS, device_type="washing_machine"
    )
    result = await configure(hass, result, WASHER_MAPPING)

    assert result["step_id"] == "program"
    assert fields(result) == ["entity_id", "attribute", "ignored"]
    result = await configure(
        hass, result, {"entity_id": WASHER_PROGRAM, "attribute": "program"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "consumption"


async def test_the_program_step_is_optional(hass: HomeAssistant) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)

    subentry = await add_washing_machine(hass, entry)

    assert subentry.data["program"] == {"entity_id": None, "attribute": None}


async def test_a_program_input_is_stored_with_its_attribute(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)

    subentry = await add_washing_machine(
        hass, entry, program={"entity_id": WASHER_PROGRAM, "attribute": "program"}
    )

    assert subentry.data["program"] == {
        "entity_id": WASHER_PROGRAM,
        "attribute": "program",
    }
    assert subentry.data["consumption"]["entity_id"] == WASHER_ENERGY


@pytest.fixture
async def programmed(hass: HomeAssistant, clock: Clock) -> ConfigSubentry:
    """A washing machine whose Program input is `WASHER_PROGRAM`'s state."""
    return await add_washer(hass, price=0.50)


@pytest.mark.usefixtures("programmed")
async def test_a_late_and_corrected_program_ends_up_on_the_one_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_washer(hass, "running")
    await clock.advance(minutes=4)
    await set_program(hass, "Cotton 40")
    await clock.advance(minutes=3)
    await set_program(hass, " Cotton 60° ")
    await clock.advance(minutes=80)
    await set_washer(hass, "finished")
    await set_energy(hass, 101)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"], run["outcome"]) == (
        "Cotton 60°",
        "Cotton 60°",
        "completed",
    )


@pytest.mark.usefixtures("programmed")
async def test_an_unavailable_program_input_keeps_the_last_program(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_program(hass, "Eco 40-60")
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_program(hass, "unavailable")
    await clock.advance(minutes=30)
    await set_program(hass, "  ")
    await set_washer(hass, "finished")
    await set_program(hass, "Quick 15")
    await set_energy(hass, 101)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"]) == ("Eco 40-60", "Eco 40-60")


async def test_values_the_program_input_ignores_are_like_no_program(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    await set_program(hass, "Standby")
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": WASHER_PROGRAM, "ignored": ["Standby", "Detecting"]},
    )
    assert subentry.data["program"]["ignored"] == ["Standby", "Detecting"]

    await set_washer(hass, "running")
    await set_program(hass, "Wool")
    await clock.advance(minutes=30)
    await set_program(hass, "Detecting")
    await set_washer(hass, "finished")
    await set_energy(hass, 101)

    [run] = stored_runs(hass_storage)
    assert (run["program"], run["name"]) == ("Wool", "Wool")


async def test_a_renamed_run_keeps_its_name_when_the_program_changes(
    hass: HomeAssistant,
    clock: Clock,
    programmed: ConfigSubentry,
    panel: PanelClient,
) -> None:
    await set_washer(hass, "running")
    await set_program(hass, "Cotton 40")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], name="Bedding")

    await set_program(hass, "Cotton 60")

    detail = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert (detail["program"], detail["name"]) == ("Cotton 60", "Bedding")


async def test_a_program_attribute_is_followed(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": WASHER_PROGRAM, "attribute": "program"},
    )

    await set_program(hass, "on", {"program": "Wool 30"})
    await set_washer(hass, "running")

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["name"]) == ("Wool 30", "Wool 30")


async def test_a_new_program_input_applies_to_the_open_run_at_once(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    entry = await add_hub(hass)
    subentry = await add_washing_machine(hass, entry)
    await set_washer(hass, "running")
    await set_program(hass, "Mix 40")

    await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "program"},
        {"entity_id": WASHER_PROGRAM},
    )

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["name"], run["ended"]) == ("Mix 40", "Mix 40", None)


@pytest.mark.usefixtures("programmed")
async def test_correcting_the_program_of_an_ended_run_changes_no_line_item(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_program(hass, "Cotton 40")
    await washed(hass, clock, kwh=1.2)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    before = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]

    after = (
        await panel.call("coinop/runs/update", run_id=run["id"], program=" Cotton 60 ")
    )["run"]

    assert (after["program"], after["name"]) == ("Cotton 60", "Cotton 40")
    assert after["line_items"] == before["line_items"]
    assert after["total"] == before["total"] == 0.6
    cleared = await panel.call("coinop/runs/update", run_id=run["id"], program="")
    assert cleared["run"]["program"] is None


@pytest.mark.usefixtures("programmed")
async def test_correcting_the_program_of_an_open_run_renames_it_alike(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    await set_program(hass, "Cotton 40")
    await set_washer(hass, "running")
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    updated = await panel.call(
        "coinop/runs/update", run_id=run["id"], program="Delicates"
    )

    assert (updated["run"]["program"], updated["run"]["name"]) == (
        "Delicates",
        "Delicates",
    )


@pytest.mark.usefixtures("programmed")
async def test_the_ended_event_and_last_run_cost_carry_the_program(
    hass: HomeAssistant, clock: Clock
) -> None:
    fired = record_events(hass, "event.washer_run")
    await set_program(hass, "Cotton 60°")

    await washed(hass, clock, kwh=1.2)

    [_, ended] = fired
    assert ended["program"] == "Cotton 60°"
    last = hass.states.get("sensor.washer_last_run_cost")
    assert last is not None
    assert last.attributes["program"] == "Cotton 60°"


async def test_a_printer_run_has_no_program_to_correct(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_device(hass, await add_hub(hass))
    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    error = await panel.error("coinop/runs/update", run_id=run["id"], program="PLA")

    assert error["code"] == "not_allowed"
    assert run["program"] is None


@pytest.mark.usefixtures("programmed")
async def test_a_cost_statement_shows_the_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    await set_program(hass, "Cotton 60°")
    await washed(hass, clock, kwh=1.2)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], name="Towels")

    detailed = await export(panel, browser, run_ids=[run["id"]])
    compact = await export(panel, browser, run_ids=[run["id"]], detail="compact")

    assert (
        "Washer · Jan 15, 2026 · Program Cotton 60° · Running time 1 h 30 min"
        in detailed.lines
    )
    assert compact.lines[3:5] == [
        "Run Device Program Start Total",
        "Towels Washer Cotton 60° Jan 15, 2026 €0.60",
    ]
