"""Running time: a Run's time from start to end (or `until` while open), pauses excluded."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from custom_components.coinop.models import Pause, Run


def running_between(
    start: datetime, end: datetime, pauses: Iterable[Pause]
) -> timedelta:
    """Time from `start` to `end` outside the pauses; a pause still open lasts to `end`."""
    paused = sum(
        (
            max(timedelta(), min(pause.end or end, end) - max(pause.start, start))
            for pause in pauses
        ),
        timedelta(),
    )
    return max(timedelta(), end - start - paused)


def running_time(run: Run, until: datetime) -> timedelta:
    return running_between(run.started, run.ended or until, run.pauses)
