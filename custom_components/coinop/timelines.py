"""A Run's timeline of one quantity's readings and prices, its Flags and its consumption model."""

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .cost import consumption
from .models import Flag, Run, Timeline
from .quantities import Quantity


def meter_of(
    quantity: Quantity, section: Mapping[str, Any] | None
) -> Mapping[str, Any] | None:
    """The section's meter or rate input; None for a fallback without one."""
    if section is None or section["source"] not in (
        quantity.total_source,
        quantity.rate_source,
    ):
        return None
    return section


def add_flag(run: Run, flag: Flag) -> None:
    if flag not in run.flags:
        run.flags.append(flag)


def add_price(timeline: Timeline, at: datetime, price: float | None) -> None:
    prices = timeline.prices
    index = bisect_right(prices, at, key=lambda entry: entry[0])
    if index and prices[index - 1][0] == at:
        prices[index - 1] = (at, price)
    elif not index or prices[index - 1][1] != price:
        prices.insert(index, (at, price))


def add_reading(
    quantity: Quantity, run: Run, at: datetime, value: float | None
) -> None:
    """Add a reading (None while it had no value) and flag gaps and resets."""
    timeline = run.timelines[quantity.kind]
    readings = timeline.readings
    index = bisect_right(readings, at, key=lambda reading: reading[0])
    if index and readings[index - 1][0] == at:
        return
    if index == len(readings) >= 2 and readings[-1][1] == readings[-2][1] == value:
        readings[-1] = (at, value)
        return
    readings.insert(index, (at, value))
    if run.ended is not None and at > run.ended:
        # Only the stretch up to the end belongs to the Run.
        at = run.ended
    previous = next(
        (
            (time, reading)
            for time, reading in reversed(readings[:index])
            if reading is not None
        ),
        None,
    )
    if value is None:
        if run.ended is None or at < run.ended:
            add_flag(run, Flag.CONSUMPTION_GAP)
    elif (
        (meter := meter_of(quantity, timeline.source))
        and meter["source"] == quantity.total_source
        and previous is not None
        and value < previous[1]
        and (run.ended is None or previous[0] < run.ended)
    ):
        add_flag(run, Flag.METER_RESET)


def has_final_report(run: Run, timeline: Timeline) -> bool:
    return any(
        value is not None and run.ended is not None and at >= run.ended
        for at, value in timeline.readings
    )


def model(
    quantity: Quantity,
    timeline: Timeline,
    gap_rates: Sequence[tuple[datetime, float | None]],
    fallback: consumption.Model,
) -> consumption.Model:
    """The timeline's consumption model: its meter, its rate input (each gap at
    the rate given from its moment on, else the last one), else `fallback`."""
    meter = meter_of(quantity, timeline.source)
    if meter is None:
        return fallback
    if meter["source"] == quantity.total_source:
        return consumption.total(timeline.readings)
    return consumption.piecewise(
        [
            (since, consumption.rate(timeline.readings, gap, quantity.unit_seconds))
            for since, gap in gap_rates
        ]
    )
