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
        "part_count": 1,
        "line_items": [electricity(0.24, 0.30, started, end)],
    } | fields


def stored_material(material_id: str, **fields: Any) -> dict[str, Any]:
    """A PLA filament at 0.02 per gram."""
    return {
        "id": material_id,
        "name": material_id.upper(),
        "form": "filament",
        "type": "PLA",
        "density": 1.24,
        "vendor": None,
        "colour": None,
        "diameter": 1.75,
        "default_for_type": False,
        "archived": False,
        "price": {
            "source": "fixed",
            "pack_price": 20.0,
            "pack_size": 1000.0,
            "pack_unit": "g",
        },
    } | fields


def _place_catalogue(
    hass_storage: dict[str, Any], name: str, entries: list[Any]
) -> None:
    catalog = hass_storage.setdefault(
        "wattbill.catalog",
        {
            "version": 1,
            "minor_version": 1,
            "key": "wattbill.catalog",
            "data": {"materials": [], "tags": [], "templates": []},
        },
    )
    catalog["data"][name] = entries


def place_materials(hass_storage: dict[str, Any], *materials: dict[str, Any]) -> None:
    _place_catalogue(hass_storage, "materials", list(materials))


def place_tags(hass_storage: dict[str, Any], *tags: str) -> None:
    _place_catalogue(hass_storage, "tags", sorted(tags))


def place_runs(hass_storage: dict[str, Any], *runs: dict[str, Any]) -> None:
    """Ended Runs go to the runs Store, open ones to the live Store."""
    for key, finalised in (("wattbill.runs", True), ("wattbill.live", False)):
        hass_storage[key] = {
            "version": 1,
            "minor_version": 1,
            "key": key,
            "data": {"runs": [r for r in runs if r["finalised"] is finalised]},
        }
