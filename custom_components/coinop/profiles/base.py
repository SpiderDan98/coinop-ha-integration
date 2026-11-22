"""What every Integration Profile and kind check is built from."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from custom_components.coinop.device_config import (
    ConsumptionSource,
    ExpectedEnergyForm,
    Target,
)


class Find(Protocol):
    """The first of the HA device's entities on the platform whose unique id ends in
    (or with `start`, starts with) one of the keys, in the keys' order."""

    def __call__(
        self,
        platform: str,
        /,
        *keys: str,
        start: bool = False,
        disabled: bool = False,
        exclude: str | None = None,
    ) -> str | None: ...

    def linked(self) -> list[Find]:
        """A finder for each linked HA device alone, such as each multi-material
        unit, in the registry's order."""
        ...


class NoDeviceType(Enum):
    """What a kind check answers for an HA device it has no Device Type for."""

    NOT_A_DEVICE = "not_a_device"
    CANT_TELL = "cant_tell"


# Tells an HA device's kind from its entities, its registry entry and its config entry.
KindCheck = Callable[[Find, dr.DeviceEntry, ConfigEntry], str | NoDeviceType]


@dataclass(frozen=True)
class Integration:
    """A known integration: its name, the profile that finds its Device Inputs, the
    Device Types it serves and how it tells which of them an HA device is.
    """

    name: str
    profile: Callable[[Find], dict[str, Any]]
    device_types: tuple[str, ...]
    kind: KindCheck
    # Whether the profile also reads the HA devices linked to the chosen one (a
    # multi-material unit); not where those are Devices of their own (OCPP connectors).
    linked_devices: bool = True


def found(entity: str | list[str] | None, /, **fields: Any) -> dict[str, Any]:
    """The fields of an input, or none if the profile didn't find its entity."""
    return fields if entity else {}


def entity_input(entity_id: str | None, /, **fields: Any) -> dict[str, Any]:
    """An input read from the entity's state, or none if the profile didn't find it."""
    return found(entity_id, entity_id=entity_id, attribute=None, **fields)


def energy_source(entity_id: str | None) -> dict[str, Any]:
    """The electricity source on the entity's energy meter, if the profile found it."""
    return entity_input(entity_id, source=ConsumptionSource.ENERGY.value)


def progress_inputs(remaining: str | None, progress: str | None) -> dict[str, Any]:
    """The progress section's Remaining time and Progress the profile found."""
    return found(remaining, remaining_time=remaining) | found(
        progress, progress=progress
    )


def expected_energy(
    entity_id: str | None, form: ExpectedEnergyForm, attribute: str | None = None
) -> dict[str, Any]:
    """The progress section's Expected energy, if the profile found its entity."""
    return found(
        entity_id,
        expected_energy={
            "entity_id": entity_id,
            "attribute": attribute,
            "form": form.value,
        },
    )


def mapping(**values: list[str]) -> dict[str, list[str]]:
    return {target.value: values.get(target.value, []) for target in Target}


def always(device_type: str) -> KindCheck:
    return lambda *_: device_type
