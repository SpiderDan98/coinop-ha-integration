"""Records what the panel receives, as canned responses for the panel's own tests."""

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from .clock import CLOCK_START, Clock
from .contract import assert_recorded, stable_ids
from .devices import STATUS, add_device, add_hub
from .stored import electricity, line_item, place_runs, stored_run
from .websocket import PanelClient

DAY = timedelta(days=1)


def image(image_id: str, kind: str, created: datetime) -> dict[str, Any]:
    return {"id": image_id, "kind": kind, "created": created.isoformat()}


def history() -> list[dict[str, Any]]:
    benchy_start = CLOCK_START - 3 * DAY
    helmet_start = CLOCK_START - 2 * DAY
    return [
        stored_run(
            "benchy",
            name="Benchy",
            started=benchy_start,
            hours=1.25,
            images=[
                image("benchy-thumbnail", "thumbnail", benchy_start),
                image("benchy-snapshot", "snapshot", benchy_start + DAY / 19.2),
            ],
            line_items=[
                electricity(0.15, 0.30, benchy_start, benchy_start + DAY / 19.2),
                line_item(
                    "material",
                    0.3125,
                    id="benchy-pla",
                    label="PLA Basic Black",
                    quantity=12.5,
                    unit="g",
                    unit_price=0.025,
                ),
                line_item("other", 0.5, id="benchy-wear", label="Nozzle wear"),
            ],
        ),
        stored_run(
            "helmet",
            name="Helmet",
            started=helmet_start,
            hours=9,
            outcome="failed",
            images=[image("helmet-snapshot", "snapshot", helmet_start + DAY * 9 / 24)],
            line_items=[
                electricity(0.6, 0.30, helmet_start, helmet_start + DAY / 4)
                | {
                    "quantity": 1.08,
                    "unit_price": 0.3 / 1.08,
                    "amount": 0.3,
                    "segments": [
                        {
                            "start": helmet_start.isoformat(),
                            "end": (helmet_start + DAY / 4).isoformat(),
                            "kwh": 0.6,
                            "unit_price": 0.3,
                        },
                        {
                            "start": (helmet_start + DAY / 4).isoformat(),
                            "end": (helmet_start + DAY * 9 / 24).isoformat(),
                            "kwh": 0.48,
                            "unit_price": 0.25,
                        },
                    ],
                },
            ],
        ),
        stored_run(
            "cancelled",
            name=None,
            device_id="device-mini",
            device_name="Mini",
            started=CLOCK_START - DAY,
            hours=0.5,
            outcome="cancelled",
        ),
    ]


async def test_record_the_runs_the_panel_shows(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    entry = await add_hub(hass)
    hass.states.async_set(STATUS, "idle")
    await panel.subscribe("wattbill/runs/subscribe")
    events = [await panel.event()]
    subentry = await add_device(hass, entry, running_power=120, price=0.30)
    hass.states.async_set(STATUS, "printing")
    await hass.async_block_till_done()
    events.append(await panel.event())
    await clock.advance(minutes=45)
    events.append(await panel.event())
    live_id = events[-1]["run"]["id"]
    ids = {live_id: "print-live", subentry.subentry_id: "device-kobra"}
    runs = [run["id"] for run in events[0]["runs"]] + [live_id]
    details = [await panel.call("wattbill/runs/get", run_id=run) for run in runs]
    [live_item] = details[-1]["run"]["line_items"]
    ids[live_item["id"]] = "print-live-electricity"
    hass.states.async_set(STATUS, "finished")
    await hass.async_block_till_done()
    events.append(await panel.event())

    assert [event.get("change") for event in events] == [
        None,
        "started",
        "updated",
        "ended",
    ]
    assert_recorded("runs-subscribe", stable_ids(events, ids))
    assert_recorded("runs-get", stable_ids(details, ids))
