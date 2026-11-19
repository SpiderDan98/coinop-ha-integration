"""Running time of a Run: from start to end (or now), pauses excluded."""

from datetime import datetime, timedelta

from custom_components.wattbill.models import Run


def running_time(run: Run, now: datetime) -> timedelta:
    end = run.ended or now
    paused = sum(
        (
            max(timedelta(), min(pause.end or end, end) - max(pause.start, run.started))
            for pause in run.pauses
        ),
        timedelta(),
    )
    return max(timedelta(), end - run.started - paused)
