"""Line Item Templates: saved Other Line Items, copied into Runs.

A copy keeps only the template's id as its origin, so editing or deleting the
template never changes a Run. With the running-hours basis the quantity is the
Run's running time without pauses, live while the Run is open.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util.ulid import ulid_now

from .cost.running_time import running_time
from .models import LineItem, LineItemKind, QuantityBasis, Run, unknown_fields

TEMPLATES = "templates"


@dataclass
class LineItemTemplate:
    id: str
    label: str
    unit: str
    unit_price: float
    default_quantity: float
    basis: QuantityBasis
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    def line_item(
        self, run: Run, until: datetime, quantity: float | None = None
    ) -> LineItem:
        """The template's copy for `run`; `quantity` replaces an entered default."""
        item = LineItem(
            id=ulid_now(),
            kind=LineItemKind.OTHER,
            label=self.label,
            quantity=self.default_quantity if quantity is None else quantity,
            unit=self.unit,
            unit_price=self.unit_price,
            amount=0.0,
            template_id=self.id,
            basis=self.basis,
        )
        item.amount = (item.quantity or 0.0) * item.unit_price
        count_running_hours([item], run, until)
        return item

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "unit_price": self.unit_price,
            "default_quantity": self.default_quantity,
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineItemTemplate:
        return cls(
            id=data["id"],
            label=data["label"],
            unit=data["unit"],
            unit_price=data["unit_price"],
            default_quantity=data["default_quantity"],
            basis=QuantityBasis(data["basis"]),
            unknown=unknown_fields(cls, data),
        )


def count_running_hours(items: Iterable[LineItem], run: Run, until: datetime) -> None:
    """Set the running-hours quantities to the Run's running time up to `until`."""
    hours = running_time(run, until).total_seconds() / 3600
    for item in items:
        if item.basis is QuantityBasis.RUNNING_HOURS:
            item.recompute(hours)


def add_templates(
    run: Run, templates: Iterable[LineItemTemplate], until: datetime
) -> None:
    """Copy the templates into the Run, e.g. a Device's automatic templates.

    Running hours count up to `until` while the Run is open, to its end once ended.
    """
    run.line_items += [template.line_item(run, until) for template in templates]
