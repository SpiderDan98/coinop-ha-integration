"""Consumption models: each answers "how many kWh between two moments?"."""

from bisect import bisect_right
from collections.abc import Callable, Sequence
from datetime import datetime

from custom_components.wattbill.models import Pause


def _overlap(start: datetime, end: datetime, pause: Pause) -> float:
    pause_end = end if pause.end is None else min(pause.end, end)
    return max(0.0, (pause_end - max(pause.start, start)).total_seconds())


def estimate(
    running_watts: float, paused_watts: float, pauses: Sequence[Pause]
) -> Callable[[datetime, datetime], float]:
    """Average running power while running, paused power within pauses."""

    def kwh(start: datetime, end: datetime) -> float:
        paused = sum(_overlap(start, end, pause) for pause in pauses)
        running = (end - start).total_seconds() - paused
        return (running_watts * running + paused_watts * paused) / 3_600_000

    return kwh


# As in Home Assistant's total_increasing: a smaller drop is a dip, not a reset.
RESET_BELOW = 0.9


def counted(previous: float, reading: float) -> float:
    """Energy a meter counted between two readings, never negative.

    After a reset it counts from 0 again; energy between the last reading and
    the reset is lost.
    """
    if reading >= previous:
        return reading - previous
    return reading if reading < previous * RESET_BELOW else 0.0


def energy(
    readings: Sequence[tuple[datetime, float | None]],
) -> Callable[[datetime, datetime], float]:
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

    def total(moment: datetime) -> float:
        after = bisect_right(times, moment)
        if after == 0:
            return totals[0] if totals else 0.0
        if after == len(times):
            return totals[-1]
        share = (moment - times[after - 1]) / (times[after] - times[after - 1])
        return totals[after - 1] + share * (totals[after] - totals[after - 1])

    return lambda start, end: total(end) - total(start)
