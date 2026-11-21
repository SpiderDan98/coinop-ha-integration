"""A Device's settings as written by the Add Device flow into its subentry."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigSubentry

from .const import (
    DEVICE_TYPE_3D_PRINTER,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_WASHING_MACHINE,
)


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
    PER_PROGRAM = "per_program"


class WaterSource(StrEnum):
    METER = "meter"
    FLOW = "flow"
    PER_PROGRAM = "per_program"
    NONE = "none"


class Capability(StrEnum):
    """What a Device Type has; code branches on these, not on the type."""

    # The job name, Material used, Slots and Loaded slot inputs.
    JOB = "job"
    # Thumbnail, Camera and Snapshot.
    IMAGES = "images"
    # A Material Line Item on every Run, a default Material and the grams used.
    MATERIAL = "material"
    PART_COUNT = "part_count"
    # Electricity estimated from average powers when nothing measures it.
    AVERAGE_POWER = "average_power"
    # The Program input; a Run records its Program.
    PROGRAM = "program"
    # A Dose list whose Program Defaults become Material Line Items.
    DOSES = "doses"
    # A water source and price, and a Water Line Item from them.
    WATER = "water"
    # Electricity and water from the Program Defaults' kWh and litres when not measured.
    PROGRAM_CONSUMPTION = "program_consumption"
    # Meters may count each Run from 0, such as per-cycle counters: a drop after
    # the end is no reset.
    PER_RUN_METERS = "per_run_meters"


# Every Device Type, in the order Add Device lists them.
CAPABILITIES = {
    DEVICE_TYPE_3D_PRINTER: frozenset(
        {
            Capability.JOB,
            Capability.IMAGES,
            Capability.MATERIAL,
            Capability.PART_COUNT,
            Capability.AVERAGE_POWER,
        }
    ),
    DEVICE_TYPE_WASHING_MACHINE: frozenset(
        {
            Capability.PROGRAM,
            Capability.DOSES,
            Capability.WATER,
            Capability.PROGRAM_CONSUMPTION,
            Capability.PER_RUN_METERS,
        }
    ),
    DEVICE_TYPE_DISHWASHER: frozenset(
        {
            Capability.PROGRAM,
            Capability.DOSES,
            Capability.WATER,
            Capability.PROGRAM_CONSUMPTION,
            Capability.PER_RUN_METERS,
        }
    ),
}

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
    program_entity_id: str | None
    program_attribute: str | None
    # Values the Program input reports while it knows no Program.
    program_ignored: frozenset[str]
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
        program = data.get("program", {})
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
            program_entity_id=program.get("entity_id"),
            program_attribute=program.get("attribute"),
            program_ignored=frozenset(program.get("ignored", ())),
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

    @property
    def capabilities(self) -> frozenset[Capability]:
        return CAPABILITIES[self.device_type]

    def target(self, value: str) -> Target:
        return self.mapping.get(value, Target.IGNORED)

    def program(self, value: str | None) -> str | None:
        """The Program a Program input value names, trimmed; None if blank or ignored."""
        program = (value or "").strip()
        return program if program and program not in self.program_ignored else None
