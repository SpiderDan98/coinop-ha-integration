"""The Run engine for one Device: its Status input opens and closes Runs."""

import asyncio
from bisect import bisect_right
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.recorder import history
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
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from . import recorded
from .catalog import Catalog
from .cost import consumption
from .cost.electricity import electricity_line_item, price_gap
from .cost.material import GRAM, MILLILITRE, material_line_item, slot_line_items
from .cost.slots import slot_material, slot_shares
from .device_config import ConsumptionSource, DeviceConfig, Target
from .device_inputs import (
    input_time,
    input_value,
    meter_reading,
    price_reading,
    slot_colour,
    slot_number,
    usage_reading,
)
from .device_settings import (
    AUTOMATIC_TEMPLATES,
    DEFAULT_MATERIAL,
    TAGS_FOR_NEW_RUNS,
    DeviceSettings,
)
from .images import DeviceImages
from .materials import Material, MaterialForm, SpoolmanPrice
from .models import (
    ElectricityMethod,
    Flag,
    LineItem,
    LineItemKind,
    LoadedSlot,
    Outcome,
    Pause,
    Run,
    SlotReport,
    Usage,
)
from .run_book import RunBook
from .spoolman import Spoolman
from .store import LIVE_SAVE_DELAY
from .templates import add_templates, count_running_hours

LIVE_INTERVAL = timedelta(minutes=1)
FINAL_REPORT_WAIT = timedelta(minutes=5)
# An open Run is refreshed every minute and saved about a minute later; a longer
# silence means WattBill wasn't watching the meter.
OUTAGE = LIVE_INTERVAL + LIVE_SAVE_DELAY
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
        self,
        hass: HomeAssistant,
        book: RunBook,
        config: DeviceConfig,
        settings: DeviceSettings,
        images: DeviceImages,
        catalog: Catalog,
        spoolman: Spoolman,
    ) -> None:
        self._hass = hass
        self._book = book
        self._config = config
        self._settings = settings
        self._images = images
        self._catalog = catalog
        self._spoolman = spoolman
        self._unsubscribe: list[CALLBACK_TYPE] = []
        # Until WattBill has seen the Status input, it may have missed the end.
        self._status_lost = True
        self._final_waits: dict[str, CALLBACK_TYPE] = {}
        self._finalised: dict[str, asyncio.Future[None]] = {}
        self._finishing: set[str] = set()
        # The price entity's last valid report, for a Run starting while it has none.
        self._last_price: tuple[datetime, float] | None = None

    async def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        if price_entity_id := self._config.price_entity_id:
            self._unsubscribe.append(
                async_track_state_change_event(
                    self._hass, price_entity_id, self._on_price
                )
            )
            self._remember_price(self._hass.states.get(price_entity_id))
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
        if usage := self._config.material:
            self._unsubscribe += [
                async_track_state_change_event(
                    self._hass, usage["entity_id"], self._on_usage
                ),
                async_track_state_report_event(
                    self._hass, usage["entity_id"], self._on_usage
                ),
            ]
        if loaded_slot := self._config.loaded_slot_entity_id:
            self._unsubscribe.append(
                async_track_state_change_event(
                    self._hass, [loaded_slot, *self._config.slots], self._on_slot
                )
            )
        if run := self._book.open_run(self._config.device_id):
            self._record_slot(run)
            await self._async_follow_device(run)
        for run in self._unfinalised_runs():
            self._record_usage(run, self._usage_state())
            await self._async_catch_up(run)
            if run.ended is not None:
                self._await_final_report(run)
        self._images.async_start()
        open_run = self._book.open_run(self._config.device_id)
        self._apply(self._hass.states.get(self._config.status_entity_id))
        # A Run still open after a restart or reconfigure gets the current Thumbnail.
        if open_run and self._book.open_run(self._config.device_id) is open_run:
            self._images.async_copy_thumbnail(open_run)

    async def _async_follow_device(self, run: Run) -> None:
        """Apply the Device's price and average power to the open Run from now on.

        The same price entity as before only catches up on missed reports.
        """
        now = dt_util.utcnow()
        self._follow_average_power(run, now)
        price = dict(self._config.price)
        if run.cost_source != price:
            # A Run stored before it had a Cost Source followed this one from start.
            since = run.started if run.cost_source is None else now
            run.cost_source = price
            self._add_price(run, since, self._current_price())
        elif entity_id := self._config.price_entity_id:
            since = run.prices[-1][0] if run.prices else run.started
            for state in await self._async_history(entity_id, since, now):
                self._record_price(run, state)
            self._record_price(run, self._hass.states.get(entity_id))
        self._book.async_update(run)

    def _follow_average_power(self, run: Run, at: datetime) -> None:
        # Unless the Device changed its consumption source since the Run started.
        current = self._config.consumption
        pinned = run.consumption
        section = (
            current if not pinned or pinned["source"] == current["source"] else pinned
        )
        powers = (section.get("running_power"), section.get("paused_power"))
        if not run.average_powers:
            run.average_powers = [(run.started, *powers)]
        elif run.average_powers[-1][1:] != powers:
            run.average_powers.append((at, *powers))

    async def _async_catch_up(self, run: Run) -> None:
        """Add the meter reports missed while WattBill wasn't running."""
        if not (meter := _meter(run.consumption)):
            return
        entity_id = meter["entity_id"]
        now = dt_util.utcnow()
        since = run.readings[-1][0] if run.readings else run.started
        missed = await self._async_history(entity_id, since, now)
        for state in missed:
            self._record(run, state)
        if current := self._hass.states.get(entity_id):
            self._record(run, current)
        watched = max(
            [
                run.electricity.segments[-1].end,
                *(state.last_updated for state in missed),
            ]
        )
        if now - watched > OUTAGE:
            self._add_reading(run, watched, None)
        if run.ended is None:
            self._refresh(run, now)
        self._book.async_update(run)

    async def _async_history(
        self, entity_id: str, start: datetime, end: datetime
    ) -> list[State]:
        if "recorder" not in self._hass.config.components:
            return []
        states = await get_instance(self._hass).async_add_executor_job(
            partial(
                history.state_changes_during_period,
                self._hass,
                start,
                end,
                entity_id,
                include_start_time_state=False,
            )
        )
        return states.get(entity_id, [])

    @callback
    def async_stop(self) -> None:
        while self._unsubscribe:
            self._unsubscribe.pop()()
        while self._final_waits:
            self._final_waits.popitem()[1]()
        self._images.async_stop()

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
            elif not self._awaits_report(run):
                self._finish(run)
                continue
            self._book.async_update(run)

    @callback
    def _on_usage(
        self, event: Event[EventStateChangedData] | Event[EventStateReportedData]
    ) -> None:
        for run in self._unfinalised_runs():
            if run.ended is not None and run.id not in self._final_waits:
                # Already being finalised.
                continue
            self._record_usage(run, event.data["new_state"])
            if run.ended is not None and not self._awaits_report(run):
                self._finish(run)
                continue
            self._refresh(run, run.ended or dt_util.utcnow())
            self._book.async_update(run)

    def _usage_state(self) -> State | None:
        usage = self._config.material
        return None if usage is None else self._hass.states.get(usage["entity_id"])

    def _record_usage(self, run: Run, state: State | None) -> None:
        """Keep the Material used input's report if it is valid and the Run's own."""
        if (usage := self._config.material) is None or state is None:
            return
        if (reading := usage_reading(state, usage)) is None:
            return
        changed = input_time(state, usage["attribute"])
        late = run.ended is not None and changed > run.ended + FINAL_REPORT_WAIT
        # A value from before the Run is still the previous job's.
        if changed < run.started or late:
            return
        run.usage = Usage(max(changed, state.last_reported), *reading)

    @callback
    def _on_slot(self, event: Event[EventStateChangedData]) -> None:
        if (run := self._book.open_run(self._config.device_id)) and self._record_slot(
            run
        ):
            self._refresh(run, dt_util.utcnow())
            self._book.async_update(run)

    def _record_slot(self, run: Run) -> bool:
        """Note a change of the loaded Slot or its report; whether there was one.

        While the Loaded slot input or the loaded Slot's entity has no value, the
        last report stands; the first one known counts from the Run's start.
        """
        if (entity_id := self._config.loaded_slot_entity_id) is None:
            return False
        loaded_state = self._hass.states.get(entity_id)
        if (value := input_value(loaded_state, None)) is None:
            return False
        assert loaded_state is not None
        at = loaded_state.last_changed
        slot: SlotReport | None = None
        slots = self._config.slots
        loaded = run.loaded_slots
        previous = loaded[-1].slot if loaded else None
        if number := slot_number(value, len(slots)):
            state = self._hass.states.get(slots[number - 1])
            if (material_type := input_value(state, None)) is None:
                return False
            assert state is not None
            colour = self._config.colour_attribute
            slot = SlotReport(
                number,
                material_type,
                slot_colour(state.attributes.get(colour)) if colour else None,
            )
            if previous and previous.number == number:
                # The same Slot, refilled.
                at = state.last_updated
        if loaded and previous == slot:
            return False
        loaded.append(
            LoadedSlot(max(at, loaded[-1].since) if loaded else run.started, slot)
        )
        return True

    def _material(self) -> Material | None:
        """The Material a Run of this Device is charged for."""
        material_id = self._settings.get(self._config.device_id)[DEFAULT_MATERIAL]
        material = self._catalog.material(material_id) if material_id else None
        return None if material is None or material.archived else material

    @callback
    def _on_price(self, event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        self._remember_price(state)
        if run := self._book.open_run(self._config.device_id):
            self._record_price(run, state)
            self._refresh(run, dt_util.utcnow())
            self._book.async_update(run)

    def _price_of(self, state: State | None) -> float | None:
        return price_reading(state, self._config.price, self._hass.config.currency)

    def _current_price(self) -> float | None:
        if (entity_id := self._config.price_entity_id) is None:
            value: float = self._config.price["value"]
            return value
        return self._price_of(self._hass.states.get(entity_id))

    def _remember_price(self, state: State | None) -> None:
        if state is not None and (price := self._price_of(state)) is not None:
            self._last_price = (self._price_time(state), price)

    def _price_time(self, state: State) -> datetime:
        return input_time(state, self._config.price.get("attribute"))

    def _record_price(self, run: Run, state: State | None) -> None:
        """Add the price entity's report to the Run's price timeline."""
        if state is None:
            self._add_price(run, dt_util.utcnow(), None)
        else:
            self._add_price(run, self._price_time(state), self._price_of(state))

    @staticmethod
    def _add_price(run: Run, at: datetime, price: float | None) -> None:
        prices = run.prices
        index = bisect_right(prices, at, key=lambda entry: entry[0])
        if index and prices[index - 1][0] == at:
            prices[index - 1] = (at, price)
        elif not index or prices[index - 1][1] != price:
            prices.insert(index, (at, price))

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
        settings = self._settings.get(self._config.device_id)
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
            cost_source=dict(self._config.price),
            tags=settings[TAGS_FOR_NEW_RUNS],
        )
        if meter := _meter(run.consumption):
            self._record(run, self._hass.states.get(meter["entity_id"]))
        self._follow_average_power(run, at)
        self._record_usage(run, self._usage_state())
        self._record_slot(run)
        self._open_prices(run, at)
        self._refresh(run, at)
        add_templates(
            run, self._catalog.find_templates(settings[AUTOMATIC_TEMPLATES]), at
        )
        self._book.async_start(run)
        self._images.async_copy_thumbnail(run)

    async def async_create_run(
        self,
        started: datetime,
        ended: datetime,
        outcome: Outcome,
        name: str | None,
        tags: list[str] | None,
    ) -> Run:
        """A Run made by hand, final at once: no Snapshot, no `started` or `ended`.

        Without `tags` it gets the Device's Tags for new Runs.
        """
        settings = self._settings.get(self._config.device_id)
        run = Run(
            id=ulid_now(),
            device_id=self._config.device_id,
            device_name=self._config.name,
            name=name,
            started=started,
            ended=ended,
            outcome=outcome,
            finalised=True,
            line_items=[],
            consumption=dict(self._config.consumption),
            cost_source=dict(self._config.price),
            tags=settings[TAGS_FOR_NEW_RUNS] if tags is None else tags,
        )
        covered = await recorded.async_covers(self._hass, started, ended)
        await self._async_past_prices(run, covered)
        run.line_items = [await self._async_past_electricity(run, covered)]
        run.readings, run.prices = [], []
        self._settle_material(run, measuring=False)
        add_templates(
            run, self._catalog.find_templates(settings[AUTOMATIC_TEMPLATES]), ended
        )
        await self._book.async_add(run)
        return run

    async def _async_past_prices(self, run: Run, covered: bool) -> None:
        """A past Run's price timeline from history, flagged where it has none."""
        assert run.ended is not None
        if (entity_id := self._config.price_entity_id) is None:
            self._add_price(run, run.started, self._current_price())
            return
        states = await recorded.async_states(
            self._hass, entity_id, run.started, run.ended
        )
        if not any(self._price_time(state) <= run.started for state in states):
            self._add_price(run, run.started, None)
        for state in states:
            self._record_price(run, state)
        if not covered or price_gap(run.started, run.ended, run.prices):
            # Without the recorder, the last price it knew may be outdated.
            self._flag(run, Flag.PRICE_GAP)

    async def _async_past_electricity(self, run: Run, covered: bool) -> LineItem:
        """From the meter's history if it covers the Run, else estimated from the
        average running power, else left for the user to enter.
        """
        assert run.ended is not None
        start, end, prices = run.started, run.ended, run.prices
        meter = _meter(run.consumption)
        if covered and meter:
            states = await recorded.async_states(
                self._hass, meter["entity_id"], start, end
            )
            before = [state for state in states if state.last_updated <= start]
            if before and meter_reading(before[-1], meter) is not None:
                for state in states[len(before) - 1 :]:
                    self._record(run, state)
                self._follow_average_power(run, start)
                return electricity_line_item(
                    ulid_now(),
                    start,
                    end,
                    self._kwh(run),
                    prices,
                    ElectricityMethod.FROM_HISTORY,
                )
        if (running := self._config.consumption.get("running_power")) is not None:
            return electricity_line_item(
                ulid_now(),
                start,
                end,
                consumption.estimate(running, running, []),
                prices,
                ElectricityMethod.ESTIMATED,
            )
        item = electricity_line_item(
            ulid_now(), start, end, lambda _, __: 0.0, prices, ElectricityMethod.ENTERED
        )
        item.quantity, item.segments = None, []
        return item

    def _open_prices(self, run: Run, at: datetime) -> None:
        """The price at Run start; without one, the last valid price before it."""
        if (entity_id := self._config.price_entity_id) is None:
            self._add_price(run, at, self._current_price())
            return
        state = self._hass.states.get(entity_id)
        if self._price_of(state) is None and self._last_price:
            self._add_price(run, *self._last_price)
        if state is None:
            self._add_price(run, at, None)
        else:
            self._record_price(run, state)

    @callback
    def async_end_run(self) -> asyncio.Future[None]:
        """End the open Run now as Unknown ("End Run now", or its Device is removed).

        The result is done once the Run is finalised, which a metered Run awaits
        up to five minutes for.
        """
        if run := self._book.open_run(self._config.device_id):
            return self._end(run, dt_util.utcnow(), Outcome.UNKNOWN)
        done = self._hass.loop.create_future()
        done.set_result(None)
        return done

    def _end(
        self, run: Run, at: datetime, outcome: Outcome, *, snapshot: bool = True
    ) -> asyncio.Future[None]:
        """End the Run now; the result is done once it is finalised."""
        run.ended = at
        if run.pauses and run.pauses[-1].end is None:
            run.pauses[-1].end = at
        run.outcome = outcome
        self._refresh(run, at)
        if snapshot:
            self._images.async_run_ended(run)
        if self._awaits_report(run):
            self._book.async_update(run)
        return self._await_final_report(run)

    def _awaits_report(self, run: Run) -> bool:
        """Whether the meter or the Material used input may still report the Run's end."""
        assert run.ended is not None
        if _meter(run.consumption) and not self._has_final_report(run):
            return True
        return self._config.material is not None and (
            run.usage is None or run.usage.at < run.ended
        )

    def _await_final_report(self, run: Run) -> asyncio.Future[None]:
        """Freeze the Run at the inputs' next reports, at the latest after the wait."""
        finalised = self._finalised.setdefault(run.id, self._hass.loop.create_future())
        assert run.ended is not None
        if not self._awaits_report(run):
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
        if run.id not in self._finishing:
            self._finishing.add(run.id)
            self._hass.async_create_task(self._async_finish(run))

    async def _async_finish(self, run: Run) -> None:
        """Freeze the Run's values, with Material prices as Spoolman has them now."""
        read = await self._spoolman.async_update_prices()
        assert run.ended is not None
        self._refresh(run, run.ended)
        self._settle_material(run)
        if not read and self._uses_spoolman(run):
            self._flag(run, Flag.SPOOLMAN_UNREACHABLE)
        run.readings = []
        run.prices = []
        run.loaded_slots = []
        await self._async_finalise(run)
        self._finishing.discard(run.id)

    def _uses_spoolman(self, run: Run) -> bool:
        return any(
            isinstance(material.price, SpoolmanPrice)
            for item in run.line_items
            if item.material_id
            and (material := self._catalog.material(item.material_id))
        )

    def _settle_material(self, run: Run, *, measuring: bool = True) -> None:
        """Flag missing usage or Material; without a Material used input (or a
        measurement, as on a manual Run), add a Material Line Item to fill in
        unless the user already added one."""
        items = [i for i in run.line_items if i.measured]
        if not (measuring and self._config.material) and not any(
            i.kind is LineItemKind.MATERIAL for i in run.line_items
        ):
            material = self._material()
            resin = material is not None and material.form is MaterialForm.RESIN
            item = material_line_item(
                ulid_now(),
                None,
                material,
                measured=False,
                unit=MILLILITRE if resin else GRAM,
            )
            run.line_items.append(item)
            items.append(item)
        if any(item.share is not None for item in items):
            self._flag(run, Flag.ESTIMATED_SPLIT)
        if any(
            self._slot_fell_back(slot)
            for item in items
            if item.material_id is not None
            for slot in item.slots
        ):
            self._flag(run, Flag.SLOT_FALLBACK)
        for item in items:
            if item.quantity is None and item.length is None:
                self._flag(run, Flag.USAGE_MISSING)
            if item.material_id is None:
                self._flag(run, Flag.MATERIAL_MISSING)

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
        meter = _meter(run.consumption)
        if meter and meter["source"] == ConsumptionSource.ENERGY:
            return consumption.energy(run.readings)
        return consumption.piecewise(
            [
                (
                    since,
                    consumption.power(run.readings, running)
                    if meter
                    else consumption.estimate(
                        running or 0.0,
                        running or 0.0 if paused is None else paused,
                        run.pauses,
                    ),
                )
                for since, running, paused in run.average_powers
            ]
        )

    def _slot_fell_back(self, slot: SlotReport) -> bool:
        return slot_material(slot, self._catalog.materials()) is None

    def _measured_items(self, run: Run, until: datetime) -> list[LineItem]:
        """The measured total attributed through the loaded Slots, else to the default."""
        ids = {i.material_id: i.id for i in run.line_items if i.measured}
        spare = list(ids.values())

        def item_id(material_id: str | None) -> str:
            # A Line Item keeps its id while its Material stays.
            if (found := ids.get(material_id)) in spare:
                spare.remove(found)
                return found
            return spare.pop(0) if spare else ulid_now()

        shares = slot_shares(run.loaded_slots, run.pauses, until)
        if not shares:
            return [material_line_item(item_id(None), run.usage, self._material())]
        materials = self._catalog.materials()
        return slot_line_items(
            run.usage,
            shares,
            lambda slot: slot_material(slot, materials) or self._material(),
            item_id,
        )

    def _refresh(self, run: Run, until: datetime) -> None:
        """Recompute the Run's live values up to `until`."""
        item = electricity_line_item(
            run.electricity.id if run.line_items else ulid_now(),
            run.started,
            until,
            self._kwh(run),
            run.prices,
            ElectricityMethod.MEASURED
            if _meter(run.consumption)
            else ElectricityMethod.ESTIMATED,
        )
        materials = self._measured_items(run, until) if self._config.material else []
        run.line_items = [
            item,
            *materials,
            *(
                i
                for i in run.line_items
                if i.kind is not LineItemKind.ELECTRICITY and not i.measured
            ),
        ]
        count_running_hours(run.line_items, run, until)
        if price_gap(run.started, until, run.prices):
            self._flag(run, Flag.PRICE_GAP)
