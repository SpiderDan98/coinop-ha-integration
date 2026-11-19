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


ENDING_TARGETS = frozenset({Target.FINISHED, Target.CANCELLED, Target.ENDED})


@dataclass(frozen=True)
class DeviceConfig:
    device_id: str
    name: str
    printer_device_id: str | None
    status_entity_id: str
    status_attribute: str | None
    mapping: Mapping[str, Target]
    job_entity_id: str | None
    job_attribute: str | None
    thumbnail_entity_id: str | None
    camera_entity_id: str | None
    snapshot: bool
    running_power: float
    paused_power: float | None
    price: float

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> DeviceConfig:
        data: Mapping[str, Any] = subentry.data
        job = data.get("job", {})
        images = data.get("images", {})
        return cls(
            device_id=subentry.subentry_id,
            name=subentry.title,
            printer_device_id=data["printer_device_id"],
            status_entity_id=data["status"]["entity_id"],
            status_attribute=data["status"]["attribute"],
            mapping={
                value: Target(target)
                for target, values in data["mapping"].items()
                for value in values
            },
            job_entity_id=job.get("entity_id"),
            job_attribute=job.get("attribute"),
            thumbnail_entity_id=images.get("thumbnail"),
            camera_entity_id=images.get("camera"),
            snapshot=images.get("snapshot", False),
            running_power=data["consumption"]["running_power"],
            paused_power=data["consumption"]["paused_power"],
            price=data["price"]["value"],
        )

    def target(self, value: str) -> Target:
        return self.mapping.get(value, Target.IGNORED)
