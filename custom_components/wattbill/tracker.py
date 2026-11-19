"""The Run engine for one Device: its Status input opens and closes Runs."""

import asyncio
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
from .device_inputs import input_time, input_value
from .images import DeviceImages
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
        self,
        hass: HomeAssistant,
        book: RunBook,
        config: DeviceConfig,
        images: DeviceImages,
    ) -> None:
        self._hass = hass
        self._book = book
        self._config = config
        self._images = images
        self._unsubscribe: list[CALLBACK_TYPE] = []
        # Until WattBill has seen the Status input, it may have missed the end.
        self._status_lost = True

    @callback
    def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        self._images.async_start()
        run = self._book.open_run(self._config.device_id)
        self._apply(self._hass.states.get(self._config.status_entity_id))
        # A Run still open after a restart or reconfigure gets the current Thumbnail.
        if run is not None and self._book.open_run(self._config.device_id) is run:
            self._images.async_copy_thumbnail(run)

    @callback
    def async_stop(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()
        self._images.async_stop()

    @callback
    def _on_status(self, event: Event[EventStateChangedData]) -> None:
        self._apply(event.data["new_state"])

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
            # The camera already shows the next print.
            self._end(
                run, run.last_seen or run.started, Outcome.UNKNOWN, snapshot=False
            )
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
        )
        self._refresh(run, at)
        self._book.async_start(run)
        self._images.async_copy_thumbnail(run)

    async def async_end_run(self) -> None:
        """End the open Run now as Unknown, e.g. because its Device is removed."""
        if run := self._book.open_run(self._config.device_id):
            await self._end(run, dt_util.utcnow(), Outcome.UNKNOWN)

    def _end(
        self, run: Run, at: datetime, outcome: Outcome, *, snapshot: bool = True
    ) -> asyncio.Task[None]:
        run.ended = at
        if run.pauses and run.pauses[-1].end is None:
            run.pauses[-1].end = at
        run.outcome = outcome
        self._refresh(run, at)
        finalise = self._hass.async_create_task(self._book.async_finalise(run))
        if snapshot:
            self._images.async_run_ended(run)
        return finalise

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
