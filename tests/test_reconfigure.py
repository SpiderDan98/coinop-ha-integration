"""Reconfigure: a menu of the Device's sections, saved at once and applied."""

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    MAPPING,
    STATUS,
    add_device,
    add_hub,
    configure,
    reconfigure,
    start_reconfigure,
)
from .test_device_flow import suggested
from .test_persistence import live_runs
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value


async def test_reconfigure_is_a_menu_of_the_devices_sections(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry)

    result = await start_reconfigure(hass, entry, subentry)

    assert result["step_id"] == "reconfigure"
    assert result["menu_options"] == [
        "status",
        "job",
        "consumption",
        "price",
        "save",
    ]


async def test_each_section_is_pre_filled_and_returns_to_the_menu(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(
        hass, entry, job="sensor.kobra_job", running_power=95, price=0.31
    )
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "status"})
    assert suggested(result, "entity_id") == STATUS
    result = await configure(hass, result, {"entity_id": STATUS})
    assert result["step_id"] == "mapping"
    assert suggested(result, "finished") == ["finished"]
    result = await configure(hass, result, MAPPING)
    assert result["step_id"] == "reconfigure"

    result = await configure(hass, result, {"next_step_id": "job"})
    assert suggested(result, "entity_id") == "sensor.kobra_job"
    result = await configure(hass, result, {"entity_id": "sensor.kobra_job"})
    assert result["step_id"] == "reconfigure"

    result = await configure(hass, result, {"next_step_id": "consumption"})
    assert result["type"] is FlowResultType.MENU
    result = await configure(hass, result, {"next_step_id": "estimate"})
    assert suggested(result, "running_power") == 95
    result = await configure(hass, result, {"running_power": 95})
    assert result["step_id"] == "reconfigure"

    result = await configure(hass, result, {"next_step_id": "price"})
    assert suggested(result, "price") == 0.31
    result = await configure(hass, result, {"price": 0.31})
    assert result["step_id"] == "reconfigure"


async def test_save_writes_every_section_at_once(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=100, price=0.30)

    result = await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "status"},
        {"entity_id": "sensor.other_status", "attribute": "job_state"},
        {"running": ["on"], "ended": ["off"]},
        {"next_step_id": "job"},
        {"entity_id": "sensor.kobra_job", "attribute": "file_name"},
        {"next_step_id": "consumption"},
        {"next_step_id": "estimate"},
        {"running_power": 90, "paused_power": 10},
        {"next_step_id": "price"},
        {"price": 0.5},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    data = entry.subentries[subentry.subentry_id].data
    assert data["status"] == {
        "entity_id": "sensor.other_status",
        "attribute": "job_state",
    }
    assert data["mapping"]["running"] == ["on"]
    assert data["mapping"]["finished"] == []
    assert data["job"] == {"entity_id": "sensor.kobra_job", "attribute": "file_name"}
    assert data["consumption"]["running_power"] == 90
    assert data["consumption"]["paused_power"] == 10
    assert data["price"]["value"] == 0.5


async def test_leaving_without_save_changes_nothing(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, price=0.30)
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "price"})
    await configure(hass, result, {"price": 0.5})

    assert entry.subentries[subentry.subentry_id].data["price"]["value"] == 0.30


async def test_an_open_run_survives_save_and_continues_at_the_new_price(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    [open_run] = live_runs(hass_storage)

    await reconfigure(hass, entry, subentry, {"next_step_id": "price"}, {"price": 2})
    await clock.advance(minutes=1)
    before = value(hass, TOTAL_COST)
    await clock.advance(hours=1)

    assert value(hass, TOTAL_COST) - before == pytest.approx(0.2)
    await set_status(hass, "finished")
    assert value(hass, RUNS) == 1
    [run] = stored_runs(hass_storage)
    assert run["id"] == open_run["id"]


async def test_a_new_average_power_applies_to_the_open_run(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "consumption"},
        {"next_step_id": "estimate"},
        {"running_power": 300},
    )
    await clock.advance(minutes=1)
    before = value(hass, TOTAL_COST)
    await clock.advance(hours=1)

    assert value(hass, TOTAL_COST) - before == pytest.approx(0.3)


async def test_a_new_mapping_applies_to_the_open_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)

    await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "status"},
        {"entity_id": STATUS},
        MAPPING | {"cancelled": ["cancelled", "stopped"]},
    )
    await set_status(hass, "stopped")

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "cancelled"


async def test_a_new_status_entity_applies_to_the_open_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)

    await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "status"},
        {"entity_id": "binary_sensor.kobra_printing"},
        {"running": ["on"], "finished": ["off"]},
    )
    hass.states.async_set("binary_sensor.kobra_printing", "off")
    await hass.async_block_till_done()

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert value(hass, RUNS) == 1


async def test_ended_runs_never_change(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    ended = deepcopy(stored_runs(hass_storage))

    await reconfigure(hass, entry, subentry, {"next_step_id": "price"}, {"price": 5})
    await clock.advance(hours=1)

    assert stored_runs(hass_storage) == ended
    assert value(hass, TOTAL_COST) == pytest.approx(0.1)


async def test_reconfigure_keeps_its_own_status_entity_but_refuses_another_devices(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    await add_device(hass, entry, name="Voron", status="sensor.voron_status")
    menu = await start_reconfigure(hass, entry, kobra)
    result = await configure(hass, menu, {"next_step_id": "status"})

    refused = await configure(hass, result, {"entity_id": "sensor.voron_status"})
    kept = await configure(hass, refused, {"entity_id": STATUS})

    assert refused["errors"] == {"entity_id": "status_already_used"}
    assert kept["step_id"] == "mapping"
