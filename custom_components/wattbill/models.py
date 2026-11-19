"""Runs and Line Items: the records WattBill keeps, free of Home Assistant types.

`as_dict` / `from_dict` give the JSON shape used by the Stores (and their
migrations); values are stored unrounded.
"""

from dataclasses import dataclass, field
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


@dataclass
class PriceSegment:
    """Evidence on the Electricity Line Item: energy used while one price applied."""

    start: datetime
    end: datetime
    kwh: float
    unit_price: float

    def as_dict(self) -> dict[str, Any]:
        return {
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
        )


@dataclass
class LineItem:
    """One cost line: amount = quantity * unit price.

    Computed Line Items keep `label` None and are labelled by their kind in the
    output language.
    """

    id: str
    kind: LineItemKind
    quantity: float | None
    unit: str
    unit_price: float
    amount: float
    label: str | None = None
    method: ElectricityMethod | None = None
    segments: list[PriceSegment] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
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
            quantity=data["quantity"],
            unit=data["unit"],
            unit_price=data["unit_price"],
            amount=data["amount"],
            method=None
            if data["method"] is None
            else ElectricityMethod(data["method"]),
            segments=[PriceSegment.from_dict(s) for s in data["segments"]],
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
    """

    id: str
    device_id: str
    device_name: str
    started: datetime
    line_items: list[LineItem]
    name: str | None = None
    ended: datetime | None = None
    outcome: Outcome | None = None
    end_reconstructed: bool = False
    finalised: bool = False
    pauses: list[Pause] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def electricity(self) -> LineItem:
        return next(i for i in self.line_items if i.kind is LineItemKind.ELECTRICITY)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "name": self.name,
            "started": self.started.isoformat(),
            "ended": _iso(self.ended),
            "outcome": self.outcome,
            "end_reconstructed": self.end_reconstructed,
            "finalised": self.finalised,
            "pauses": [
                {"start": pause.start.isoformat(), "end": _iso(pause.end)}
                for pause in self.pauses
            ],
            "flags": list(self.flags),
            "line_items": [item.as_dict() for item in self.line_items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        return cls(
            id=data["id"],
            device_id=data["device_id"],
            device_name=data["device_name"],
            name=data["name"],
            started=datetime.fromisoformat(data["started"]),
            ended=_time(data["ended"]),
            outcome=None if data["outcome"] is None else Outcome(data["outcome"]),
            end_reconstructed=data.get("end_reconstructed", False),
            finalised=data["finalised"],
            pauses=[
                Pause(datetime.fromisoformat(p["start"]), _time(p["end"]))
                for p in data["pauses"]
            ],
            flags=list(data["flags"]),
            line_items=[LineItem.from_dict(item) for item in data["line_items"]],
        )
