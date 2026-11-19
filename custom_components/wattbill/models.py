"""Runs and Line Items: the records WattBill keeps, free of Home Assistant types.

`as_dict` / `from_dict` give the JSON shape used by the Stores (and their
migrations); values are stored unrounded. Fields a newer minor version added
are kept in `unknown` and written back unchanged.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Flag(StrEnum):
    FAULT = "fault"
    CONSUMPTION_GAP = "consumption_gap"
    METER_RESET = "meter_reset"
    PRICE_GAP = "price_gap"


class LineItemKind(StrEnum):
    ELECTRICITY = "electricity"
    MATERIAL = "material"
    OTHER = "other"


class ElectricityMethod(StrEnum):
    MEASURED = "measured"
    FROM_HISTORY = "from_history"
    ESTIMATED = "estimated"
    ENTERED = "entered"


def _time(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def unknown_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    known = {f.name for f in fields(cls)}
    return {key: value for key, value in data.items() if key not in known}


@dataclass
class PriceSegment:
    """Evidence on the Electricity Line Item: energy used while one price applied."""

    start: datetime
    end: datetime
    kwh: float
    unit_price: float
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "kwh": self.kwh,
            "unit_price": self.unit_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PriceSegment:
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            kwh=data["kwh"],
            unit_price=data["unit_price"],
            unknown=unknown_fields(cls, data),
        )


@dataclass
class LineItem:
    """One cost line: amount = quantity * unit price.

    Computed Line Items keep `label` None and are labelled by their kind in the
    output language. Material Line Items reference their Material by
    `material_id`, which keeps it from being deleted.
    """

    id: str
    kind: LineItemKind
    quantity: float | None
    unit: str
    unit_price: float
    amount: float
    label: str | None = None
    material_id: str | None = None
    method: ElectricityMethod | None = None
    segments: list[PriceSegment] = field(default_factory=list)
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "material_id": self.material_id,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "amount": self.amount,
            "method": self.method,
            "segments": [segment.as_dict() for segment in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineItem:
        return cls(
            id=data["id"],
            kind=LineItemKind(data["kind"]),
            label=data["label"],
            material_id=data.get("material_id"),
            quantity=data["quantity"],
            unit=data["unit"],
            unit_price=data["unit_price"],
            amount=data["amount"],
            method=None
            if data["method"] is None
            else ElectricityMethod(data["method"]),
            segments=[PriceSegment.from_dict(s) for s in data["segments"]],
            unknown=unknown_fields(cls, data),
        )


@dataclass
class Pause:
    start: datetime
    end: datetime | None = None


@dataclass
class Run:
    """One working cycle of a Device.

    Open while `ended` is None; ended but not `finalised` while its last values
    are still awaited; frozen once finalised. `end_reconstructed` marks an end
    WattBill only learnt about after the Status input or WattBill itself was away.
    `job_name` is the job the Device reported, kept apart from the editable name;
    `last_seen` is the last time the Status input was seen during the open Run.
    `consumption` is the Device's consumption section when the Run started;
    `readings` are its meter's (time, kWh or W) reports, None while it had no
    value, kept until finalised. `cost_source` is the Device's price section the
    Run follows; `prices` its (since, price per kWh) timeline, None while the
    price entity had no value, kept until finalised. `average_powers` are the
    (since, running W, paused W) the Run's consumption model used.
    """

    id: str
    device_id: str
    device_name: str
    started: datetime
    line_items: list[LineItem]
    name: str | None = None
    job_name: str | None = None
    last_seen: datetime | None = None
    ended: datetime | None = None
    outcome: Outcome | None = None
    end_reconstructed: bool = False
    finalised: bool = False
    pauses: list[Pause] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    part_count: int = 1
    note: str | None = None
    tags: list[str] = field(default_factory=list)
    consumption: dict[str, Any] | None = None
    readings: list[tuple[datetime, float | None]] = field(default_factory=list)
    cost_source: dict[str, Any] | None = None
    prices: list[tuple[datetime, float | None]] = field(default_factory=list)
    average_powers: list[tuple[datetime, float | None, float | None]] = field(
        default_factory=list
    )
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def electricity(self) -> LineItem:
        return next(i for i in self.line_items if i.kind is LineItemKind.ELECTRICITY)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "name": self.name,
            "job_name": self.job_name,
            "started": self.started.isoformat(),
            "last_seen": _iso(self.last_seen),
            "ended": _iso(self.ended),
            "outcome": self.outcome,
            "end_reconstructed": self.end_reconstructed,
            "finalised": self.finalised,
            "pauses": [
                {"start": pause.start.isoformat(), "end": _iso(pause.end)}
                for pause in self.pauses
            ],
            "flags": list(self.flags),
            "part_count": self.part_count,
            "note": self.note,
            "tags": list(self.tags),
            "consumption": self.consumption,
            "readings": [[at.isoformat(), value] for at, value in self.readings],
            "cost_source": self.cost_source,
            "prices": [[at.isoformat(), price] for at, price in self.prices],
            "average_powers": [
                [at.isoformat(), running, paused]
                for at, running, paused in self.average_powers
            ],
            "line_items": [item.as_dict() for item in self.line_items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        return cls(
            id=data["id"],
            device_id=data["device_id"],
            device_name=data["device_name"],
            name=data["name"],
            job_name=data.get("job_name"),
            started=datetime.fromisoformat(data["started"]),
            last_seen=_time(data.get("last_seen")),
            ended=_time(data["ended"]),
            outcome=None if data["outcome"] is None else Outcome(data["outcome"]),
            end_reconstructed=data.get("end_reconstructed", False),
            finalised=data["finalised"],
            pauses=[
                Pause(datetime.fromisoformat(p["start"]), _time(p["end"]))
                for p in data["pauses"]
            ],
            flags=list(data["flags"]),
            part_count=data["part_count"],
            note=data.get("note"),
            tags=list(data.get("tags", [])),
            consumption=data.get("consumption"),
            readings=[
                (datetime.fromisoformat(at), value)
                for at, value in data.get("readings", [])
            ],
            cost_source=data.get("cost_source"),
            prices=[
                (datetime.fromisoformat(at), price)
                for at, price in data.get("prices", [])
            ],
            average_powers=[
                (datetime.fromisoformat(at), running, paused)
                for at, running, paused in data.get("average_powers", [])
            ],
            line_items=[LineItem.from_dict(item) for item in data["line_items"]],
            unknown=unknown_fields(cls, data),
        )
