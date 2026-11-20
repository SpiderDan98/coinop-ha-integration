"""Coin-op's Stores and file folder, checked, migrated and removed together.

Every Store is registered in `SCHEMAS`; the missing-data check, the `.bak`
copy before a major migration and uninstall then cover it.

Schema versions: a minor version only adds fields (read them with a default;
older code keeps fields it doesn't know), a major version breaks the shape and
registers a migration from the major before it. Migrations only reshape and
fill defaults, never recompute frozen values.
"""

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, UnsupportedStorageVersionError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .models import Run

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
LIVE_SAVE_DELAY = timedelta(seconds=60)

# Hub entry data: the Stores Coin-op has written, so a missing one is noticed.
CONF_STORES = "stores"
ISSUE_DATA_MISSING = "data_missing"
ISSUE_DATA_CORRUPT = "data_corrupt"


@dataclass(frozen=True)
class Schema:
    version: int
    minor_version: int
    empty: dict[str, Any]
    # Major version N -> turns data of version N into version N + 1.
    migrations: Mapping[int, Callable[[dict[str, Any]], dict[str, Any]]] = field(
        default_factory=dict
    )


RUNS_SCHEMA = Schema(STORAGE_VERSION, STORAGE_MINOR_VERSION, {"runs": []})
SCHEMAS = {
    "catalog": Schema(1, 1, {"materials": [], "tags": [], "templates": []}),
    "runs": RUNS_SCHEMA,
    "live": RUNS_SCHEMA,
    "device_settings": Schema(1, 1, {"devices": {}}),
}


def files_path(hass: HomeAssistant) -> Path:
    """Coin-op's folder for files (images) in the HA config directory."""
    return Path(hass.config.path(DOMAIN))


class CoinOpStore(Store[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.schema = SCHEMAS[name]
        super().__init__(
            hass,
            self.schema.version,
            f"{DOMAIN}.{name}",
            atomic_writes=True,
            minor_version=self.schema.minor_version,
        )

    def bak(self, version: int = 1, minor_version: int = 1) -> Store[dict[str, Any]]:
        """The copy kept from before the latest major migration."""
        return Store(self.hass, version, f"{self.key}.bak", minor_version=minor_version)

    @override
    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: Any
    ) -> dict[str, Any]:
        if old_major_version == self.version:
            return dict(old_data)
        await self.bak(old_major_version, old_minor_version).async_save(old_data)
        data: dict[str, Any] = old_data
        for version in range(old_major_version, self.version):
            data = self.schema.migrations[version](data)
        return data


class CoinOpStores:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._stores = {name: CoinOpStore(hass, name) for name in SCHEMAS}

    def __getitem__(self, name: str) -> CoinOpStore:
        return self._stores[name]

    async def async_load(self, entry: ConfigEntry) -> dict[str, dict[str, Any]]:
        """Load every Store; fail without writing if stored data is missing or newer."""
        try:
            loaded = {
                name: await store.async_load() for name, store in self._stores.items()
            }
        except UnsupportedStorageVersionError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="data_too_new",
                translation_placeholders={"store": err.storage_key},
            ) from err
        recorded = entry.data.get(CONF_STORES, [])
        if missing := [
            self._stores[name].key
            for name in recorded
            if name in loaded and loaded[name] is None
        ]:
            placeholders = {"stores": ", ".join(missing)}
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                ISSUE_DATA_MISSING,
                is_fixable=True,
                severity=ir.IssueSeverity.CRITICAL,
                translation_key=ISSUE_DATA_MISSING,
                translation_placeholders=placeholders,
            )
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key=ISSUE_DATA_MISSING,
                translation_placeholders=placeholders,
            )
        ir.async_delete_issue(self._hass, DOMAIN, ISSUE_DATA_MISSING)
        ir.async_delete_issue(self._hass, DOMAIN, ISSUE_DATA_CORRUPT)

        data = {}
        for name, store in self._stores.items():
            if (stored := loaded[name]) is None:
                stored = deepcopy(store.schema.empty)
                await store.async_save(stored)
            data[name] = stored
        if set(recorded) != set(self._stores):
            self._hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_STORES: list(self._stores)}
            )
        return data

    def parse[T](
        self,
        data: Mapping[str, dict[str, Any]],
        name: str,
        parse: Callable[[dict[str, Any]], T],
    ) -> T:
        """Read a Store's data; data of another shape stops setup with a repair issue."""
        try:
            return parse(data[name])
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            placeholders = {"store": self._stores[name].key}
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                ISSUE_DATA_CORRUPT,
                is_fixable=False,
                severity=ir.IssueSeverity.CRITICAL,
                translation_key=ISSUE_DATA_CORRUPT,
                translation_placeholders=placeholders,
            )
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key=ISSUE_DATA_CORRUPT,
                translation_placeholders=placeholders,
            ) from err

    async def async_remove(self) -> None:
        """Delete every Store, its `.bak` copy and the file folder."""
        for store in self._stores.values():
            await store.async_remove()
            await store.bak().async_remove()
        await self._hass.async_add_executor_job(
            shutil.rmtree, files_path(self._hass), True
        )


def async_start_fresh(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Accept missing Stores: the next setup starts them empty."""
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_STORES: []})


def _payload(runs: Iterable[Run]) -> dict[str, Any]:
    return {"runs": [run.as_dict() for run in runs]}


def _runs(data: dict[str, Any]) -> list[Run]:
    return [Run.from_dict(run) for run in data["runs"]]


class RunStore:
    """Ended Runs in the runs Store, open Runs in the live Store."""

    def __init__(self, stores: CoinOpStores) -> None:
        self._stores = stores
        self._runs = stores["runs"]
        self._live = stores["live"]
        self._live_due: datetime | None = None

    def runs(self, data: Mapping[str, dict[str, Any]]) -> list[Run]:
        ended = self._stores.parse(data, "runs", _runs)
        ended_ids = {run.id for run in ended}
        live = self._stores.parse(data, "live", _runs)
        # A crash between finalisation's two writes leaves a Run in both Stores.
        return ended + [run for run in live if run.id not in ended_ids]

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
