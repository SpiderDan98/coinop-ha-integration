"""Projected Total: an open Run's cost so far plus the rest still to come.

Each rest is what one part adds from now to the expected end, priced at its Cost
Source's current unit price. Nothing here is stored (ADR 0002).
"""

from collections.abc import Iterable, Mapping
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
# The running time with and without drying a Run needs before its drying power is
# learned from it.
LEARNING = timedelta(minutes=10)


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


def _without(
    spans: Iterable[tuple[datetime, datetime]],
    holes: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """The parts of the ordered `spans` outside every one of the `holes`."""
    holes = sorted(holes)
    kept = []
    for start, end in spans:
        for hole_start, hole_end in holes:
            if hole_end <= start or hole_start >= end:
                continue
            if hole_start > start:
                kept.append((start, hole_start))
            start = max(start, hole_end)
        if start < end:
            kept.append((start, end))
    return kept


def _within(
    spans: Iterable[tuple[datetime, datetime]],
    window: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """The parts of the `spans` inside the `window`."""
    window = list(window)
    return [
        (max(start, window_start), min(end, window_end))
        for start, end in spans
        for window_start, window_end in window
        if max(start, window_start) < min(end, window_end)
    ]


def _seconds(spans: Iterable[tuple[datetime, datetime]]) -> float:
    return sum((end - start).total_seconds() for start, end in spans)


def _latest(
    spans: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """The last `RECENT` of the ordered `spans`, or all of them if they are shorter."""
    left, latest = RECENT, []
    for start, end in reversed(spans):
        if left <= timedelta():
            break
        start = max(start, end - left)
        latest.append((start, end))
        left -= end - start
    return latest


def _watts(spans: list[tuple[datetime, datetime]], measured: Model) -> float:
    return sum(measured(s, e) for s, e in spans) * 3_600_000 / _seconds(spans)


def recent_power(
    run: Run,
    until: datetime,
    measured: Model,
    drying: Iterable[list[tuple[datetime, datetime]]] = (),
    drying_power: float | None = None,
) -> float | None:
    """The average W the `measured` kWh make over the Run's most recent half hour of
    running time outside the drying units' `drying` spans, or all of it if it ran
    less; None before it ran at all.

    A Run that dried all along gives its recent power less the units' `drying_power`.
    """
    drying = list(drying)
    running = running_spans(run, until)
    if clear := _without(running, (span for unit in drying for span in unit)):
        return _watts(_latest(clear), measured)
    if not (recent := _latest(running)):
        return None
    dried = sum(_seconds(_within(unit, recent)) for unit in drying)
    return _watts(recent, measured) - (drying_power or 0.0) * dried / _seconds(recent)


def learned_drying_power(
    run: Run,
    until: datetime,
    measured: Model,
    drying: Iterable[list[tuple[datetime, datetime]]],
) -> float | None:
    """The extra W a unit drew while drying in this Run: the average power while any
    dried less the average while none did, per drying unit; None until each side ran
    for `LEARNING`."""
    drying = list(drying)
    running = running_spans(run, until)
    clear = _without(running, (span for unit in drying for span in unit))
    dried = _without(running, clear)
    if min(_seconds(clear), _seconds(dried)) < LEARNING.total_seconds():
        return None
    units = sum(_seconds(_within(unit, running)) for unit in drying)
    extra = (_watts(dried, measured) - _watts(clear, measured)) * _seconds(dried)
    return max(extra / units, 0.0)


def drying_hours(left: timedelta, drying_left: Iterable[timedelta | None]) -> float:
    """The hours the drying units dry within the time `left`, added up: each for its
    drying left, or for all of the time left without one."""
    return sum(
        (left if unit is None else min(unit, left)).total_seconds() / 3600
        for unit in drying_left
    )


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
    rests: Mapping[ProjectedPart, float | None],
    ends: datetime | None,
    pending: Iterable[ProjectedPart] = (),
) -> Projection | None:
    """The rests that could be projected; None when none could, a rest of 0 counts."""
    projected = {part: rest for part, rest in rests.items() if rest is not None}
    return Projection(projected, ends, frozenset(pending)) if projected else None


def projected_total(run: Run, decimals: int) -> Decimal | None:
    """The cost so far plus the rests, rounded like the Line Items and never below
    the cost so far; None without a projection."""
    if run.projection is None:
        return None
    so_far = rounded_sum((item.amount for item in run.line_items), decimals)
    rest = rounded_sum(run.projection.rests.values(), decimals)
    return so_far + max(rest, Decimal(0))
