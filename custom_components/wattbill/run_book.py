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
from .tags import retag


class RunChange(StrEnum):
    STARTED = "started"
    UPDATED = "updated"
    ENDED = "ended"
    DELETED = "deleted"


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

    def run(self, run_id: str) -> Run | None:
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

    def uses_material(self, material_id: str) -> bool:
        return any(
            item.material_id == material_id
            for run in self._runs.values()
            for item in run.line_items
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

    async def async_correct(self, run: Run) -> None:
        """Save a change outside the lifecycle (a correction, an image); announces UPDATED."""
        await self._save(run)
        self._announce(RunChange.UPDATED, run)

    async def async_delete(self, runs: list[Run]) -> None:
        """Remove Runs for good; listeners hear DELETED, e.g. to delete their files."""
        for run in runs:
            del self._runs[run.id]
        await self._store.async_save_runs(r for r in self.runs() if r.finalised)
        if not all(run.finalised for run in runs):
            await self.async_flush()
        for run in runs:
            self._announce(RunChange.DELETED, run)

    async def async_rename_device(self, device_id: str, name: str) -> None:
        """Keep every Run's Device name current, so removed Devices keep their last one."""
        renamed = [
            run
            for run in self._runs.values()
            if run.device_id == device_id and run.device_name != name
        ]
        for run in renamed:
            run.device_name = name
        await self._save(*renamed)

    async def async_retag(self, tag: str, new: str | None) -> None:
        """Replace `tag` by `new` on every Run carrying it, or remove it when None."""
        tagged = [run for run in self._runs.values() if tag in run.tags]
        for run in tagged:
            run.tags = retag(run.tags, tag, new)
        await self._save(*tagged)
        for run in tagged:
            self._announce(RunChange.UPDATED, run)

    async def async_flush(self) -> None:
        """Write pending live changes now, e.g. before unloading."""
        await self._store.async_save_live(self._unfinalised())

    async def _save(self, *runs: Run) -> None:
        if any(run.finalised for run in runs):
            await self._store.async_save_runs(r for r in self.runs() if r.finalised)
        if not all(run.finalised for run in runs):
            await self.async_flush()

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
