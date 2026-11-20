"""Electricity's own fallback without measurement: the Device's average powers."""

from collections.abc import Sequence
from datetime import datetime

from custom_components.coinop.models import Pause

from .consumption import Model


def _overlap(start: datetime, end: datetime, pause: Pause) -> float:
    pause_end = end if pause.end is None else min(pause.end, end)
    return max(0.0, (pause_end - max(pause.start, start)).total_seconds())


def estimate(
    running_watts: float, paused_watts: float, pauses: Sequence[Pause]
) -> Model:
    """Average running power while running, paused power within pauses, in kWh."""

    def kwh(start: datetime, end: datetime) -> float:
        paused = sum(_overlap(start, end, pause) for pause in pauses)
        running = (end - start).total_seconds() - paused
        return (running_watts * running + paused_watts * paused) / 3_600_000

    return kwh
