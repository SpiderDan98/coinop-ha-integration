"""The user corrects a Run in place: its fields, its Flags, ending and deleting it."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import CLOCK_START, Clock
from .devices import add_device, add_hub
from .stored import line_item, place_runs, stored_run
from .test_measured import add_metered_device, set_meter
from .test_run_event import record_events
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value
from .test_sensors import CURRENT, FLAGGED, LAST, print_runs, restart_with, state_of
from .websocket import PanelClient

ENERGY = "sensor.kobra_energy_in_runs"


async def test_name_note_and_part_count_are_saved_at_once(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(
        hass_storage,
        stored_run("plate", line_items=[line_item("electricity", 1.0)]),
    )
    await add_hub(hass)

    result = await panel.call(
        "coinop/runs/update",
        run_id="plate",
        name="Six hooks",
        note="Two broke off the plate",
        part_count=4,
    )

    run = result["run"]
    assert (run["name"], run["note"], run["part_count"]) == (
        "Six hooks",
        "Two broke off the plate",
        4,
    )
    assert run["cost_per_part"] == 0.25
    [stored] = stored_runs(hass_storage)
    assert (stored["name"], stored["note"], stored["part_count"]) == (
        "Six hooks",
        "Two broke off the plate",
        4,
    )
    [listed] = (await panel.call("coinop/runs/list"))["runs"]
    assert (listed["part_count"], listed["cost_per_part"]) == (4, 0.25)


async def test_an_emptied_name_or_note_is_none(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("plate", note="Brim"))
    await add_hub(hass)

    result = await panel.call("coinop/runs/update", run_id="plate", name="  ", note="")

    assert (result["run"]["name"], result["run"]["note"]) == (None, None)


async def printed_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hours: list[int]
) -> tuple[ConfigEntry, list[dict[str, Any]]]:
    """Runs of 100 W at 1 EUR/kWh, oldest first, as the gallery lists them."""
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await print_runs(hass, clock, hours)
    runs = (await panel.call("coinop/runs/list"))["runs"]
    return entry, sorted(runs, key=lambda run: run["started"])


async def test_times_and_outcome_change_no_cost_and_fire_nothing(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, watcher: PanelClient
) -> None:
    _, [run] = await printed_run(hass, clock, panel, [2])
    fired = record_events(hass)
    started = datetime.fromisoformat(run["started"])
    await watcher.subscribe("coinop/runs/subscribe")
    await watcher.event()

    result = await panel.call(
        "coinop/runs/update",
        run_id=run["id"],
        started=(started - timedelta(hours=1)).isoformat(),
        ended=(started + timedelta(hours=5)).isoformat(),
        outcome="failed",
    )

    corrected = result["run"]
    assert corrected["outcome"] == "failed"
    assert corrected["running_seconds"] == 6 * 3600
    assert corrected["total"] == run["total"] == 0.2
    assert value(hass, TOTAL_COST) == pytest.approx(0.2)
    assert value(hass, ENERGY) == pytest.approx(0.2)
    assert state_of(hass, LAST).attributes["outcome"] == "failed"
    assert (await watcher.event())["change"] == "updated"
    assert fired == []


async def test_times_and_outcome_wait_for_the_run_to_be_final(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    for field, change in [
        ("started", (clock.now() - timedelta(hours=1)).isoformat()),
        ("ended", clock.now().isoformat()),
        ("outcome", "completed"),
    ]:
        error = await panel.error(
            "coinop/runs/update", run_id=run["id"], **{field: change}
        )
        assert error["code"] == "not_allowed", field

    result = await panel.call(
        "coinop/runs/update", run_id=run["id"], name="Gear", part_count=2
    )
    assert (result["run"]["name"], result["run"]["ended"]) == ("Gear", None)


@pytest.mark.parametrize(
    "change",
    [
        {"part_count": 0},
        {"part_count": 1.5},
        {"ended": (CLOCK_START - timedelta(days=2)).isoformat()},
        {"started": "2026-01-14T10:00:00"},
        {"outcome": "lost"},
    ],
)
async def test_impossible_corrections_are_refused(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    change: dict[str, Any],
) -> None:
    place_runs(hass_storage, stored_run("plate"))
    await add_hub(hass)

    error = await panel.error("coinop/runs/update", run_id="plate", **change)

    assert error["code"] == "invalid_format"
    run = (await panel.call("coinop/runs/get", run_id="plate"))["run"]
    fields = ("started", "ended", "outcome", "part_count")
    assert {key: run[key] for key in fields} == {
        key: stored_run("plate")[key] for key in fields
    }


async def test_clearing_flags_lowers_the_flagged_runs_count(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry, _ = await printed_run(hass, clock, panel, [1, 1])

    def flag(runs: list[dict[str, Any]]) -> None:
        runs[0]["flags"] = ["price_gap", "fault"]
        runs[1]["flags"] = ["fault"]

    await restart_with(hass, entry, hass_storage, flag)
    assert value(hass, FLAGGED) == 2
    first, second = stored_runs(hass_storage)

    result = await panel.call(
        "coinop/runs/clear_flag", run_id=first["id"], flag="fault"
    )
    assert result["run"]["flags"] == ["price_gap"]
    assert value(hass, FLAGGED) == 2

    await panel.call("coinop/runs/clear_flag", run_id=first["id"], flag="price_gap")
    assert value(hass, FLAGGED) == 1
    assert stored_runs(hass_storage)[0]["flags"] == []
    [listed] = [
        run
        for run in (await panel.call("coinop/runs/list"))["runs"]
        if run["id"] == second["id"]
    ]
    assert listed["flags"] == ["fault"]


async def test_end_run_now_ends_the_open_run_as_unknown_once(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    fired = record_events(hass)
    await set_status(hass, "printing")
    await clock.advance(hours=3)
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    result = await panel.call("coinop/runs/end", run_id=run["id"])
    await hass.async_block_till_done()

    assert result["run"]["outcome"] == "unknown"
    assert result["run"]["ended"] == clock.now().isoformat()
    ended = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert ended["finalised"] is True
    assert ended["total"] == 0.3
    assert [event["event_type"] for event in fired] == ["started", "ended"]
    assert fired[-1]["outcome"] == "unknown"
    assert state_of(hass, CURRENT).state == STATE_UNKNOWN

    await panel.call("coinop/runs/update", run_id=run["id"], name="Stuck print")
    await panel.call("coinop/runs/update", run_id=run["id"], outcome="failed")
    await hass.async_block_till_done()
    assert len(fired) == 2
    error = await panel.error("coinop/runs/end", run_id=run["id"])
    assert error["code"] == "not_allowed"


async def test_end_run_now_answers_before_a_metered_run_is_final(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_meter(hass, 10.0)
    await add_metered_device(hass)
    fired = record_events(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, 10.3)
    await clock.advance(minutes=1)
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    result = await panel.call("coinop/runs/end", run_id=run["id"])

    assert (result["run"]["outcome"], result["run"]["finalised"]) == ("unknown", False)
    await clock.advance(minutes=5)
    ended = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert ended["finalised"] is True
    assert [event["event_type"] for event in fired] == ["started", "ended"]


async def test_deleting_a_run_says_and_lowers_what_the_totals_lose(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    watcher: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    _, [first, last] = await printed_run(hass, clock, panel, [1, 3])
    assert value(hass, TOTAL_COST) == pytest.approx(0.4)

    preview = await panel.call("coinop/runs/delete_preview", run_ids=[last["id"]])

    drop = preview["drop"]
    assert drop["cost"] == 0.3
    assert drop["electricity_cost"] == 0.3
    assert (drop["runs"], drop["flagged_runs"]) == (1, 1)
    assert drop["energy_kwh"] == pytest.approx(0.3)
    assert drop["running_hours"] == pytest.approx(3)
    assert value(hass, TOTAL_COST) == pytest.approx(0.4)

    await watcher.subscribe("coinop/runs/subscribe")
    await watcher.event()
    result = await panel.call("coinop/runs/delete", run_ids=[last["id"]])

    assert result == preview
    assert value(hass, TOTAL_COST) == pytest.approx(0.1)
    assert value(hass, RUNS) == 1
    assert float(state_of(hass, LAST).state) == pytest.approx(0.1)
    deleted = await watcher.event()
    assert (deleted["change"], deleted["run"]["id"]) == ("deleted", last["id"])
    assert [run["id"] for run in stored_runs(hass_storage)] == [first["id"]]
    error = await panel.error("coinop/runs/get", run_id=last["id"])
    assert error["code"] == "not_found"


async def test_deleting_several_runs_drops_their_sum(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    _, runs = await printed_run(hass, clock, panel, [1, 3])

    result = await panel.call("coinop/runs/delete", run_ids=[run["id"] for run in runs])

    assert (result["drop"]["cost"], result["drop"]["runs"]) == (0.4, 2)
    assert value(hass, TOTAL_COST) == 0
    assert state_of(hass, LAST).state == STATE_UNKNOWN


async def test_only_final_runs_that_exist_are_deleted(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    _, [done] = await printed_run(hass, clock, panel, [1])
    await set_status(hass, "printing")
    open_run = next(
        run
        for run in (await panel.call("coinop/runs/list"))["runs"]
        if run["ended"] is None
    )

    for command in ("coinop/runs/delete_preview", "coinop/runs/delete"):
        missing = await panel.error(command, run_ids=[done["id"], "nope"])
        still_open = await panel.error(command, run_ids=[done["id"], open_run["id"]])
        assert (missing["code"], still_open["code"]) == ("not_found", "not_allowed")

    assert value(hass, RUNS) == 2


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("coinop/runs/update", {"run_id": "plate", "name": "x"}),
        ("coinop/runs/clear_flag", {"run_id": "plate", "flag": "fault"}),
        ("coinop/runs/end", {"run_id": "plate"}),
        ("coinop/runs/delete_preview", {"run_ids": ["plate"]}),
        ("coinop/runs/delete", {"run_ids": ["plate"]}),
        *(
            (
                f"coinop/line_items/{verb}",
                {"run_id": "plate", "line_item_id": "electricity"},
            )
            for verb in ("update", "reset", "delete")
        ),
        ("coinop/line_items/add", {"run_id": "plate", "kind": "other"}),
    ],
)
async def test_only_admins_correct_runs(
    hass: HomeAssistant,
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    hass_storage: dict[str, Any],
    command: str,
    data: dict[str, Any],
) -> None:
    place_runs(hass_storage, stored_run("plate", flags=["fault"]))
    await add_hub(hass)
    user = connect_panel(hass_read_only_user)

    error = await user.error(command, **data)

    assert error["code"] == "unauthorized"
    assert stored_runs(hass_storage) == [stored_run("plate", flags=["fault"])]
