"""Slot attribution: which Material each loaded Slot held, and its share of running time."""

from collections.abc import Iterable
from datetime import datetime

from custom_components.coinop.cost.running_time import running_between
from custom_components.coinop.materials import Material
from custom_components.coinop.models import LoadedSlot, Pause, SlotReport


def slot_shares(
    loaded: list[LoadedSlot], pauses: Iterable[Pause], until: datetime
) -> dict[SlotReport, float]:
    """Each Slot report loaded during the Run with its share of the running time.

    Slots loaded only while paused get none; without any running time every
    loaded Slot counts the same.
    """
    pauses = list(pauses)
    seconds: dict[SlotReport, float] = {}
    ends = [*(following.since for following in loaded[1:]), until]
    for entry, end in zip(loaded, ends, strict=False):
        if entry.slot is None:
            continue
        end = min(end, until)
        running = running_between(entry.since, end, pauses).total_seconds()
        seconds[entry.slot] = seconds.get(entry.slot, 0.0) + running
    total = sum(seconds.values())
    if not total:
        return {slot: 1 / len(seconds) for slot in seconds}
    return {slot: running / total for slot, running in seconds.items() if running}


def slot_material(slot: SlotReport, materials: Iterable[Material]) -> Material | None:
    """The Material of the reported type and colour, else the type's default."""
    of_type = [
        material
        for material in materials
        if not material.archived
        and material.type.strip().casefold() == slot.type.strip().casefold()
    ]
    return next(
        (m for m in of_type if slot.colour and m.colour == slot.colour),
        next((m for m in of_type if m.default_for_type), None),
    )
