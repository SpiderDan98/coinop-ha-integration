"""Manual Runs: prints recorded by hand, e.g. made while Home Assistant was down."""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import CLOCK_START, Clock
from .devices import add_device, add_hub
from .images import CAMERA, add_camera, picture
from .test_measured import add_metered_device, electricity, set_meter
from .test_run_event import record_events
from .test_runs import RUNS, TOTAL_COST, stored_runs, value
from .test_sensors import LAST, print_runs, state_of
from .test_templates import (
    INSERTS,
    WEAR,
    create as create_template,
    other_items,
    set_automatic,
)
from .websocket import PanelClient

ENERGY = "sensor.kobra_energy_in_runs"


def at(hours: float) -> str:
    return (CLOCK_START + timedelta(hours=hours)).isoformat()


async def create(panel: PanelClient, device_id: str, **fields: Any) -> dict[str, Any]:
    """A manual Run from 10:00 to 12:00 unless `fields` say otherwise."""
    result = await panel.call(
        "wattbill/runs/create",
        **{
            "device_id": device_id,
            "name": "Bracket",
            "started": at(0),
            "ended": at(2),
            "outcome": "completed",
        }
        | fields,
    )
    run: dict[str, Any] = result["run"]
    return run


async def test_a_manual_run_is_recorded_with_its_device_name_times_and_outcome(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry)
    await clock.advance(hours=5)

    run = await create(panel, device.subentry_id, outcome="failed")

    assert (
        run["device_id"],
        run["name"],
        run["started"],
        run["ended"],
        run["outcome"],
        run["finalised"],
    ) == (device.subentry_id, "Bracket", at(0), at(2), "failed", True)
    [stored] = stored_runs(hass_storage)
    assert (stored["id"], stored["name"], stored["outcome"]) == (
        run["id"],
        "Bracket",
        "failed",
    )


async def test_without_a_meter_a_manual_run_is_estimated_from_average_power(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry, running_power=100, price=0.30)
    await clock.advance(hours=5)

    run = await create(panel, device.subentry_id)

    item = electricity(run)
    assert item["method"] == "estimated"
    assert item["quantity"] == pytest.approx(0.2)
    assert item["amount"] == pytest.approx(0.06)


async def test_a_manual_run_ends_after_it_starts_and_before_now(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry)
    await clock.advance(hours=5)

    for started, ended in ((at(2), at(2)), (at(3), at(1)), (at(4), at(6))):
        error = await panel.error(
            "wattbill/runs/create",
            device_id=device.subentry_id,
            started=started,
            ended=ended,
            outcome="completed",
        )
        assert error["code"] == "invalid_format"
    error = await panel.error(
        "wattbill/runs/create",
        device_id="gone",
        started=at(0),
        ended=at(1),
        outcome="completed",
    )
    assert error["code"] == "not_found"
    assert (await panel.call("wattbill/runs/list"))["runs"] == []


async def test_without_history_or_average_power_the_user_enters_the_electricity(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    [device] = entry.subentries.values()
    await clock.advance(hours=5)

    run = await create(panel, device.subentry_id)

    item = electricity(run)
    assert (item["method"], item["quantity"], item["amount"]) == ("entered", None, 0)
    assert item["unit_price"] == pytest.approx(0.30)
    entered = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=item["id"],
        quantity=0.5,
    )
    item = electricity(entered["run"])
    assert (item["method"], item["quantity"], item["computed"]) == (
        "entered",
        0.5,
        None,
    )
    assert item["amount"] == pytest.approx(0.15)
    error = await panel.error(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=item["id"],
        unit="Wh",
    )
    assert error["code"] == "not_allowed"


async def test_totals_count_a_manual_run_at_creation(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry, running_power=100, price=1)
    await clock.advance(hours=5)

    await create(panel, device.subentry_id)

    assert value(hass, RUNS) == 1
    assert value(hass, TOTAL_COST) == pytest.approx(0.2)
    assert value(hass, ENERGY) == pytest.approx(0.2)


async def test_last_run_cost_takes_a_manual_run_only_if_it_ended_after_the_last_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry, running_power=100, price=1)
    await clock.advance(hours=4)
    await print_runs(hass, clock, [1])  # 14:00 to 15:00
    await clock.advance(hours=2)

    await create(panel, device.subentry_id, name="Older")
    assert float(state_of(hass, LAST).state) == pytest.approx(0.1)

    await create(panel, device.subentry_id, name="Newer", started=at(5), ended=at(7))
    last = state_of(hass, LAST)
    assert last.attributes["name"] == "Newer"
    assert float(last.state) == pytest.approx(0.2)


async def test_a_manual_run_fires_no_event_and_takes_no_snapshot(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    camera = await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    device = await add_device(hass, entry, camera=CAMERA, snapshot=True)
    fired = record_events(hass)
    await clock.advance(hours=5)

    run = await create(panel, device.subentry_id)
    await clock.advance(minutes=5)

    assert fired == []
    assert camera.requests == 0
    assert run["images"] == []


async def test_automatic_templates_are_computed_once_from_the_entered_times(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry)
    wear = await create_template(panel, **WEAR)
    inserts = await create_template(panel, **INSERTS)
    await set_automatic(panel, device, wear, inserts)
    await clock.advance(hours=5)

    await create(panel, device.subentry_id)
    await clock.advance(hours=1)

    assert other_items(hass_storage) == [
        [("Wear Kobra", 2, 0.3), ("Threaded inserts", 8, 0.64)]
    ]


async def test_tags_for_new_runs_apply_unless_the_dialog_sends_its_own(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry)
    await panel.call(
        "wattbill/devices/update_settings",
        device_id=device.subentry_id,
        settings={"tags_for_new_runs": ["Batch 7"]},
    )
    await clock.advance(hours=5)

    default = await create(panel, device.subentry_id)
    own = await create(panel, device.subentry_id, tags=["gift ", "Spare parts"])

    assert default["tags"] == ["Batch 7"]
    assert own["tags"] == ["gift", "Spare parts"]


async def test_only_admins_create_manual_runs(
    hass: HomeAssistant,
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
) -> None:
    entry = await add_hub(hass)
    device = await add_device(hass, entry)
    await clock.advance(hours=5)

    error = await connect_panel(hass_read_only_user).error(
        "wattbill/runs/create",
        device_id=device.subentry_id,
        started=at(0),
        ended=at(2),
        outcome="completed",
    )

    assert error["code"] == "unauthorized"
    assert value(hass, RUNS) == 0
