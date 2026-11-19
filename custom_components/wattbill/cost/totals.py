"""Per-Device totals: summed from Runs at startup, then advanced by deltas."""

from dataclasses import dataclass, fields
from datetime import datetime

from custom_components.wattbill.cost.running_time import running_time
from custom_components.wattbill.models import LineItemKind, Run


@dataclass(frozen=True)
class Totals:
    """What a Run (or a sum of Runs) contributes to its Device's summed sensors."""

    cost: float = 0.0
    electricity_cost: float = 0.0
    material_cost: float = 0.0
    other_cost: float = 0.0
    material_grams: float = 0.0
    energy_kwh: float = 0.0
    runs: int = 0
    running_hours: float = 0.0
    flagged_runs: int = 0

    def __add__(self, other: Totals) -> Totals:
        return Totals(
            *(getattr(self, f.name) + getattr(other, f.name) for f in fields(self))
        )

    def __sub__(self, other: Totals) -> Totals:
        return Totals(
            *(getattr(self, f.name) - getattr(other, f.name) for f in fields(self))
        )


def _amount(run: Run, kind: LineItemKind) -> float:
    return sum(item.amount for item in run.line_items if item.kind is kind)


def run_totals(run: Run, now: datetime) -> Totals:
    """`now` is where the running time of an open Run ends."""
    return Totals(
        cost=sum(item.amount for item in run.line_items),
        electricity_cost=_amount(run, LineItemKind.ELECTRICITY),
        material_cost=_amount(run, LineItemKind.MATERIAL),
        other_cost=_amount(run, LineItemKind.OTHER),
        material_grams=sum(
            item.quantity or 0.0
            for item in run.line_items
            if item.kind is LineItemKind.MATERIAL
        ),
        energy_kwh=run.electricity.quantity or 0.0,
        runs=1,
        running_hours=running_time(run, now).total_seconds() / 3600,
        flagged_runs=1 if run.flags else 0,
    )


class DeviceTotals:
    """Keeps each Run's last contribution so a change moves the sum by its delta."""

    def __init__(self) -> None:
        self._by_run: dict[str, Totals] = {}
        self.sum = Totals()

    def apply(self, run: Run, now: datetime) -> None:
        contribution = run_totals(run, now)
        self.sum = self.sum - self._by_run.get(run.id, Totals()) + contribution
        self._by_run[run.id] = contribution

    def remove(self, run_id: str) -> None:
        self.sum = self.sum - self._by_run.pop(run_id, Totals())
