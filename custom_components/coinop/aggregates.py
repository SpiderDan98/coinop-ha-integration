"""Totals across Runs, grouped by any of kind, Device, month, Material, Outcome and Tag.

The facts are Line Items: cost, grams, kWh and litres sum the Line Items in a group;
Runs, running hours and Flagged Runs count each Run once in every group that
holds one of its Line Items. So a Run counts in each of its Tags and Materials,
and those groups overlap. A Run counts in the month it started in, in HA's time
zone; open Runs count at their provisional values.
"""

from collections.abc import Collection, Iterable, Mapping
from datetime import datetime, tzinfo
from itertools import product
from typing import Any

from custom_components.coinop.cost.rounding import rounded_sum
from custom_components.coinop.cost.running_time import running_time
from custom_components.coinop.models import LineItem, LineItemKind, Run

DIMENSIONS = ("kind", "device", "month", "material", "outcome", "tag")

type Fact = tuple[Run, LineItem]


def measures(facts: list[Fact], now: datetime, decimals: int) -> dict[str, Any]:
    """`now` is where the running time of an open Run ends."""
    runs = list({run.id: run for run, _ in facts}.values())
    items = [item for _, item in facts]

    def cost(kind: LineItemKind | None = None) -> float:
        amounts = (i.amount for i in items if kind is None or i.kind is kind)
        return float(rounded_sum(amounts, decimals))

    def quantity(kind: LineItemKind) -> float:
        return sum((i.quantity or 0.0 for i in items if i.kind is kind), 0.0)

    return {
        "cost": cost(),
        **{f"{kind}_cost": cost(kind) for kind in LineItemKind},
        "material_grams": sum((item.grams for item in items), 0.0),
        "energy_kwh": quantity(LineItemKind.ELECTRICITY),
        "water_litres": quantity(LineItemKind.WATER),
        "runs": len(runs),
        "running_hours": sum(
            (running_time(run, now).total_seconds() / 3600 for run in runs), 0.0
        ),
        "flagged_runs": sum(1 for run in runs if run.flags),
    }


def run_measures(runs: Iterable[Run], now: datetime, decimals: int) -> dict[str, Any]:
    return measures(
        [(run, item) for run in runs for item in run.line_items], now, decimals
    )


def _keys(
    dimension: str,
    run: Run,
    item: LineItem,
    zone: tzinfo,
    material_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """The groups a Line Item falls in along one dimension."""
    match dimension:
        case "kind":
            return [{"kind": item.kind}]
        case "device":
            return [{"device_id": run.device_id, "device_name": run.device_name}]
        case "month":
            return [{"month": run.started.astimezone(zone).strftime("%Y-%m")}]
        case "material":
            name = material_names.get(item.material_id or "") or (
                None if item.material is None else item.material.name
            )
            return [{"material_id": item.material_id, "material_name": name}]
        case "outcome":
            return [{"outcome": run.outcome}]
        case _:
            return [{"tag": tag} for tag in run.tags] or [{"tag": None}]


def aggregate(
    runs: Iterable[Run],
    group_by: list[str],
    now: datetime,
    decimals: int,
    zone: tzinfo,
    material_names: Mapping[str, str],
    material_ids: Collection[str | None] | None = None,
) -> list[dict[str, Any]]:
    """One group per combination of `group_by` values that has Line Items.

    `material_names` names the catalogue's Materials; a Material deleted since
    is named by the Line Item's copy of it. With `material_ids`, only Line Items
    of those Materials count. Groups come sorted by their values, none last.
    """
    facts: dict[tuple[tuple[str, Any], ...], list[Fact]] = {}
    for run in runs:
        for item in run.line_items:
            if material_ids is not None and item.material_id not in material_ids:
                continue
            for parts in product(
                *(
                    _keys(dimension, run, item, zone, material_names)
                    for dimension in group_by
                )
            ):
                key = tuple(pair for part in parts for pair in part.items())
                facts.setdefault(key, []).append((run, item))
    return [
        dict(key) | measures(facts[key], now, decimals)
        for key in sorted(
            facts, key=lambda key: [(value is None, str(value)) for _, value in key]
        )
    ]
