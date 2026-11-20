"""What the recorder kept of a past period, e.g. of a manual Run.

History covers a period only while the recorder was recording throughout it:
while Home Assistant was down there are no reports, however the states around
the gap look.
"""

from datetime import datetime, timedelta

from homeassistant.components.recorder import history
from homeassistant.components.recorder.db_schema import RecorderRuns
from homeassistant.components.recorder.models import process_timestamp
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.recorder import get_instance, session_scope
from homeassistant.util import dt as dt_util

# Reports this long before a period still count for interpolating at its start.
LOOKBACK = timedelta(hours=1)
# A restart this short leaves no gap worth knowing about.
RESTART = timedelta(minutes=5)


def _recording(hass: HomeAssistant) -> bool:
    return "recorder" in hass.config.components


async def async_covers(hass: HomeAssistant, start: datetime, end: datetime) -> bool:
    """Whether the recorder was recording throughout [start, end]."""
    if not _recording(hass):
        return False
    return await get_instance(hass).async_add_executor_job(_covers, hass, start, end)


def _covers(hass: HomeAssistant, start: datetime, end: datetime) -> bool:
    with session_scope(hass=hass, read_only=True) as session:
        runs = (
            session.query(RecorderRuns.start, RecorderRuns.end)
            .order_by(RecorderRuns.start)
            .all()
        )
    covered = start
    for run_start, run_end in runs:
        if process_timestamp(run_start) > covered + RESTART:
            break
        covered = max(
            covered, dt_util.utcnow() if run_end is None else process_timestamp(run_end)
        )
    return covered >= end


async def async_states(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> list[State]:
    """The entity's recorded states from before `start` to its first one after `end`.

    The first may be the state `LOOKBACK` before `start`, timed then.
    """
    if not _recording(hass):
        return []
    return await get_instance(hass).async_add_executor_job(
        _states, hass, entity_id, start, end
    )


def _states(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> list[State]:
    during = history.state_changes_during_period(hass, start - LOOKBACK, end, entity_id)
    # From just before `end`, as both queries leave out their bounds.
    after = history.state_changes_during_period(
        hass,
        end - timedelta(microseconds=1),
        None,
        entity_id,
        limit=1,
        include_start_time_state=False,
    )
    return [*during.get(entity_id, []), *after.get(entity_id, [])]
