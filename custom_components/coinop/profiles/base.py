"""What every Integration Profile and kind check is built from."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from custom_components.coinop.device_config import Target

# `disabled=True` also finds a disabled entity: a kind check reads what is registered.
# `exclude` passes over unique ids that end in it, such as a longer key ending alike.
Find = Callable[..., str | None]


class NoDeviceType(Enum):
    """What a kind check answers for an HA device it has no Device Type for."""

    NOT_A_DEVICE = "not_a_device"
    CANT_TELL = "cant_tell"


# Tells an HA device's kind from its entities, its registry entry and its config entry.
KindCheck = Callable[[Find, dr.DeviceEntry, ConfigEntry], str | NoDeviceType]


@dataclass(frozen=True)
class Integration:
    """A known integration: its name, the profile that finds its Device Inputs, the
    Device Types it serves and how it tells which of them an HA device is."""

    name: str
    profile: Callable[[Find], dict[str, Any]]
    device_types: tuple[str, ...]
    kind: KindCheck


def found(entity: str | list[str] | None, /, **fields: Any) -> dict[str, Any]:
    """The fields of an input, or none if the profile didn't find its entity."""
    return fields if entity else {}


def mapping(**values: list[str]) -> dict[str, list[str]]:
    return {target.value: values.get(target.value, []) for target in Target}


def always(device_type: str) -> KindCheck:
    return lambda *_: device_type
