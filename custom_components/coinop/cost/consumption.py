"""Consumption models of any quantity: each answers "how much between two moments?"."""

from bisect import bisect_right
from collections.abc import Callable, Sequence
from datetime import datetime

type Model = Callable[[datetime, datetime], float]
type Readings = Sequence[tuple[datetime, float | None]]

# As in Home Assistant's total_increasing: a smaller drop is a dip, not a reset.
RESET_BELOW = 0.9


def counted(previous: float, reading: float) -> float:
    """What a meter counted between two readings, never negative.

    After a reset it counts from 0 again; what came between the last reading
    and the reset is lost.
    """
    if reading >= previous:
        return reading - previous
    return reading if reading < previous * RESET_BELOW else 0.0


def total(readings: Readings) -> Model:
    """Meter readings interpolated linearly between reports, also across gaps."""
    times: list[datetime] = []
    totals: list[float] = []
    previous: float | None = None
    for at, reading in readings:
        if reading is None:
            continue
        times.append(at)
        totals.append(
            0.0 if previous is None else totals[-1] + counted(previous, reading)
        )
        previous = reading

    def counted_at(moment: datetime) -> float:
        after = bisect_right(times, moment)
        if after == 0:
            return totals[0] if totals else 0.0
        if after == len(times):
            return totals[-1]
        share = (moment - times[after - 1]) / (times[after] - times[after - 1])
        return totals[after - 1] + share * (totals[after] - totals[after - 1])

    return lambda start, end: counted_at(end) - counted_at(start)


def rate(readings: Readings, gap_rate: float | None, unit_seconds: float) -> Model:
    """Left rule: each reading holds until the next one.

    A gap holds `gap_rate` if given, otherwise the last value (before the first
    value: the first one). A rate of 1 held for `unit_seconds` counts one unit.
    """
    last = next((value for _, value in readings if value is not None), 0.0)
    leading = last if gap_rate is None else gap_rate
    steps: list[tuple[datetime, float]] = []
    for at, value in readings:
        if value is not None:
            last = value
        if value is None:
            value = last if gap_rate is None else gap_rate
        steps.append((at, value))

    def amount(start: datetime, end: datetime) -> float:
        held = 0.0
        value, since = leading, start
        for at, step in steps:
            if at >= end:
                break
            if at > start:
                held += value * (at - since).total_seconds()
                since = at
            value = step
        held += value * (end - since).total_seconds()
        return held / unit_seconds

    return amount


def piecewise(models: Sequence[tuple[datetime, Model]]) -> Model:
    """Each model from its moment until the next one's; the first also before it."""

    def amount(start: datetime, end: datetime) -> float:
        result = 0.0
        for i, (since, model) in enumerate(models):
            low = start if i == 0 else max(start, since)
            high = end if i + 1 == len(models) else min(end, models[i + 1][0])
            if low < high:
                result += model(low, high)
        return result

    return amount
