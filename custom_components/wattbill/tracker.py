"""The Run engine for one Device: its Status input opens and closes Runs."""

from datetime import datetime, timedelta

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .cost import consumption
from .cost.electricity import electricity_line_item
from .device_config import DeviceConfig, Target
from .device_inputs import input_value
from .models import ElectricityMethod, Flag, Outcome, Pause, Run
from .run_book import RunBook

LIVE_INTERVAL = timedelta(minutes=1)
OUTCOMES = {
    Target.FINISHED: Outcome.COMPLETED,
    Target.CANCELLED: Outcome.CANCELLED,
    Target.ENDED: Outcome.UNKNOWN,
}


class DeviceTracker:
    def __init__(
        self, hass: HomeAssistant, book: RunBook, config: DeviceConfig
    ) -> None:
        self._hass = hass
        self._book = book
        self._config = config
        self._unsubscribe: list[CALLBACK_TYPE] = []

    @callback
    def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        self._apply(self._hass.states.get(self._config.status_entity_id))

    @callback
    def async_stop(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()

    @callback
    def _on_status(self, event: Event[EventStateChangedData]) -> None:
        self._apply(event.data["new_state"])

    @callback
    def _on_tick(self, now: datetime) -> None:
        if run := self._book.open_run(self._config.device_id):
            self._refresh(run, dt_util.utcnow())
            self._book.async_update(run)

    def _apply(self, state: State | None) -> None:
        value = input_value(state, self._config.status_attribute)
        if state is None or value is None:
            return
        at = (
            state.last_changed
            if self._config.status_attribute is None
            else state.last_updated
        )
        target = self._config.target(value)
        run = self._book.open_run(self._config.device_id)
        if run is None:
            if target is Target.RUNNING:
                self._open(at)
        elif target in (Target.PAUSED, Target.FAULT):
            if target is Target.FAULT and Flag.FAULT not in run.flags:
                run.flags.append(Flag.FAULT)
            if not run.pauses or run.pauses[-1].end is not None:
                run.pauses.append(Pause(at))
            self._book.async_update(run)
        elif target is Target.RUNNING:
            if run.pauses and run.pauses[-1].end is None:
                run.pauses[-1].end = at
                self._book.async_update(run)
        elif target in OUTCOMES:
            outcome = OUTCOMES[target]
            if outcome is Outcome.CANCELLED and Flag.FAULT in run.flags:
                outcome = Outcome.FAILED
            self._end(run, at, outcome)

    def _open(self, at: datetime) -> None:
        run = Run(
            id=ulid_now(),
            device_id=self._config.device_id,
            device_name=self._config.name,
            started=at,
            line_items=[],
        )
        self._refresh(run, at)
        self._book.async_start(run)

    def _end(self, run: Run, at: datetime, outcome: Outcome) -> None:
        run.ended = at
        if run.pauses and run.pauses[-1].end is None:
            run.pauses[-1].end = at
        run.outcome = outcome
        self._refresh(run, at)
        self._hass.async_create_task(self._book.async_finalise(run))

    def _refresh(self, run: Run, until: datetime) -> None:
        """Recompute the Run's live values up to `until`."""
        config = self._config
        paused_power = (
            config.running_power if config.paused_power is None else config.paused_power
        )
        item = electricity_line_item(
            run.electricity.id if run.line_items else ulid_now(),
            run.started,
            until,
            consumption.estimate(config.running_power, paused_power, run.pauses),
            [(run.started, config.price)],
            ElectricityMethod.ESTIMATED,
        )
        run.line_items = [item] + [i for i in run.line_items if i.kind is not item.kind]
