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
    USAGE_MISSING = "usage_missing"
    MATERIAL_MISSING = "material_missing"


class UsageUnit(StrEnum):
    """A Material used input reports a length (kept in mm) or a mass (in g)."""

    MILLIMETRE = "mm"
    GRAM = "g"


class LineItemKind(StrEnum):
    ELECTRICITY = "electricity"
    MATERIAL = "material"
    OTHER = "other"


class QuantityBasis(StrEnum):
    """Where a Line Item Template's quantity comes from."""

    ENTERED = "entered"
    RUNNING_HOURS = "running_hours"


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
class MaterialCopy:
    """Evidence on a Material Line Item: its Material as it was when priced."""

    name: str
    type: str
    density: float
    diameter: float | None
    price_per_gram: float
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "name": self.name,
            "type": self.type,
            "density": self.density,
            "diameter": self.diameter,
            "price_per_gram": self.price_per_gram,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaterialCopy:
        return cls(
            name=data["name"],
            type=data["type"],
            density=data["density"],
            diameter=data["diameter"],
            price_per_gram=data["price_per_gram"],
            unknown=unknown_fields(cls, data),
        )


@dataclass
class Usage:
    """The Material used input's last valid report during a Run, in mm or g.

    `at` is when it was last reported, which may be after the Run ended.
    """

    at: datetime
    value: float
    unit: UsageUnit

    def as_dict(self) -> dict[str, Any]:
        return {"at": self.at.isoformat(), "value": self.value, "unit": self.unit}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Usage:
        return cls(
            datetime.fromisoformat(data["at"]), data["value"], UsageUnit(data["unit"])
        )


VALUES = ("quantity", "unit_price", "amount")


@dataclass
class LineItem:
    """One cost line: amount = quantity * unit price.

    Computed Line Items keep `label` None and are labelled by their kind in the
    output language. Material Line Items reference their Material by
    `material_id`, which keeps it from being deleted, and keep a copy of it in
    `material`; their unit is g or ml. A `measured` one follows the Material used
    input, whose length (mm) it keeps. A Line Item copied from a Line Item
    Template keeps only `template_id` as its origin and the template's `basis`;
    with running hours WattBill computes its quantity. Quantity, unit price and
    amount are what counts; once the user overrides a computed one, `computed`
    keeps what WattBill computed.
    """

    id: str
    kind: LineItemKind
    quantity: float | None
    unit: str
    unit_price: float
    amount: float
    label: str | None = None
    material_id: str | None = None
    material: MaterialCopy | None = None
    measured: bool = False
    length: float | None = None
    template_id: str | None = None
    basis: QuantityBasis | None = None
    method: ElectricityMethod | None = None
    segments: list[PriceSegment] = field(default_factory=list)
    computed: dict[str, float | None] | None = None
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_computed(self) -> bool:
        """WattBill computes its values, live while the Run is open."""
        return (
            self.kind is LineItemKind.ELECTRICITY
            or self.measured
            or self.basis is QuantityBasis.RUNNING_HOURS
        )

    @property
    def grams(self) -> float:
        """How much Material it counts for; millilitres weigh their density."""
        if self.kind is not LineItemKind.MATERIAL or not self.quantity:
            return 0.0
        if self.unit == "ml" and self.material is not None:
            return self.quantity * self.material.density
        return self.quantity

    @property
    def negative_prices(self) -> bool:
        """Only Other Line Items record discounts and refunds."""
        return self.kind is LineItemKind.OTHER

    def values(self) -> dict[str, float | None]:
        return {name: getattr(self, name) for name in VALUES}

    def override(self, values: dict[str, float | None]) -> None:
        """Take the user's quantity, unit price and/or amount.

        An amount back-computes the unit price; with an empty or zero quantity
        the amount stands.
        """
        if self.is_computed and self.computed is None:
            self.computed = self.values()
        for name, value in values.items():
            setattr(self, name, value)
        if not self.quantity:
            return
        if "amount" in values:
            self.unit_price = self.amount / self.quantity
        else:
            self.amount = self.quantity * self.unit_price

    def recompute(self, quantity: float) -> None:
        """A new computed quantity at the computed unit price; overrides still count."""
        unit_price = (self.computed or self.values())["unit_price"] or 0.0
        values: dict[str, float | None] = {
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": quantity * unit_price,
        }
        if self.computed is None:
            for name, value in values.items():
                setattr(self, name, value)
        else:
            self.computed = values

    def reset(self) -> None:
        """Back to the computed values."""
        for name, value in (self.computed or {}).items():
            setattr(self, name, value)
        self.computed = None

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "material_id": self.material_id,
            "material": None if self.material is None else self.material.as_dict(),
            "measured": self.measured,
            "length": self.length,
            "template_id": self.template_id,
            "basis": self.basis,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "amount": self.amount,
            "method": self.method,
            "segments": [segment.as_dict() for segment in self.segments],
            "computed": self.computed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineItem:
        return cls(
            id=data["id"],
            kind=LineItemKind(data["kind"]),
            label=data["label"],
            material_id=data.get("material_id"),
            material=None
            if (material := data.get("material")) is None
            else MaterialCopy.from_dict(material),
            measured=data.get("measured", False),
            length=data.get("length"),
            template_id=data.get("template_id"),
            basis=None if data.get("basis") is None else QuantityBasis(data["basis"]),
            quantity=data["quantity"],
            unit=data["unit"],
            unit_price=data["unit_price"],
            amount=data["amount"],
            method=None
            if data["method"] is None
            else ElectricityMethod(data["method"]),
            segments=[PriceSegment.from_dict(s) for s in data["segments"]],
            computed=data.get("computed"),
            unknown=unknown_fields(cls, data),
        )


class ImageKind(StrEnum):
    """In Cover Image order: Thumbnail, Snapshot, then uploads by time."""

    THUMBNAIL = "thumbnail"
    SNAPSHOT = "snapshot"
    UPLOAD = "upload"


@dataclass
class RunImage:
    """A stored image of a Run; its files are named after `id`, which never changes."""

    id: str
    kind: ImageKind
    created: datetime
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "kind": self.kind,
            "created": self.created.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunImage:
        return cls(
            id=data["id"],
            kind=ImageKind(data["kind"]),
            created=datetime.fromisoformat(data["created"]),
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
    (since, running W, paused W) the Run's consumption model used. `usage` is what
    the Material used input last reported during the Run: its measured total.
    `cover_id` is the image the user picked as Cover Image.
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
    images: list[RunImage] = field(default_factory=list)
    usage: Usage | None = None
    cover_id: str | None = None
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def electricity(self) -> LineItem:
        return next(i for i in self.line_items if i.kind is LineItemKind.ELECTRICITY)

    def locked(self, item: LineItem) -> bool:
        """Computed values update live until the Run is final; then they are the user's."""
        return not self.finalised and item.is_computed

    def deletable(self, item: LineItem) -> bool:
        """Every Run keeps its one Electricity Line Item, overridden down to 0 at most."""
        return item.kind is not LineItemKind.ELECTRICITY and not self.locked(item)

    @property
    def images_in_order(self) -> list[RunImage]:
        order = list(ImageKind)
        return sorted(
            self.images, key=lambda image: (order.index(image.kind), image.created)
        )

    @property
    def cover(self) -> RunImage | None:
        """The picked image, else the first in order; a deleted pick falls back."""
        picked = (image for image in self.images if image.id == self.cover_id)
        return next(picked, None) or next(iter(self.images_in_order), None)

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
            "usage": None if self.usage is None else self.usage.as_dict(),
            "line_items": [item.as_dict() for item in self.line_items],
            "images": [image.as_dict() for image in self.images],
            "cover_id": self.cover_id,
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
            usage=None
            if (usage := data.get("usage")) is None
            else Usage.from_dict(usage),
            line_items=[LineItem.from_dict(item) for item in data["line_items"]],
            images=[RunImage.from_dict(image) for image in data.get("images", [])],
            cover_id=data.get("cover_id"),
            unknown=unknown_fields(cls, data),
        )
