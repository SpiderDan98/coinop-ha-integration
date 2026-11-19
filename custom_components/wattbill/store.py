"""Run persistence: ended Runs in the runs Store, open Runs in the live Store."""

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import Run

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
LIVE_SAVE_DELAY = 60


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
        self._live.async_delay_save(lambda: _payload(open_runs()), LIVE_SAVE_DELAY)

    async def async_save_live(self, open_runs: Iterable[Run]) -> None:
        await self._live.async_save(_payload(open_runs))

    async def async_save_runs(self, ended_runs: Iterable[Run]) -> None:
        await self._runs.async_save(_payload(ended_runs))
