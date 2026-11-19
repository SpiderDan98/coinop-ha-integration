"""Run persistence: ended Runs in the runs Store, open Runs in the live Store."""

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .models import Run

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
LIVE_SAVE_DELAY = timedelta(seconds=60)


def _payload(runs: Iterable[Run]) -> dict[str, Any]:
    return {"runs": [run.as_dict() for run in runs]}


class RunStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._runs = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.runs",
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._live = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.live",
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._live_due: datetime | None = None

    async def async_load(self) -> list[Run]:
        ended = [Run.from_dict(run) for run in await self._load(self._runs)]
        ended_ids = {run.id for run in ended}
        # A crash between finalisation's two writes leaves a Run in both Stores.
        live = [
            Run.from_dict(run)
            for run in await self._load(self._live)
            if run["id"] not in ended_ids
        ]
        return ended + live

    @staticmethod
    async def _load(store: Store[dict[str, Any]]) -> list[dict[str, Any]]:
        data = await store.async_load()
        return [] if data is None else data["runs"]

    def schedule_live_save(self, open_runs: Callable[[], Iterable[Run]]) -> None:
        """Save open Runs about a minute after the first unsaved change."""
        # Store pushes a delayed save back on every call; keep the first deadline
        # so a Run updated every minute is still written.
        if self._live_due is None:
            self._live_due = dt_util.utcnow() + LIVE_SAVE_DELAY

        def payload() -> dict[str, Any]:
            self._live_due = None
            return _payload(open_runs())

        delay = (self._live_due - dt_util.utcnow()).total_seconds()
        self._live.async_delay_save(payload, max(delay, 0))

    async def async_save_live(self, open_runs: Iterable[Run]) -> None:
        self._live_due = None
        await self._live.async_save(_payload(open_runs))

    async def async_save_runs(self, ended_runs: Iterable[Run]) -> None:
        await self._runs.async_save(_payload(ended_runs))
