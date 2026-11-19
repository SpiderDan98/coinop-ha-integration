"""The Run book: every Run in memory, persisted, totalled and announced.

All changes to Runs go through here, so Stores, per-Device totals and
listeners (sensors, events, panel subscriptions) never disagree.
"""

from collections import defaultdict
from collections.abc import Callable
from enum import StrEnum

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.util import dt as dt_util

from .cost.totals import DeviceTotals, Totals
from .models import Run
from .store import RunStore


class RunChange(StrEnum):
    STARTED = "started"
    UPDATED = "updated"
    ENDED = "ended"


class RunBook:
    def __init__(self, store: RunStore, runs: list[Run]) -> None:
        self._store = store
        self._runs = {run.id: run for run in runs}
        self._totals: defaultdict[str, DeviceTotals] = defaultdict(DeviceTotals)
        for run in runs:
            self._totals[run.device_id].apply(run, dt_util.utcnow())
        self._listeners: list[Callable[[RunChange, Run], None]] = []

    def runs(self) -> list[Run]:
        return list(self._runs.values())

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def open_run(self, device_id: str) -> Run | None:
        return next(
            (
                run
                for run in self._runs.values()
                if run.device_id == device_id and run.ended is None
            ),
            None,
        )

    def totals(self, device_id: str) -> Totals:
        return self._totals[device_id].sum

    @callback
    def async_listen(self, listener: Callable[[RunChange, Run], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def async_start(self, run: Run) -> None:
        self._runs[run.id] = run
        self._changed(RunChange.STARTED, run)

    @callback
    def async_update(self, run: Run) -> None:
        """Record new provisional values of an unfinalised Run."""
        self._changed(RunChange.UPDATED, run)

    async def async_finalise(self, run: Run) -> None:
        """Freeze the Run: written to runs first, then dropped from live."""
        run.finalised = True
        await self._store.async_save_runs(r for r in self.runs() if r.finalised)
        await self._store.async_save_live(self._unfinalised())
        self._announce(RunChange.ENDED, run)

    async def async_edit(self, run: Run) -> None:
        """Record a change to a Run in either state, e.g. a new image."""
        if run.finalised:
            await self._store.async_save_runs(r for r in self.runs() if r.finalised)
            self._announce(RunChange.UPDATED, run)
        else:
            self._changed(RunChange.UPDATED, run)

    async def async_rename_device(self, device_id: str, name: str) -> None:
        """Keep every Run's Device name current, so removed Devices keep their last one."""
        renamed = [
            run
            for run in self._runs.values()
            if run.device_id == device_id and run.device_name != name
        ]
        for run in renamed:
            run.device_name = name
        if any(run.finalised for run in renamed):
            await self._store.async_save_runs(r for r in self.runs() if r.finalised)
        if not all(run.finalised for run in renamed):
            await self.async_flush()

    async def async_flush(self) -> None:
        """Write pending live changes now, e.g. before unloading."""
        await self._store.async_save_live(self._unfinalised())

    def _unfinalised(self) -> list[Run]:
        return [run for run in self._runs.values() if not run.finalised]

    def _changed(self, change: RunChange, run: Run) -> None:
        self._store.schedule_live_save(self._unfinalised)
        self._announce(change, run)

    def _announce(self, change: RunChange, run: Run) -> None:
        """Move the Device's totals by this Run's delta, then tell listeners.

        Any kind of change works: a Run no longer in the book leaves the totals.
        """
        totals = self._totals[run.device_id]
        if run.id in self._runs:
            totals.apply(run, dt_util.utcnow())
        else:
            totals.remove(run.id)
        for listener in list(self._listeners):
            listener(change, run)
