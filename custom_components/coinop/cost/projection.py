"""Projected Total: an open Run's cost so far plus the rest still to come.

Each rest is what one part adds from now to the expected end, priced at its Cost
Source's current unit price. Nothing here is stored (ADR 0002).
"""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal

from custom_components.coinop.models import (
    ExpectedEnergyForm,
    LineItem,
    ProjectedPart,
    Projection,
    QuantityBasis,
    Run,
    Usage,
    UsageUnit,
)

from .consumption import Model
from .material import length_of_grams
from .rounding import rounded_sum

type Span = tuple[datetime, datetime]

# The running time a metered Run's base power is averaged over, so its start's
# preheating soon stops counting.
RECENT = timedelta(minutes=30)
# The running time with and without drying a Run needs before its drying power is
# learned from it.
LEARNING = timedelta(minutes=10)
# Below it, a progress reading would multiply the running time so far too much.
MIN_PROGRESS = 5.0


def running_spans(run: Run, until: datetime) -> list[Span]:
    """The Run's running intervals up to `until`, pauses left out, in order."""
    pauses = [(pause.start, pause.end or until) for pause in run.pauses]
    return _without([(run.started, until)], pauses) if run.started < until else []


def progress_time_left(run: Run, until: datetime, percent: float) -> timedelta | None:
    """The time left if the rest takes as long per percent as the running time so
    far did; None below `MIN_PROGRESS`."""
    if percent < MIN_PROGRESS:
        return None
    ran = sum((end - start for start, end in running_spans(run, until)), timedelta())
    return ran * (100 - percent) / percent


def _without(
    spans: Iterable[Span],
    holes: Iterable[Span],
) -> list[Span]:
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
    spans: Iterable[Span],
    window: Iterable[Span],
) -> list[Span]:
    """The parts of the `spans` inside the `window`."""
    window = list(window)
    return [
        (max(start, window_start), min(end, window_end))
        for start, end in spans
        for window_start, window_end in window
        if max(start, window_start) < min(end, window_end)
    ]


def _seconds(spans: Iterable[Span]) -> float:
    return sum((end - start).total_seconds() for start, end in spans)


def _latest(
    spans: list[Span],
) -> list[Span]:
    """The last `RECENT` of the ordered `spans`, or all of them if they are shorter."""
    left, latest = RECENT, []
    for start, end in reversed(spans):
        if left <= timedelta():
            break
        start = max(start, end - left)
        latest.append((start, end))
        left -= end - start
    return latest


def _watts(spans: list[Span], measured: Model) -> float:
    return sum(measured(s, e) for s, e in spans) * 3_600_000 / _seconds(spans)


def recent_power(
    run: Run,
    until: datetime,
    measured: Model,
    drying: Iterable[list[Span]] = (),
    drying_power: float | None = None,
    unknown: Iterable[Span] = (),
) -> float | None:
    """The average W the `measured` kWh make over the Run's most recent half hour of
    running time outside the drying units' `drying` spans and the `unknown` ones, or
    all of it if it ran less; None before it ran at all.

    A Run that dried all along gives its recent power less the units' `drying_power`.
    """
    drying = list(drying)
    running = running_spans(run, until)
    observed = _without(running, unknown)
    if clear := _without(observed, (span for unit in drying for span in unit)):
        return _watts(_latest(clear), measured)
    # Until anything was seen, the recent power is all there is to go by.
    if not (recent := _latest(observed) or _latest(running)):
        return None
    dried = sum(_seconds(_within(unit, recent)) for unit in drying)
    return _watts(recent, measured) - (drying_power or 0.0) * dried / _seconds(recent)


def learned_drying_power(
    run: Run,
    until: datetime,
    measured: Model,
    drying: Iterable[list[Span]],
    unknown: Iterable[Span] = (),
) -> float | None:
    """The extra W a unit drew while drying in this Run: the average power while any
    dried less the average while none did, per drying unit, leaving out the `unknown`
    spans; None until each side ran for `LEARNING`."""
    drying = list(drying)
    running = _without(running_spans(run, until), unknown)
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


def total_rest(total: float, so_far: float) -> float:
    """What the amount `so_far` leaves of the Run's `total`, at least 0."""
    return max(total - so_far, 0.0)


def expected_energy_rest(
    expected: float, so_far: float, form: ExpectedEnergyForm
) -> float:
    """The kWh still to come from the Expected energy in its `form`: itself, or as
    the Run's total what the `so_far` kWh leave of it."""
    if form is ExpectedEnergyForm.TOTAL:
        return total_rest(expected, so_far)
    return expected


def material_rest(
    measured: Usage | None,
    planned: Usage | None,
    percent: float | None,
    items: list[LineItem],
    now: datetime,
) -> Usage | None:
    """The Material still to come at `now` in mm or g: what the plan leaves of the
    `measured` total, else as much per percent as so far once past `MIN_PROGRESS`;
    None while neither tells. The measured Line Items' Materials convert between
    the two."""
    if planned is not None:
        so_far = _measured_in(measured, planned.unit, items)
        if so_far is None:
            return None
        return Usage(now, total_rest(planned.value, so_far), planned.unit)
    if measured is None or percent is None or percent < MIN_PROGRESS:
        return None
    return Usage(now, measured.value * (100 - percent) / percent, measured.unit)


def _measured_in(
    measured: Usage | None, unit: UsageUnit, items: list[LineItem]
) -> float | None:
    """The `measured` total in `unit`; None where a Material can't convert it."""
    if measured is None:
        return 0.0
    if measured.unit is unit:
        return measured.value
    total = 0.0
    for item in items:
        value = item.quantity
        if value is not None and unit is UsageUnit.MILLIMETRE:
            value = length_of_grams(value, item.material) if item.material else None
        if value is None:
            return None
        total += value
    return total


def running_hours_rest(run: Run, hours_left: float) -> float | None:
    """What the running-hours Line Items add over the time left; None without one."""
    items = [i for i in run.line_items if i.basis is QuantityBasis.RUNNING_HOURS]
    if not items:
        return None
    return sum(item.unit_price * hours_left for item in items)


def project(
    rests: Mapping[ProjectedPart, float | None],
    ends_at: datetime | None,
    pending: Iterable[ProjectedPart] = (),
) -> Projection | None:
    """The rests that could be projected; None when none could, a rest of 0 counts."""
    projected = {part: rest for part, rest in rests.items() if rest is not None}
    return Projection(projected, ends_at, frozenset(pending)) if projected else None


def projected_total(run: Run, decimals: int) -> Decimal | None:
    """The cost so far plus the rests, rounded like the Line Items and never below
    the cost so far; None without a projection."""
    if run.projection is None:
        return None
    so_far = rounded_sum((item.amount for item in run.line_items), decimals)
    rest = rounded_sum(run.projection.rests.values(), decimals)
    return so_far + max(rest, Decimal(0))
