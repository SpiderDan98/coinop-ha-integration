"""Runs placed in the Stores before setup, in the stored JSON shape."""

from datetime import datetime, timedelta
from typing import Any

from .clock import CLOCK_START


def line_item(kind: str, amount: float, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"{kind}-{amount}",
        "kind": kind,
        "label": None,
        "quantity": 1,
        "unit": "pcs",
        "unit_price": amount,
        "amount": amount,
        "method": None,
        "segments": [],
    } | fields


def electricity(
    kwh: float, price: float, start: datetime, end: datetime
) -> dict[str, Any]:
    segment = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "kwh": kwh,
        "unit_price": price,
    }
    return line_item(
        "electricity",
        kwh * price,
        id="electricity",
        quantity=kwh,
        unit="kWh",
        unit_price=price,
        method="estimated",
        segments=[segment],
    )


def stored_run(
    run_id: str,
    *,
    hours: float = 2,
    started: datetime = CLOCK_START - timedelta(days=1),
    ended: bool = True,
    **fields: Any,
) -> dict[str, Any]:
    end = started + timedelta(hours=hours)
    return {
        "id": run_id,
        "device_id": "device-kobra",
        "device_name": "Kobra",
        "name": f"Run {run_id}",
        "started": started.isoformat(),
        "ended": end.isoformat() if ended else None,
        "outcome": "completed" if ended else None,
        "finalised": ended,
        "pauses": [],
        "flags": [],
        "line_items": [electricity(0.24, 0.30, started, end)],
    } | fields


def place_runs(hass_storage: dict[str, Any], *runs: dict[str, Any]) -> None:
    """Ended Runs go to the runs Store, open ones to the live Store."""
    for key, finalised in (("wattbill.runs", True), ("wattbill.live", False)):
        hass_storage[key] = {
            "version": 1,
            "minor_version": 1,
            "key": key,
            "data": {"runs": [r for r in runs if r["finalised"] is finalised]},
        }
