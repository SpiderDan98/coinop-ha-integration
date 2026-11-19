"""A Run's timelines of meter readings and prices, its Flags from them and its kWh."""

from bisect import bisect_right
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from .cost import consumption
from .device_config import ConsumptionSource
from .models import Flag, Run


def meter_of(section: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The section's Energy or Power meter; None for an estimate."""
    if section is None or section["source"] == ConsumptionSource.ESTIMATE:
        return None
    return section


def add_flag(run: Run, flag: Flag) -> None:
    if flag not in run.flags:
        run.flags.append(flag)


def add_price(run: Run, at: datetime, price: float | None) -> None:
    prices = run.prices
    index = bisect_right(prices, at, key=lambda entry: entry[0])
    if index and prices[index - 1][0] == at:
        prices[index - 1] = (at, price)
    elif not index or prices[index - 1][1] != price:
        prices.insert(index, (at, price))


def add_reading(run: Run, at: datetime, value: float | None) -> None:
    """Add a meter reading (None while it had no value) and flag gaps and resets."""
    readings = run.readings
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
        (meter := meter_of(run.consumption))
        and meter["source"] == ConsumptionSource.ENERGY
        and previous is not None
        and value < previous[1]
        and (run.ended is None or previous[0] < run.ended)
    ):
        add_flag(run, Flag.METER_RESET)


def has_final_report(run: Run) -> bool:
    return any(
        value is not None and run.ended is not None and at >= run.ended
        for at, value in run.readings
    )


def kwh(run: Run) -> Callable[[datetime, datetime], float]:
    """The Run's consumption model: its meter, else its average powers' estimate."""
    meter = meter_of(run.consumption)
    if meter and meter["source"] == ConsumptionSource.ENERGY:
        return consumption.energy(run.readings)
    return consumption.piecewise(
        [
            (
                since,
                consumption.power(run.readings, running)
                if meter
                else consumption.estimate(
                    running or 0.0,
                    running or 0.0 if paused is None else paused,
                    run.pauses,
                ),
            )
            for since, running, paused in run.average_powers
        ]
    )
