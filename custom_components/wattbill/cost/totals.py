"""Per-Device totals: summed from Runs at startup, then advanced by deltas."""

from dataclasses import dataclass, fields

from custom_components.wattbill.models import Run


@dataclass(frozen=True)
class Totals:
    """What a Run (or a sum of Runs) contributes to its Device's total sensors."""

    cost: float = 0.0
    energy_kwh: float = 0.0
    runs: int = 0

    def __add__(self, other: Totals) -> Totals:
        return Totals(
            *(getattr(self, f.name) + getattr(other, f.name) for f in fields(self))
        )

    def __sub__(self, other: Totals) -> Totals:
        return Totals(
            *(getattr(self, f.name) - getattr(other, f.name) for f in fields(self))
        )


def run_totals(run: Run) -> Totals:
    return Totals(
        cost=sum(item.amount for item in run.line_items),
        energy_kwh=run.electricity.quantity or 0.0,
        runs=1,
    )


class DeviceTotals:
    """Keeps each Run's last contribution so a change moves the sum by its delta."""

    def __init__(self) -> None:
        self._by_run: dict[str, Totals] = {}
        self.sum = Totals()

    def apply(self, run: Run) -> None:
        contribution = run_totals(run)
        self.sum = self.sum - self._by_run.get(run.id, Totals()) + contribution
        self._by_run[run.id] = contribution

    def remove(self, run_id: str) -> None:
        self.sum = self.sum - self._by_run.pop(run_id, Totals())
