"""The Run engine for one Device: its Status input opens and closes Runs."""

from bisect import bisect_right
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .cost import consumption
from .cost.electricity import electricity_line_item
from .device_config import ConsumptionSource, DeviceConfig, Target
from .device_inputs import input_value, meter_reading
from .models import ElectricityMethod, Flag, Outcome, Run
from .run_book import RunBook

LIVE_INTERVAL = timedelta(minutes=1)
FINAL_REPORT_WAIT = timedelta(minutes=5)
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
        self._final_waits: dict[str, CALLBACK_TYPE] = {}

    @callback
    def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        if meter := self._config.meter_entity_id:
            self._unsubscribe += [
                async_track_state_change_event(self._hass, meter, self._on_meter),
                async_track_state_report_event(self._hass, meter, self._on_meter),
            ]
        self._apply(self._hass.states.get(self._config.status_entity_id))

    @callback
    def async_stop(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()
        while self._final_waits:
            self._final_waits.popitem()[1]()

    @callback
    def _on_status(self, event: Event[EventStateChangedData]) -> None:
        self._apply(event.data["new_state"])

    @callback
    def _on_meter(
        self, event: Event[EventStateChangedData] | Event[EventStateReportedData]
    ) -> None:
        state = event.data["new_state"]
        for run in self._unfinalised_runs():
            self._record(run, state)
            if run.ended is None:
                self._refresh(run, dt_util.utcnow())
            elif self._has_final_report(run):
                self._finish(run)
                continue
            self._book.async_update(run)

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
        if target is Target.RUNNING and run is None:
            self._open(at)
        elif target in OUTCOMES and run is not None:
            self._end(run, at, OUTCOMES[target])

    def _open(self, at: datetime) -> None:
        run = Run(
            id=ulid_now(),
            device_id=self._config.device_id,
            device_name=self._config.name,
            started=at,
            line_items=[],
        )
        if meter := self._config.meter_entity_id:
            self._record(run, self._hass.states.get(meter))
        self._refresh(run, at)
        self._book.async_start(run)

    def _end(self, run: Run, at: datetime, outcome: Outcome) -> None:
        run.ended = at
        run.outcome = outcome
        self._refresh(run, at)
        if self._config.source is ConsumptionSource.ESTIMATE or self._has_final_report(
            run
        ):
            self._finish(run)
            return
        self._book.async_update(run)
        self._await_final_report(run)

    def _await_final_report(self, run: Run) -> None:
        """Freeze the Run at the meter's next report, at the latest after the wait."""
        assert run.ended is not None
        due = run.ended + FINAL_REPORT_WAIT - dt_util.utcnow()

        @callback
        def waited(now: datetime) -> None:
            self._final_waits.pop(run.id, None)
            self._finish(run)

        self._final_waits[run.id] = async_call_later(
            self._hass, max(due, timedelta()), waited
        )

    def _finish(self, run: Run) -> None:
        if cancel := self._final_waits.pop(run.id, None):
            cancel()
        assert run.ended is not None
        self._refresh(run, run.ended)
        run.readings = []
        self._hass.async_create_task(self._book.async_finalise(run))

    def _unfinalised_runs(self) -> list[Run]:
        return [
            run
            for run in self._book.runs()
            if run.device_id == self._config.device_id and not run.finalised
        ]

    def _has_final_report(self, run: Run) -> bool:
        return any(
            value is not None and run.ended is not None and at >= run.ended
            for at, value in run.readings
        )

    def _record(self, run: Run, state: State | None) -> None:
        """Add the meter's report to the Run's readings and flag gaps and resets."""
        value = meter_reading(state, self._config)
        if state is None:
            self._add_reading(run, dt_util.utcnow(), None)
        elif value is None:
            self._add_reading(run, state.last_updated, None)
        else:
            self._add_reading(run, state.last_updated, value)
            self._add_reading(run, state.last_reported, value)

    def _add_reading(self, run: Run, at: datetime, value: float | None) -> None:
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
                self._flag(run, Flag.CONSUMPTION_GAP)
        elif (
            self._config.source is ConsumptionSource.ENERGY
            and previous is not None
            and value < previous[1]
            and (run.ended is None or previous[0] < run.ended)
        ):
            self._flag(run, Flag.METER_RESET)

    @staticmethod
    def _flag(run: Run, flag: Flag) -> None:
        if flag not in run.flags:
            run.flags.append(flag)

    def _kwh(self, run: Run) -> Callable[[datetime, datetime], float]:
        config = self._config
        if config.source is ConsumptionSource.ENERGY:
            return consumption.energy(run.readings)
        if config.source is ConsumptionSource.POWER:
            return consumption.power(run.readings, config.running_power)
        running_power = config.running_power or 0.0
        paused_power = (
            running_power if config.paused_power is None else config.paused_power
        )
        return consumption.estimate(running_power, paused_power, run.pauses)

    def _refresh(self, run: Run, until: datetime) -> None:
        """Recompute the Run's live values up to `until`."""
        item = electricity_line_item(
            run.electricity.id if run.line_items else ulid_now(),
            run.started,
            until,
            self._kwh(run),
            [(run.started, self._config.price)],
            ElectricityMethod.ESTIMATED
            if self._config.source is ConsumptionSource.ESTIMATE
            else ElectricityMethod.MEASURED,
        )
        run.line_items = [item] + [i for i in run.line_items if i.kind is not item.kind]
