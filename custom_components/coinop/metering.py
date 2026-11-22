"""Following one consumed quantity for a Device's Runs, whatever the quantity.

Its meter or rate input and its price become the Run's timeline (missed
reports filled from recorder history), and the timeline its priced Line Item.
Only the fallback without measurement is the quantity's own; without a
measurement or a fallback the Run gets no Line Item of the quantity, and a Run
that started with source none has neither.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from . import recorded
from .cost.consumption import Model, spread
from .cost.pricing import price_gap, priced_line_item
from .device_config import NO_SOURCE, Capability, DeviceConfig
from .device_inputs import input_time, meter_reading, price_reading
from .models import ConsumptionMethod, Flag, LineItem, Run, Timeline
from .quantities import Quantity
from .store import LIVE_SAVE_DELAY
from .timelines import (
    add_flag,
    add_price,
    add_reading,
    has_final_report,
    meter_of,
    model,
)

LIVE_INTERVAL = timedelta(minutes=1)
# An open Run is refreshed every minute and saved about a minute later; a longer
# silence means Coin-op wasn't watching the meter.
OUTAGE = LIVE_INTERVAL + LIVE_SAVE_DELAY

type Fallback = tuple[Model | float | None, ConsumptionMethod]


class Metering:
    """One quantity of a Device's Runs.

    `gap_rates(run)` are the (since, rate) a rate input's gaps hold, None for its
    last value; `fallback(run)` is the method without measurement with a model,
    an amount for the whole Run (spread evenly over it) or None for no value (an
    empty quantity), and is None for no Line Item at all; it isn't asked for a Run
    that started with source none. A meter without any valid reading up to the
    Run's end flags the ended Run `consumption_gap`; with `silent_meter_falls_back`
    it falls back too.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        quantity: Quantity,
        config: DeviceConfig,
        gap_rates: Callable[[Run], Sequence[tuple[datetime, float | None]]],
        fallback: Callable[[Run], Fallback | None],
        *,
        silent_meter_falls_back: bool = False,
    ) -> None:
        self._hass = hass
        self.quantity = quantity
        self._silent_meter_falls_back = silent_meter_falls_back
        self._per_run = Capability.PER_RUN_METERS in config.capabilities
        self._source: Mapping[str, Any] = config.flow_data[quantity.source_key]
        # Without a source there may be no price section.
        self._price: Mapping[str, Any] = config.flow_data.get(quantity.price_key, {})
        self._gap_rates = gap_rates
        self._fallback_with_source = fallback
        # The price entity's last valid report, for a Run starting while it has none.
        self._last_price: tuple[datetime, float] | None = None

    def timeline(self, run: Run) -> Timeline:
        return run.timelines.setdefault(self.quantity.kind, Timeline())

    def meter(self, run: Run) -> Mapping[str, Any] | None:
        return meter_of(self.quantity, self.timeline(run).source)

    def _fallback_of(self, run: Run) -> Fallback | None:
        """The Run's fallback; None for a Run that started with source none."""
        source = self.timeline(run).source
        if source is not None and source["source"] == NO_SOURCE:
            return None
        return self._fallback_with_source(run)

    def counts(self, run: Run) -> bool:
        """Whether the Run gets a Line Item of the quantity: measured or by its fallback."""
        return self.meter(run) is not None or self._fallback_of(run) is not None

    def meter_entities(self, runs: Iterable[Run]) -> set[str]:
        """The meters of these Runs and of the Device's current source."""
        sections = [self.timeline(run).source for run in runs]
        return {
            meter["entity_id"]
            for section in [*sections, self._source]
            if (meter := meter_of(self.quantity, section))
        }

    def watches(self, run: Run, entity_id: str) -> bool:
        return (meter := self.meter(run)) is not None and meter[
            "entity_id"
        ] == entity_id

    def pin(self, run: Run) -> None:
        """The new Run follows the Device's current source and price."""
        run.timelines[self.quantity.kind] = Timeline(
            source=dict(self._source), cost_source=dict(self._price) or None
        )

    def open(self, run: Run, at: datetime) -> None:
        """Pin the new Run and take the meter's reading and the price at its start."""
        self.pin(run)
        if meter := self.meter(run):
            self.record(run, self._hass.states.get(meter["entity_id"]))
        if self.counts(run):
            self._open_prices(run, at)

    def finish(self, run: Run) -> None:
        """The Run's values are frozen; its timelines are of no more use."""
        timeline = self.timeline(run)
        timeline.readings = []
        timeline.prices = []

    async def async_follow(self, run: Run, now: datetime) -> None:
        """Apply the Device's price to the open Run from `now` on.

        The same price entity as before only catches up on missed reports.
        """
        if not self.counts(run):
            return
        timeline = self.timeline(run)
        price = dict(self._price)
        if timeline.cost_source != price:
            # A Run stored before it had a Cost Source followed this one from start.
            since = run.started if timeline.cost_source is None else now
            timeline.cost_source = price
            add_price(timeline, since, self._current_price())
        elif entity_id := self.price_entity_id:
            since = timeline.prices[-1][0] if timeline.prices else run.started
            for state in await self._async_history(entity_id, since, now):
                self._record_price(timeline, state)
            self._record_price(timeline, self._hass.states.get(entity_id))

    async def async_catch_up(self, run: Run, now: datetime) -> bool:
        """Add the meter reports missed while Coin-op wasn't running; whether it has a meter."""
        if not (meter := self.meter(run)):
            return False
        entity_id = meter["entity_id"]
        readings = self.timeline(run).readings
        since = readings[-1][0] if readings else run.started
        missed = await self._async_history(entity_id, since, now)
        for state in missed:
            self.record(run, state)
        if current := self._hass.states.get(entity_id):
            self.record(run, current)
        segments = self._item(run).segments
        watched = max(
            [
                segments[-1].end if segments else run.started,
                *(state.last_updated for state in missed),
            ]
        )
        if now - watched > OUTAGE:
            add_reading(self.quantity, run, watched, None)
        return True

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

    def record(self, run: Run, state: State | None) -> None:
        """Add the meter's report to the Run's readings and flag gaps and resets."""
        meter = self.meter(run)
        assert meter is not None
        value = meter_reading(self.quantity, state, meter)
        if state is None:
            times = [dt_util.utcnow()]
        elif value is None:
            times = [state.last_updated]
        else:
            times = [state.last_updated, state.last_reported]
        for at in times:
            add_reading(self.quantity, run, at, value, per_run=self._per_run)

    def awaits_report(self, run: Run) -> bool:
        """Whether the meter may still report the ended Run's end."""
        return self.meter(run) is not None and not has_final_report(
            run, self.timeline(run)
        )

    @property
    def price_entity_id(self) -> str | None:
        entity_id: str | None = self._price.get("entity_id")
        return entity_id

    def on_price(self, state: State | None, run: Run | None) -> None:
        """The price entity reported; the open Run, if any, follows it."""
        self.remember_price(state)
        if run is not None:
            self._record_price(self.timeline(run), state)

    def _price_of(self, state: State | None) -> float | None:
        return price_reading(
            self.quantity, state, self._price, self._hass.config.currency
        )

    def _current_price(self) -> float | None:
        if (entity_id := self.price_entity_id) is None:
            return self.quantity.per_unit(self._price["value"])
        return self._price_of(self._hass.states.get(entity_id))

    def price_now(self, run: Run) -> float:
        """The open Run's current unit price: the last valid one it followed."""
        prices = self.timeline(run).prices
        return next((price for _, price in reversed(prices) if price is not None), 0.0)

    def remember_price(self, state: State | None) -> None:
        if state is not None and (price := self._price_of(state)) is not None:
            self._last_price = (self._price_time(state), price)

    def _price_time(self, state: State) -> datetime:
        return input_time(state, self._price.get("attribute"))

    def _record_price(self, timeline: Timeline, state: State | None) -> None:
        """Add the price entity's report to the price timeline."""
        if state is None:
            add_price(timeline, dt_util.utcnow(), None)
        else:
            add_price(timeline, self._price_time(state), self._price_of(state))

    def _open_prices(self, run: Run, at: datetime) -> None:
        """The price at Run start; without one, the last valid price before it."""
        timeline = self.timeline(run)
        if (entity_id := self.price_entity_id) is None:
            add_price(timeline, at, self._current_price())
            return
        state = self._hass.states.get(entity_id)
        if self._price_of(state) is None and self._last_price:
            add_price(timeline, *self._last_price)
        if state is None:
            add_price(timeline, at, None)
        else:
            self._record_price(timeline, state)

    async def async_past_prices(self, run: Run, covered: bool) -> None:
        """A past Run's price timeline from history, flagged where it has none."""
        assert run.ended is not None
        timeline = self.timeline(run)
        if (entity_id := self.price_entity_id) is None:
            add_price(timeline, run.started, self._current_price())
            return
        states = await recorded.async_states(
            self._hass, entity_id, run.started, run.ended
        )
        if not any(self._price_time(state) <= run.started for state in states):
            add_price(timeline, run.started, None)
        for state in states:
            self._record_price(timeline, state)
        if not covered or price_gap(run.started, run.ended, timeline.prices):
            # Without the recorder, the last price it knew may be outdated.
            add_flag(run, Flag.PRICE_GAP)

    async def async_past_readings(self, run: Run, covered: bool) -> bool:
        """A past Run's readings from history; whether history covers it."""
        assert run.ended is not None
        meter = self.meter(run)
        if not (covered and meter):
            return False
        states = await recorded.async_states(
            self._hass, meter["entity_id"], run.started, run.ended
        )
        before = [state for state in states if state.last_updated <= run.started]
        if not before or meter_reading(self.quantity, before[-1], meter) is None:
            return False
        for state in states[len(before) - 1 :]:
            self.record(run, state)
        return True

    def model(self, run: Run) -> Model:
        """The Run's consumption model as measured."""
        return model(
            self.quantity, self.timeline(run), self._gap_rates(run), lambda _, __: 0.0
        )

    def _silent(self, run: Run) -> bool:
        """Whether the meter had no valid reading up to the Run's end."""
        return not any(
            value is not None and (run.ended is None or at <= run.ended)
            for at, value in self.timeline(run).readings
        )

    def priced(
        self, run: Run, until: datetime, model: Model, method: ConsumptionMethod
    ) -> LineItem:
        """The Line Item of what `model` counts from the Run's start to `until`."""
        existing = next(
            (i for i in run.line_items if i.kind is self.quantity.kind), None
        )
        return priced_line_item(
            ulid_now() if existing is None else existing.id,
            self.quantity.kind,
            self.quantity.unit,
            run.started,
            until,
            model,
            self.timeline(run).prices,
            method,
        )

    def refresh(self, run: Run, until: datetime) -> LineItem | None:
        """The Run's live Line Item up to `until`, flagging a price gap; None
        without measurement and fallback."""
        fallback = self._fallback_of(run)
        metered = self.meter(run) is not None
        silent = metered and self._silent(run)
        if silent and run.ended is not None:
            # Open, a per-Run meter may still start at 0; other gaps are flagged as read.
            add_flag(run, Flag.CONSUMPTION_GAP)
        if metered and not (self._silent_meter_falls_back and fallback and silent):
            item = self.priced(run, until, self.model(run), ConsumptionMethod.MEASURED)
        elif fallback:
            item = self._fallen_back(run, until, fallback)
        else:
            return None
        if price_gap(run.started, until, self.timeline(run).prices):
            add_flag(run, Flag.PRICE_GAP)
        return item

    def fallen_back(self, run: Run, until: datetime) -> LineItem | None:
        """The Run's Line Item by the fallback alone; None without one."""
        fallback = self._fallback_of(run)
        return self._fallen_back(run, until, fallback) if fallback else None

    def _fallen_back(self, run: Run, until: datetime, fallback: Fallback) -> LineItem:
        value, method = fallback
        item = self.priced(
            run,
            until,
            value if callable(value) else spread(value or 0.0, run.started, until),
            method,
        )
        if value is None:
            item.quantity, item.segments = None, []
        return item

    def _item(self, run: Run) -> LineItem:
        return next(i for i in run.line_items if i.kind is self.quantity.kind)
