"""The Run engine for one Device: its Status input opens and closes Runs."""

import asyncio
from datetime import datetime, timedelta
from functools import partial
import re

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

from . import recorded
from .catalog import Catalog
from .cost import consumption
from .cost.electricity import estimate
from .cost.material import GRAM, MILLILITRE, material_line_item, slot_line_items
from .cost.slots import slot_material, slot_shares
from .device_config import DeviceConfig, Target
from .device_inputs import (
    input_time,
    input_value,
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
from .metering import LIVE_INTERVAL, Metering
from .models import (
    ConsumptionMethod,
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
from .quantities import ELECTRICITY
from .run_book import RunBook
from .spoolman import Spoolman
from .templates import add_templates, count_running_hours
from .timelines import add_flag

FINAL_REPORT_WAIT = timedelta(minutes=5)
OUTCOMES = {
    Target.FINISHED: Outcome.COMPLETED,
    Target.CANCELLED: Outcome.CANCELLED,
    Target.ENDED: Outcome.UNKNOWN,
}

PRINT_FILE = re.compile(r"(\.gcode)?\.(gcode|bgcode|gco|3mf)$", re.IGNORECASE)


def job_title(job_name: str | None) -> str | None:
    """A Run's name from its job: "Gear_Set.gcode.3mf" becomes "Gear Set"."""
    if job_name is None:
        return None
    return PRINT_FILE.sub("", job_name).replace("_", " ").strip() or job_name


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
        # Until Coin-op has seen the Status input, it may have missed the end.
        self._status_lost = True
        self._final_waits: dict[str, CALLBACK_TYPE] = {}
        self._finalised: dict[str, asyncio.Future[None]] = {}
        self._finishing: set[str] = set()
        self._electricity = Metering(
            hass,
            ELECTRICITY,
            config,
            gap_rates=lambda run: [
                (since, running) for since, running, _ in run.average_powers
            ],
            fallback=lambda run: (
                self._estimate(run),
                ConsumptionMethod.ESTIMATED,
            ),
        )
        self._meterings = (self._electricity,)

    async def async_start(self) -> None:
        self._unsubscribe = [
            async_track_state_change_event(
                self._hass, self._config.status_entity_id, self._on_status
            ),
            async_track_time_interval(self._hass, self._on_tick, LIVE_INTERVAL),
        ]
        for metering in self._meterings:
            if price_entity_id := metering.price_entity_id:
                self._unsubscribe.append(
                    async_track_state_change_event(
                        self._hass, price_entity_id, partial(self._on_price, metering)
                    )
                )
                metering.remember_price(self._hass.states.get(price_entity_id))
        if meters := set[str]().union(
            *(m.meter_entities(self._unfinalised_runs()) for m in self._meterings)
        ):
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
        """Apply the Device's prices and average power to the open Run from now on."""
        now = dt_util.utcnow()
        self._follow_average_power(run, now)
        for metering in self._meterings:
            await metering.async_follow(run, now)
        self._book.async_update(run)

    def _estimate(self, run: Run) -> consumption.Model:
        """Electricity from the average powers, without measurement."""
        return consumption.piecewise(
            [
                (
                    since,
                    estimate(
                        running or 0.0,
                        running or 0.0 if paused is None else paused,
                        run.pauses,
                    ),
                )
                for since, running, paused in run.average_powers
            ]
        )

    def _follow_average_power(self, run: Run, at: datetime) -> None:
        # Unless the Device changed its consumption source since the Run started.
        current = self._config.consumption
        pinned = self._electricity.timeline(run).source
        section = (
            current if not pinned or pinned["source"] == current["source"] else pinned
        )
        powers = (section.get("running_power"), section.get("paused_power"))
        if not run.average_powers:
            run.average_powers = [(run.started, *powers)]
        elif run.average_powers[-1][1:] != powers:
            run.average_powers.append((at, *powers))

    async def _async_catch_up(self, run: Run) -> None:
        """Add the meter reports missed while Coin-op wasn't running."""
        now = dt_util.utcnow()
        metered = [await m.async_catch_up(run, now) for m in self._meterings]
        if not any(metered):
            return
        if run.ended is None:
            self._refresh(run, now)
        self._book.async_update(run)

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
            watching = [
                m for m in self._meterings if m.watches(run, event.data["entity_id"])
            ]
            if not watching:
                continue
            for metering in watching:
                metering.record(run, state)
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

    def _next_started(self, run: Run, at: datetime) -> bool:
        return any(
            run.started < other.started <= at for other in self._unfinalised_runs()
        )

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
        # A value from before the Run is still the previous job's, one from after
        # the next Run's start already that job's.
        if changed < run.started or late or self._next_started(run, changed):
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
    def _on_price(
        self, metering: Metering, event: Event[EventStateChangedData]
    ) -> None:
        run = self._book.open_run(self._config.device_id)
        metering.on_price(event.data["new_state"], run)
        if run:
            self._refresh(run, dt_util.utcnow())
            self._book.async_update(run)

    @callback
    def _on_tick(self, now: datetime) -> None:
        if run := self._book.open_run(self._config.device_id):
            now = dt_util.utcnow()
            if not self._status_lost and not run.paused:
                run.last_seen = now
            self._refresh(run, now)
            self._book.async_update(run)

    def _apply(self, state: State | None) -> None:
        attribute = self._config.status_attribute
        value = input_value(state, attribute)
        run = self._book.open_run(self._config.device_id)
        if state is None or value is None:
            if run is not None and not self._status_lost and not run.paused:
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
        if target is Target.RUNNING or not run.paused:
            run.last_seen = max(run.last_seen or run.started, at)
        if target in (Target.PAUSED, Target.FAULT):
            if target is Target.FAULT and Flag.FAULT not in run.flags:
                run.flags.append(Flag.FAULT)
            if not run.paused:
                run.pauses.append(Pause(at))
        elif target is Target.RUNNING:
            if run.paused:
                run.pauses[-1].end = at
            if run.job_name is None:
                run.job_name = job_name
                run.name = run.name or job_title(job_name)
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
            name=job_title(job_name),
            job_name=job_name,
            started=at,
            last_seen=at,
            line_items=[],
            tags=settings[TAGS_FOR_NEW_RUNS],
        )
        for metering in self._meterings:
            metering.open(run, at)
        self._follow_average_power(run, at)
        self._record_usage(run, self._usage_state())
        self._record_slot(run)
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
            tags=settings[TAGS_FOR_NEW_RUNS] if tags is None else tags,
        )
        for metering in self._meterings:
            metering.pin(run)
        covered = await recorded.async_covers(self._hass, started, ended)
        run.line_items = [await self._async_past_electricity(run, covered)]
        for metering in self._meterings:
            metering.finish(run)
        self._settle_material(run, measuring=False)
        add_templates(
            run, self._catalog.find_templates(settings[AUTOMATIC_TEMPLATES]), ended
        )
        await self._book.async_add(run)
        return run

    async def _async_past_electricity(self, run: Run, covered: bool) -> LineItem:
        """From the meter's history if it covers the Run, else estimated from the
        average running power, else left for the user to enter.
        """
        assert run.ended is not None
        metering = self._electricity
        await metering.async_past_prices(run, covered)
        if await metering.async_past_readings(run, covered):
            self._follow_average_power(run, run.started)
            return metering.priced(
                run, run.ended, metering.model(run), ConsumptionMethod.FROM_HISTORY
            )
        if (running := self._config.consumption.get("running_power")) is not None:
            return metering.priced(
                run,
                run.ended,
                estimate(running, running, []),
                ConsumptionMethod.ESTIMATED,
            )
        item = metering.priced(
            run, run.ended, lambda _, __: 0.0, ConsumptionMethod.ENTERED
        )
        item.quantity, item.segments = None, []
        return item

    @callback
    def async_end_run(self) -> asyncio.Future[None]:
        """End the open Run now as Unknown ("End Run now").

        The result is done once the Run is finalised, which a metered Run awaits
        up to five minutes for.
        """
        if run := self._book.open_run(self._config.device_id):
            return self._end(run, dt_util.utcnow(), Outcome.UNKNOWN)
        done = self._hass.loop.create_future()
        done.set_result(None)
        return done

    async def async_remove(self) -> None:
        """Its Device is removed: end the open Run as Unknown and finalise every
        Run now with what it has, as no input will report for it any more."""
        if run := self._book.open_run(self._config.device_id):
            self._end(run, dt_util.utcnow(), Outcome.UNKNOWN)
        finalised = []
        for run in self._unfinalised_runs():
            finalised.append(
                self._finalised.setdefault(run.id, self._hass.loop.create_future())
            )
            self._finish(run)
        await asyncio.gather(*finalised)

    def _end(
        self, run: Run, at: datetime, outcome: Outcome, *, snapshot: bool = True
    ) -> asyncio.Future[None]:
        """End the Run now; the result is done once it is finalised."""
        run.ended = at
        # A Run closed when last seen running drops the pause it was lost in.
        run.pauses = [pause for pause in run.pauses if pause.start < at]
        if run.paused:
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
        if any(metering.awaits_report(run) for metering in self._meterings):
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
        linked = self._spoolman_prices(run)
        if not read and linked:
            add_flag(run, Flag.SPOOLMAN_UNREACHABLE)
        if any(price.last_read is None for price in linked):
            add_flag(run, Flag.SPOOLMAN_NO_PRICE)
        for metering in self._meterings:
            metering.finish(run)
        run.loaded_slots = []
        await self._async_finalise(run)
        self._finishing.discard(run.id)

    def _spoolman_prices(self, run: Run) -> list[SpoolmanPrice]:
        """The Cost Sources of the Run's Materials linked to Spoolman."""
        return [
            material.price
            for item in run.line_items
            if item.material_id
            and (material := self._catalog.material(item.material_id))
            and isinstance(material.price, SpoolmanPrice)
        ]

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
            add_flag(run, Flag.ESTIMATED_SPLIT)
        if any(
            self._slot_fell_back(slot)
            for item in items
            if item.material_id is not None
            for slot in item.slots
        ):
            add_flag(run, Flag.SLOT_FALLBACK)
        for item in items:
            if item.quantity is None and item.length is None:
                add_flag(run, Flag.USAGE_MISSING)
            if item.material_id is None:
                add_flag(run, Flag.MATERIAL_MISSING)

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
        consumed = [metering.refresh(run, until) for metering in self._meterings]
        kinds = {metering.quantity.kind for metering in self._meterings}
        materials = self._measured_items(run, until) if self._config.material else []
        run.line_items = [
            *consumed,
            *materials,
            *(i for i in run.line_items if i.kind not in kinds and not i.measured),
        ]
        count_running_hours(run.line_items, run, until)
