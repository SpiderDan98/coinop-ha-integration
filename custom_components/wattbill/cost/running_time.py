"""Running time: a Run's time from start to end (or `until` while open), pauses excluded."""

from datetime import datetime, timedelta

from custom_components.wattbill.models import Run


def running_time(run: Run, until: datetime) -> timedelta:
    end = run.ended or until
    paused = sum(
        (
            max(timedelta(), min(pause.end or end, end) - max(pause.start, run.started))
            for pause in run.pauses
        ),
        timedelta(),
    )
    return end - run.started - paused
