"""The panel reads Runs over websocket: a list, live changes, and one Run in full."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import CLOCK_START, Clock
from .devices import STATUS, add_device, add_hub
from .stored import line_item, place_runs, stored_run
from .websocket import PanelClient


async def set_status(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(STATUS, status)
    await hass.async_block_till_done()


async def test_the_list_shows_what_a_gallery_tile_needs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await set_status(hass, "idle")
    subentry = await add_device(hass, entry, running_power=120, price=0.30)
    await set_status(hass, "printing")
    await clock.advance(hours=2)
    await set_status(hass, "finished")

    result = await panel.call("wattbill/runs/list")

    [run] = result["runs"]
    assert run == {
        "id": run["id"],
        "device_id": subentry.subentry_id,
        "device_name": "Kobra",
        "name": None,
        "started": CLOCK_START.isoformat(),
        "ended": (CLOCK_START.replace(hour=12)).isoformat(),
        "outcome": "completed",
        "finalised": True,
        "running_seconds": 7200,
        "total": 0.07,
        "part_count": 1,
        "cost_per_part": 0.07,
        "flags": [],
        "tags": [],
    }


async def test_a_run_reads_like_a_receipt_of_rounded_amounts(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(
        hass_storage,
        stored_run(
            "helmet",
            line_items=[
                line_item("electricity", 0.0725, method="estimated"),
                line_item("material", 0.125, id="pla-1", label="PLA"),
                line_item("material", 0.125, id="pla-2", label="PETG"),
                line_item("other", 1.006, id="wear", label="Nozzle wear"),
            ],
        ),
    )
    await add_hub(hass)

    result = await panel.call("wattbill/runs/get", run_id="helmet")

    run = result["run"]
    assert [item["amount"] for item in run["line_items"]] == [0.07, 0.13, 0.13, 1.01]
    assert run["subtotals"] == {"electricity": 0.07, "material": 0.26, "other": 1.01}
    assert run["total"] == 1.34
    [listed] = (await panel.call("wattbill/runs/list"))["runs"]
    assert listed["total"] == 1.34


async def test_amounts_round_to_the_currency_decimals(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await hass.config.async_update(currency="JPY")
    place_runs(
        hass_storage, stored_run("vase", line_items=[line_item("electricity", 12.5)])
    )
    await add_hub(hass)

    run = (await panel.call("wattbill/runs/get", run_id="vase"))["run"]

    assert run["line_items"][0]["amount"] == 13
    assert run["total"] == 13


async def test_an_unknown_run_is_not_found(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    error = await panel.error("wattbill/runs/get", run_id="nope")

    assert error["code"] == "not_found"


async def test_an_open_run_shows_its_evidence_and_running_time_so_far(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await set_status(hass, "idle")
    await add_device(hass, entry, running_power=125, price=0.25)
    await set_status(hass, "printing")
    await clock.advance(hours=4)
    [summary] = (await panel.call("wattbill/runs/list"))["runs"]

    run = (await panel.call("wattbill/runs/get", run_id=summary["id"]))["run"]

    assert run["ended"] is None
    assert run["running_seconds"] == 4 * 3600
    [item] = run["line_items"]
    assert item["method"] == "estimated"
    assert item["quantity"] == pytest.approx(0.5)
    assert item["unit"] == "kWh"
    assert item["unit_price"] == 0.25
    assert item["amount"] == 0.13
    assert [s["unit_price"] for s in item["segments"]] == [0.25]


async def test_subscribers_see_runs_start_progress_and_end(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await set_status(hass, "idle")
    await panel.subscribe("wattbill/runs/subscribe")
    assert await panel.event() == {"runs": []}

    await add_device(hass, entry, running_power=120, price=0.30)
    await set_status(hass, "printing")
    started = await panel.event()
    await clock.advance(minutes=30)
    updated = await panel.event()
    await clock.advance(minutes=30)
    await panel.event()
    await set_status(hass, "finished")
    ended = await panel.event()

    assert [started["change"], updated["change"], ended["change"]] == [
        "started",
        "updated",
        "ended",
    ]
    assert started["run"]["id"] == updated["run"]["id"] == ended["run"]["id"]
    assert updated["run"]["running_seconds"] == 30 * 60
    assert updated["run"]["total"] == 0.02
    assert ended["run"]["outcome"] == "completed"
    assert ended["run"]["total"] == 0.04


async def test_a_new_subscriber_first_gets_every_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("a"), stored_run("b"))
    await add_hub(hass)

    await panel.subscribe("wattbill/runs/subscribe")

    assert {run["id"] for run in (await panel.event())["runs"]} == {"a", "b"}


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("wattbill/runs/list", {}),
        ("wattbill/runs/subscribe", {}),
        ("wattbill/runs/get", {"run_id": "a"}),
    ],
)
async def test_only_admins_read_runs(
    hass: HomeAssistant,
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    command: str,
    data: dict[str, Any],
) -> None:
    await add_hub(hass)
    user = connect_panel(hass_read_only_user)

    error = await user.error(command, **data)

    assert error["code"] == "unauthorized"


async def test_commands_wait_for_wattbill_to_be_loaded(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)

    error = await panel.error("wattbill/runs/list")

    assert error["code"] == "not_loaded"
