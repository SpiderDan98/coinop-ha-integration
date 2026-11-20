"""Panel settings: Coin-op's own per-Device settings, set in the Devices tab.

Each setting is one entry in `FIELDS` (its default and the schema a new value
must pass). Settings of removed Devices are dropped at setup; fields this
version doesn't know are kept as stored.
"""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from .schema import vol
from .store import CoinOpStore
from .tags import retag, tag_name

TAGS_FOR_NEW_RUNS = "tags_for_new_runs"
AUTOMATIC_TEMPLATES = "automatic_templates"
DEFAULT_MATERIAL = "default_material"

FIELDS: dict[str, tuple[Any, Any]] = {
    TAGS_FOR_NEW_RUNS: ([], [tag_name]),
    AUTOMATIC_TEMPLATES: ([], vol.All([str], vol.Unique())),
    DEFAULT_MATERIAL: (None, vol.Any(None, str)),
}


class DeviceSettings:
    def __init__(
        self,
        store: CoinOpStore,
        data: Mapping[str, Any],
        device_ids: Iterable[str],
    ) -> None:
        self._store = store
        stored: dict[str, dict[str, Any]] = data["devices"]
        self._devices = {
            device_id: stored.get(device_id, {}) for device_id in device_ids
        }
        self._removed = stored.keys() - self._devices.keys()

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices

    def get(self, device_id: str) -> dict[str, Any]:
        stored = self._devices[device_id]
        return {
            name: deepcopy(stored.get(name, default))
            for name, (default, _) in FIELDS.items()
        }

    @staticmethod
    def validate(changes: Mapping[str, Any]) -> dict[str, Any]:
        """`changes` as stored; raises `vol.Invalid` for an unknown field or value."""
        valid: dict[str, Any] = vol.Schema(
            {vol.Optional(name): schema for name, (_, schema) in FIELDS.items()}
        )(dict(changes))
        return valid

    async def async_update(
        self, device_id: str, changes: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Apply `changes` (raises `vol.Invalid` for an unknown field or value)."""
        self._devices[device_id] = self._devices[device_id] | self.validate(changes)
        await self._save()
        return self.get(device_id)

    async def async_retag(self, tag: str, new: str | None) -> None:
        """Replace `tag` by `new` in every Device's Tags for new Runs, or remove it."""
        tagged = [
            settings
            for settings in self._devices.values()
            if tag in settings.get(TAGS_FOR_NEW_RUNS, [])
        ]
        for settings in tagged:
            settings[TAGS_FOR_NEW_RUNS] = retag(settings[TAGS_FOR_NEW_RUNS], tag, new)
        if tagged:
            await self._save()

    async def async_drop_template(self, template_id: str) -> None:
        """Take a deleted template out of every Device's automatic templates."""
        using = [
            settings
            for settings in self._devices.values()
            if template_id in settings.get(AUTOMATIC_TEMPLATES, [])
        ]
        for settings in using:
            settings[AUTOMATIC_TEMPLATES].remove(template_id)
        if using:
            await self._save()

    async def async_prune(self) -> None:
        """Drop removed Devices' settings from the Store."""
        if self._removed:
            await self._save()

    async def _save(self) -> None:
        self._removed = set()
        await self._store.async_save(
            {
                "devices": {
                    device_id: settings
                    for device_id, settings in self._devices.items()
                    if settings
                }
            }
        )
