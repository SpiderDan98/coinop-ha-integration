"""The Run engine for one Device: its Status input opens and closes Runs."""

import asyncio
from bisect import bisect_right
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

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
from .device_inputs import input_time, input_value, meter_reading
from .models import ElectricityMethod, Flag, Outcome, Pause, Run
from .run_book import RunBook

LIVE_INTERVAL = timedelta(minutes=1)
FINAL_REPORT_WAIT = timedelta(minutes=5)
OUTCOMES = {
    Target.FINISHED: Outcome.COMPLETED,
    Target.CANCELLED: Outcome.CANCELLED,
    Target.ENDED: Outcome.UNKNOWN,
}


def _meter(section: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The section's Energy or Power meter; None for an estimate."""
    if section is None or section["source"] == ConsumptionSource.ESTIMATE:
        return None
    return section


class DeviceTracker:
    def __init__(
        self, hass: HomeAssistant, book: RunBook, config: DeviceConfig
    ) -> None:
        self._hass = hass
        self._book = book
        self._config = config
        self._unsubscribe: list[CALLBACK_TYPE] = []
        # Until WattBill has seen the Status input, it may have missed the end.
        self._status_lost = True
        self._final_waits: dict[str, CALLBACK_TYPE] = {}
        self._finalised: dict[str, asyncio.Future[None]] = {}

    @callback
    def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        sections = [run.consumption for run in self._unfinalised_runs()]
        if meters := {
            meter["entity_id"]
            for section in [*sections, self._config.consumption]
            if (meter := _meter(section))
        }:
            self._unsubscribe += [
                async_track_state_change_event(self._hass, meters, self._on_meter),
                async_track_state_report_event(self._hass, meters, self._on_meter),
            ]
        for run in self._unfinalised_runs():
            if run.ended is not None:
                self._await_final_report(run)
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
            meter = _meter(run.consumption)
            if meter is None or meter["entity_id"] != event.data["entity_id"]:
                continue
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
            now = dt_util.utcnow()
            if not self._status_lost:
                run.last_seen = now
            self._refresh(run, now)
            self._book.async_update(run)

    def _apply(self, state: State | None) -> None:
        attribute = self._config.status_attribute
        value = input_value(state, attribute)
        run = self._book.open_run(self._config.device_id)
        if state is None or value is None:
            if run is not None and not self._status_lost:
                run.last_seen = (
                    dt_util.utcnow() if state is None else state.last_changed
                )
                self._book.async_update(run)
            self._status_lost = True
            return
        returned, self._status_lost = self._status_lost, False
        at = input_time(state, attribute)
        if run is not None and at < run.started:
            # E.g. a Status entity picked during the Run still shows an older end.
            return
        target = self._config.target(value)
        job_name = self._job_name()
        if (
            run is not None
            and target is Target.RUNNING
            and None not in (job_name, run.job_name)
            and job_name != run.job_name
        ):
            run.end_reconstructed = True
            self._end(run, run.last_seen or run.started, Outcome.UNKNOWN)
            run = None
        if run is None:
            if target is Target.RUNNING:
                self._open(at, job_name)
            return
        if target in OUTCOMES:
            outcome = OUTCOMES[target]
            if outcome is Outcome.CANCELLED and Flag.FAULT in run.flags:
                outcome = Outcome.FAILED
            run.end_reconstructed = returned
            self._end(run, at, outcome)
        else:
            self._continue(run, target, at, job_name)

    def _continue(
        self, run: Run, target: Target, at: datetime, job_name: str | None
    ) -> None:
        run.last_seen = max(run.last_seen or run.started, at)
        if target in (Target.PAUSED, Target.FAULT):
            if target is Target.FAULT and Flag.FAULT not in run.flags:
                run.flags.append(Flag.FAULT)
            if not run.pauses or run.pauses[-1].end is not None:
                run.pauses.append(Pause(at))
        elif target is Target.RUNNING:
            if run.pauses and run.pauses[-1].end is None:
                run.pauses[-1].end = at
            if run.job_name is None:
                run.job_name = job_name
                run.name = run.name or job_name
        self._book.async_update(run)

    def _job_name(self) -> str | None:
        if (entity_id := self._config.job_entity_id) is None:
            return None
        state = self._hass.states.get(entity_id)
        return input_value(state, self._config.job_attribute) or None

    def _open(self, at: datetime, job_name: str | None) -> None:
        run = Run(
            id=ulid_now(),
            device_id=self._config.device_id,
            device_name=self._config.name,
            name=job_name,
            job_name=job_name,
            started=at,
            last_seen=at,
            line_items=[],
            consumption=dict(self._config.consumption),
        )
        if meter := _meter(run.consumption):
            self._record(run, self._hass.states.get(meter["entity_id"]))
        self._refresh(run, at)
        self._book.async_start(run)

    async def async_end_run(self) -> None:
        """End the open Run now as Unknown, e.g. because its Device is removed."""
        if run := self._book.open_run(self._config.device_id):
            await self._end(run, dt_util.utcnow(), Outcome.UNKNOWN)

    def _end(self, run: Run, at: datetime, outcome: Outcome) -> asyncio.Future[None]:
        """End the Run now; the result is done once it is finalised."""
        run.ended = at
        if run.pauses and run.pauses[-1].end is None:
            run.pauses[-1].end = at
        run.outcome = outcome
        self._refresh(run, at)
        if _meter(run.consumption):
            self._book.async_update(run)
        return self._await_final_report(run)

    def _await_final_report(self, run: Run) -> asyncio.Future[None]:
        """Freeze the Run at the meter's next report, at the latest after the wait."""
        finalised = self._finalised.setdefault(run.id, self._hass.loop.create_future())
        assert run.ended is not None
        if not _meter(run.consumption) or self._has_final_report(run):
            self._finish(run)
            return finalised

        @callback
        def waited(now: datetime) -> None:
            self._final_waits.pop(run.id, None)
            self._finish(run)

        due = run.ended + FINAL_REPORT_WAIT - dt_util.utcnow()
        self._final_waits[run.id] = async_call_later(
            self._hass, max(due, timedelta()), waited
        )
        return finalised

    def _finish(self, run: Run) -> None:
        if cancel := self._final_waits.pop(run.id, None):
            cancel()
        assert run.ended is not None
        self._refresh(run, run.ended)
        run.readings = []
        self._hass.async_create_task(self._async_finalise(run))

    async def _async_finalise(self, run: Run) -> None:
        await self._book.async_finalise(run)
        if finalised := self._finalised.pop(run.id, None):
            finalised.set_result(None)

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
        meter = _meter(run.consumption)
        assert meter is not None
        value = meter_reading(state, meter)
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
            (meter := _meter(run.consumption))
            and meter["source"] == ConsumptionSource.ENERGY
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
        # Average power applies at once, unless the Device changed its source since.
        current = self._config.consumption
        pinned = run.consumption
        powers = (
            current if not pinned or pinned["source"] == current["source"] else pinned
        )
        running_power: float | None = powers.get("running_power")
        meter = _meter(pinned)
        if meter is None:
            paused_power = powers.get("paused_power")
            return consumption.estimate(
                running_power or 0.0,
                running_power or 0.0 if paused_power is None else paused_power,
                run.pauses,
            )
        if meter["source"] == ConsumptionSource.ENERGY:
            return consumption.energy(run.readings)
        return consumption.power(run.readings, running_power)

    def _refresh(self, run: Run, until: datetime) -> None:
        """Recompute the Run's live values up to `until`."""
        item = electricity_line_item(
            run.electricity.id if run.line_items else ulid_now(),
            run.started,
            until,
            self._kwh(run),
            [(run.started, self._config.price)],
            ElectricityMethod.MEASURED
            if _meter(run.consumption)
            else ElectricityMethod.ESTIMATED,
        )
        run.line_items = [item] + [i for i in run.line_items if i.kind is not item.kind]
