"""What the open Run's projection reads from the Device's inputs over time: the time
left and Progress held through a pause, and the drying units' spans.

Tracker state only, never stored on the Run (ADR 0002).
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NamedTuple

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State
from homeassistant.util import dt as dt_util

from .cost.projection import Span, progress_time_left
from .device_config import DeviceConfig
from .device_inputs import drying, progress_reading, time_left
from .models import Run

# How soon before a pause's Status a progress input's change still belongs to the
# pause: integrations write both from one update, in no set order.
PAUSE_GRACE = timedelta(seconds=5)


class Held(NamedTuple):
    """What is held through the pause that started at `start`."""

    start: datetime
    time_left: timedelta | None
    percent: float | None


class Progress:
    """The open Run's time left and Progress, held through a pause at their values
    from before it, since some integrations drop them to 0 or unknown while paused."""

    def __init__(self, hass: HomeAssistant, config: DeviceConfig) -> None:
        self._hass = hass
        self._config = config
        # The progress inputs' states before their last change.
        self._before: dict[str, State] = {}
        self._held: Held | None = None

    def remember(self, event: Event[EventStateChangedData]) -> None:
        if before := event.data["old_state"]:
            self._before[event.data["entity_id"]] = before

    def time_left(self, run: Run, now: datetime) -> timedelta | None:
        """The open Run's time left; None while unknown."""
        if (held := self._held_now(run)) and held.time_left is not None:
            return held.time_left
        return self._time_left_at(run, now, self._hass.states.get)

    def percent(self, run: Run) -> float | None:
        """The open Run's Progress."""
        if (held := self._held_now(run)) and held.percent is not None:
            return held.percent
        progress = self._config.progress_entity_id
        return progress_reading(self._hass.states.get(progress)) if progress else None

    def hold(self, run: Run, start: datetime) -> None:
        """Hold the values the progress inputs gave before the pause at `start`."""

        def before(entity_id: str) -> State | None:
            state = self._hass.states.get(entity_id)
            if state is None or state.last_changed < start - PAUSE_GRACE:
                return state
            return self._before.get(entity_id)

        progress = self._config.progress_entity_id
        self._held = Held(
            start,
            self._time_left_at(run, start, before),
            progress_reading(before(progress)) if progress else None,
        )

    def _held_now(self, run: Run) -> Held | None:
        if not run.paused:
            return None
        start = run.pauses[-1].start
        if self._held is None or self._held.start != start:
            self.hold(run, start)
        return self._held

    def _time_left_at(
        self, run: Run, at: datetime, state: Callable[[str], State | None]
    ) -> timedelta | None:
        """The time left at `at` from the Remaining time's `state`, else from the
        Progress's; None while neither tells."""
        remaining = self._config.remaining_time_entity_id
        left = time_left(state(remaining), at) if remaining else None
        if left is not None:
            return left
        progress = self._config.progress_entity_id
        percent = progress_reading(state(progress)) if progress else None
        return None if percent is None else progress_time_left(run, at, percent)


class Drying:
    """The drying units' spans of drying in the open Run, as far as Coin-op saw them."""

    def __init__(self, hass: HomeAssistant, config: DeviceConfig) -> None:
        self._hass = hass
        self._config = config
        self._run: str | None = None
        # By active entity: the spans it dried, and since when it dries now.
        self._spans: dict[str, list[Span]] = {}
        self._since: dict[str, datetime | None] = {}
        # Before it, whether a unit dried in the Run is unknown.
        self._known = dt_util.utcnow()

    def follow(self, run: Run) -> None:
        """Start following the units for the open Run, from what they show."""
        if self._run == run.id:
            return
        self._run, self._known = run.id, run.started
        self._spans, self._since = {}, {}
        for unit in self._config.drying:
            state = self._hass.states.get(unit["active"])
            if state:
                self._known = max(self._known, state.last_changed)
            self._spans[unit["active"]] = []
            self._since[unit["active"]] = (
                max(run.started, state.last_changed)
                if state and drying(state)
                else None
            )

    def on_change(self, run: Run, event: Event[EventStateChangedData]) -> None:
        self.follow(run)
        entity_id, state = event.data["entity_id"], event.data["new_state"]
        at = dt_util.utcnow() if state is None else state.last_changed
        since = self._since[entity_id]
        if drying(state) and since is None:
            self._since[entity_id] = at
        elif not drying(state) and since is not None:
            self._spans[entity_id].append((since, at))
            self._since[entity_id] = None

    def dried(self, run: Run, until: datetime) -> list[list[Span]]:
        """Each unit's spans of drying in the open Run up to `until`."""
        self.follow(run)
        return [
            [*spans, *([(since, until)] if (since := self._since[unit]) else [])]
            for unit, spans in self._spans.items()
        ]

    def unknown(self, run: Run) -> list[Span]:
        """The open Run's time before Coin-op saw every unit's state."""
        self.follow(run)
        return [(run.started, self._known)]

    def left(self, now: datetime) -> list[timedelta | None]:
        """The drying left of each unit drying now, None for one without a drying
        left input; a unit whose drying left reads nothing is left out."""
        states = self._hass.states
        lefts = [
            (entity, time_left(states.get(entity), now) if entity else None)
            for unit in self._config.drying
            if drying(states.get(unit["active"]))
            for entity in [unit["drying_left"]]
        ]
        return [left for entity, left in lefts if left is not None or not entity]
