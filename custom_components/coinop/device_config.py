"""A Device's settings as written by the Add Device flow into its subentry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigSubentry

from .const import (
    DEVICE_TYPE_3D_PRINTER,
    DEVICE_TYPE_COFFEE_MACHINE,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_EV_CHARGER,
    DEVICE_TYPE_OTHER,
    DEVICE_TYPE_OVEN,
    DEVICE_TYPE_ROBOTIC_MOWER,
    DEVICE_TYPE_TUMBLE_DRYER,
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


NO_SOURCE = "none"


class ConsumptionSource(StrEnum):
    ENERGY = "energy"
    POWER = "power"
    ESTIMATE = "estimate"
    PER_PROGRAM = "per_program"
    NONE = NO_SOURCE


class WaterSource(StrEnum):
    METER = "meter"
    FLOW = "flow"
    PER_PROGRAM = "per_program"
    NONE = NO_SOURCE


class Capability(StrEnum):
    """What a Device can have; code branches on these, not on the Device Type."""

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


# What each shipped Device Type has, in the order Add Device lists them.
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
    DEVICE_TYPE_TUMBLE_DRYER: frozenset(
        {
            Capability.PROGRAM,
            Capability.DOSES,
            Capability.PROGRAM_CONSUMPTION,
            Capability.PER_RUN_METERS,
        }
    ),
    DEVICE_TYPE_COFFEE_MACHINE: frozenset(
        {
            Capability.PROGRAM,
            Capability.DOSES,
            Capability.WATER,
            Capability.PROGRAM_CONSUMPTION,
            Capability.PER_RUN_METERS,
        }
    ),
    DEVICE_TYPE_OVEN: frozenset(
        {
            Capability.PROGRAM,
            Capability.PROGRAM_CONSUMPTION,
            Capability.PER_RUN_METERS,
        }
    ),
    # A session energy sensor starts each charging session from 0.
    DEVICE_TYPE_EV_CHARGER: frozenset({Capability.PER_RUN_METERS}),
    DEVICE_TYPE_ROBOTIC_MOWER: frozenset[Capability](),
}

# Every Device Type, in the order Add Device lists them. Other has no set here: each
# of its Devices stores its own (ADR 0009).
DEVICE_TYPES = (*CAPABILITIES, DEVICE_TYPE_OTHER)

# The subentry keys that say what kind of Device it is; the others are its sections.
# Only an Other Device stores the last two.
TYPE_KEYS = frozenset({"device_type", "type_name", "capabilities"})

# What an Other Device can have, in the order its step offers the choices, and the
# Capabilities each choice brings.
CHOICES = {
    "program": frozenset({Capability.PROGRAM, Capability.PROGRAM_CONSUMPTION}),
    "water": frozenset({Capability.WATER}),
    "images": frozenset({Capability.IMAGES}),
    "part_count": frozenset({Capability.PART_COUNT}),
    "per_run_meters": frozenset({Capability.PER_RUN_METERS}),
}


def picks_capabilities(device_type: str) -> bool:
    """Whether the user picks what a Device of the type has, as no set is shipped."""
    return device_type not in CAPABILITIES


def chosen_capabilities(choices: Iterable[str]) -> frozenset[Capability]:
    """What an Other Device with these of `CHOICES` has."""
    capabilities = frozenset[Capability]().union(*(CHOICES[c] for c in choices))
    if Capability.PROGRAM_CONSUMPTION in capabilities:
        return capabilities
    # Without a Program's kWh, unmeasured electricity is estimated from average powers.
    return capabilities | {Capability.AVERAGE_POWER}


def capabilities_of(data: Mapping[str, Any]) -> frozenset[Capability]:
    """What the Device with this subentry data has: its Device Type's shipped set, or
    the one stored with an Other Device."""
    shipped = CAPABILITIES.get(data["device_type"])
    if shipped is not None:
        return shipped
    return frozenset(Capability(name) for name in data["capabilities"])


ENDING_TARGETS = frozenset({Target.FINISHED, Target.CANCELLED, Target.ENDED})


@dataclass(frozen=True)
class DeviceConfig:
    device_id: str
    name: str
    device_type: str
    # The heading an Other Device is listed under; None for a shipped Device Type.
    type_name: str | None
    capabilities: frozenset[Capability]
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
            type_name=data.get("type_name"),
            capabilities=capabilities_of(data),
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

    def target(self, value: str) -> Target:
        return self.mapping.get(value, Target.IGNORED)

    def program(self, value: str | None) -> str | None:
        """The Program a Program input value names, trimmed; None if blank or ignored."""
        program = (value or "").strip()
        return program if program and program not in self.program_ignored else None
