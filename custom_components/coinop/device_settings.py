"""Panel settings: Coin-op's own per-Device settings, set in the Devices tab.

Each setting is one entry in `FIELDS` (its default and the schema a new value
must pass). Settings of removed Devices are dropped at setup; fields this
version doesn't know are kept as stored.
"""

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from typing import Any

from homeassistant.core import CALLBACK_TYPE

from .device_inputs import stock_scale
from .schema import vol
from .store import CoinOpStore
from .tags import retag, tag_name

TAGS_FOR_NEW_RUNS = "tags_for_new_runs"
AUTOMATIC_TEMPLATES = "automatic_templates"
DEFAULT_MATERIAL = "default_material"
DOSES = "doses"
PROGRAM_DEFAULTS = "program_defaults"


def _unique_ids(doses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len({dose["id"] for dose in doses}) != len(doses):
        raise vol.Invalid("Dose ids must be unique")
    return doses


def _stock_unit(stock: dict[str, Any]) -> dict[str, Any]:
    if stock["attribute"] is not None and stock_scale(stock["unit"]) is None:
        raise vol.Invalid("A stock input's attribute needs a mass or volume unit")
    return stock


# An entity reporting how much of a Dose's Material is left; an attribute has no unit.
_STOCK = vol.All(
    {
        vol.Required("entity_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("attribute", default=None): vol.Any(
            None, vol.All(str, vol.Length(min=1))
        ),
        vol.Optional("unit", default=None): vol.Any(None, str),
    },
    _stock_unit,
)

# A row's amount per Dose id, in its Material's unit; a missing one is not dosed.
_ROW = {
    vol.Required("doses"): {
        str: vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))
    }
}

FIELDS: dict[str, tuple[Any, Any]] = {
    TAGS_FOR_NEW_RUNS: ([], [tag_name]),
    AUTOMATIC_TEMPLATES: ([], vol.All([str], vol.Unique())),
    DEFAULT_MATERIAL: (None, vol.Any(None, str)),
    DOSES: (
        [],
        vol.All(
            [
                {
                    vol.Required("id"): vol.All(str, vol.Length(min=1)),
                    vol.Required("material_id"): str,
                    vol.Optional("stock"): _STOCK,
                }
            ],
            _unique_ids,
        ),
    ),
    PROGRAM_DEFAULTS: ({"default": {"doses": {}}}, {vol.Required("default"): _ROW}),
}


def _drop_removed_doses(settings: dict[str, Any]) -> None:
    """A removed Dose takes its amounts with it."""
    if PROGRAM_DEFAULTS not in settings:
        return
    ids = {dose["id"] for dose in settings.get(DOSES, [])}
    row = settings[PROGRAM_DEFAULTS]["default"]
    row["doses"] = {id_: amount for id_, amount in row["doses"].items() if id_ in ids}


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
        self._listeners: list[Callable[[str], None]] = []

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
        settings = self._devices[device_id] | self.validate(changes)
        _drop_removed_doses(settings)
        self._devices[device_id] = settings
        await self._save()
        for listener in list(self._listeners):
            listener(device_id)
        return self.get(device_id)

    def async_listen(self, listener: Callable[[str], None]) -> CALLBACK_TYPE:
        """Call `listener` with the Device's id after each change of its settings."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

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
