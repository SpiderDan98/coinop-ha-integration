"""Projected Total: an open Run's cost so far plus the rest still to come.

Each rest is what one part adds from now to the expected end, priced at its Cost
Source's current unit price. Nothing here is stored (ADR 0002).
"""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal

from custom_components.coinop.models import (
    ProjectedPart,
    Projection,
    QuantityBasis,
    Run,
)

from .consumption import Model
from .rounding import rounded_sum

# The running time a metered Run's base power is averaged over, so its start's
# preheating soon stops counting.
RECENT = timedelta(minutes=30)


def running_spans(run: Run, until: datetime) -> list[tuple[datetime, datetime]]:
    """The Run's running intervals up to `until`, pauses left out, in order."""
    spans = []
    start = run.started
    for pause in run.pauses:
        if pause.start >= until:
            break
        if pause.start > start:
            spans.append((start, pause.start))
        start = max(start, pause.end or until)
    if start < until:
        spans.append((start, until))
    return spans


def recent_power(run: Run, until: datetime, measured: Model) -> float | None:
    """The average W the `measured` kWh make over the Run's most recent half hour of
    running time, or all of it if it ran less; None before it ran at all."""
    left, seconds, kwh = RECENT, 0.0, 0.0
    for start, end in reversed(running_spans(run, until)):
        start = max(start, end - left)
        seconds += (end - start).total_seconds()
        kwh += measured(start, end)
        left -= end - start
        if left <= timedelta():
            break
    return kwh * 3_600_000 / seconds if seconds else None


def expected_energy_rest(expected: float, so_far: float, total: bool) -> float:
    """The kWh still to come from the Expected energy: itself, or as the Run's
    `total` what the `so_far` kWh leave of it, at least 0."""
    return max(expected - so_far, 0.0) if total else expected


def running_hours_rest(run: Run, hours_left: float) -> float | None:
    """What the running-hours Line Items add over the time left; None without one."""
    items = [i for i in run.line_items if i.basis is QuantityBasis.RUNNING_HOURS]
    if not items:
        return None
    return sum(item.unit_price * hours_left for item in items)


def project(
    rests: Mapping[ProjectedPart, float | None], ends: datetime | None
) -> Projection | None:
    """The rests that could be projected; None when none could, a rest of 0 counts."""
    projected = {part: rest for part, rest in rests.items() if rest is not None}
    return Projection(projected, ends) if projected else None


def projected_total(run: Run, decimals: int) -> Decimal | None:
    """The cost so far plus the rests, rounded like the Line Items and never below
    the cost so far; None without a projection."""
    if run.projection is None:
        return None
    so_far = rounded_sum((item.amount for item in run.line_items), decimals)
    rest = rounded_sum(run.projection.rests.values(), decimals)
    return so_far + max(rest, Decimal(0))
