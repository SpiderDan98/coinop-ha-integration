"""A Device's settings as written by the Add Device flow into its subentry."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigSubentry


class Target(StrEnum):
    """What a value of the Status input means for the Run lifecycle."""

    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    ENDED = "ended"
    FAULT = "fault"
    IGNORED = "ignored"


class ConsumptionSource(StrEnum):
    ENERGY = "energy"
    POWER = "power"
    ESTIMATE = "estimate"


ENDING_TARGETS = frozenset({Target.FINISHED, Target.CANCELLED, Target.ENDED})


@dataclass(frozen=True)
class DeviceConfig:
    device_id: str
    name: str
    status_entity_id: str
    status_attribute: str | None
    mapping: Mapping[str, Target]
    source: ConsumptionSource
    meter_entity_id: str | None
    meter_attribute: str | None
    meter_unit: str | None
    meter_factor: float | None
    running_power: float | None
    paused_power: float | None
    price: float

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> DeviceConfig:
        data: Mapping[str, Any] = subentry.data
        consumption = data["consumption"]
        return cls(
            device_id=subentry.subentry_id,
            name=subentry.title,
            status_entity_id=data["status"]["entity_id"],
            status_attribute=data["status"]["attribute"],
            mapping={
                value: Target(target)
                for target, values in data["mapping"].items()
                for value in values
            },
            source=ConsumptionSource(consumption["source"]),
            meter_entity_id=consumption.get("entity_id"),
            meter_attribute=consumption.get("attribute"),
            meter_unit=consumption.get("unit"),
            meter_factor=consumption.get("factor"),
            running_power=consumption.get("running_power"),
            paused_power=consumption.get("paused_power"),
            price=data["price"]["value"],
        )

    def target(self, value: str) -> Target:
        return self.mapping.get(value, Target.IGNORED)
