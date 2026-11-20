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
    device_type: str
    printer_device_id: str | None
    status_entity_id: str
    status_attribute: str | None
    mapping: Mapping[str, Target]
    job_entity_id: str | None
    job_attribute: str | None
    # The Material used input: entity_id, attribute and unit.
    material: Mapping[str, Any] | None
    # The Slot entities in Slot order, their colour attribute and the Loaded slot input.
    slots: tuple[str, ...]
    colour_attribute: str | None
    loaded_slot_entity_id: str | None
    thumbnail_entity_id: str | None
    camera_entity_id: str | None
    snapshot: bool
    # The consumption section as Add Device wrote it.
    consumption: Mapping[str, Any]
    # The subentry data as the flow wrote it: the Device's HA-side settings.
    flow_data: Mapping[str, Any]

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> DeviceConfig:
        data: Mapping[str, Any] = subentry.data
        job = data.get("job", {})
        images = data.get("images", {})
        return cls(
            device_id=subentry.subentry_id,
            name=subentry.title,
            device_type=data["device_type"],
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
            material=job.get("material"),
            slots=tuple(job.get("slots", ())),
            colour_attribute=job.get("colour_attribute"),
            loaded_slot_entity_id=job.get("loaded_slot"),
            thumbnail_entity_id=images.get("thumbnail"),
            camera_entity_id=images.get("camera"),
            snapshot=images.get("snapshot", False),
            consumption=data["consumption"],
            flow_data=data,
        )

    def target(self, value: str) -> Target:
        return self.mapping.get(value, Target.IGNORED)
