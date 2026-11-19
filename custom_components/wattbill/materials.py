"""Materials: what a Device uses up, priced per gram from a Cost Source.

Free of Home Assistant types; `as_dict` / `from_dict` give the catalog Store's
JSON shape. A Cost Source is one entry of `PRICE_SOURCES` ("fixed" or
"spoolman") with a `per_gram(density)` price.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .models import unknown_fields


class MaterialForm(StrEnum):
    FILAMENT = "filament"
    RESIN = "resin"


class PackUnit(StrEnum):
    GRAM = "g"
    MILLILITRE = "ml"


DEFAULT_DIAMETER = 1.75

# Built-in types with their usual form and density (g/cm³), for pre-filling.
MATERIAL_TYPES = {
    "PLA": (MaterialForm.FILAMENT, 1.24),
    "PLA-CF": (MaterialForm.FILAMENT, 1.29),
    "PETG": (MaterialForm.FILAMENT, 1.27),
    "PETG-CF": (MaterialForm.FILAMENT, 1.30),
    "ABS": (MaterialForm.FILAMENT, 1.04),
    "ASA": (MaterialForm.FILAMENT, 1.07),
    "TPU": (MaterialForm.FILAMENT, 1.21),
    "PA": (MaterialForm.FILAMENT, 1.14),
    "PC": (MaterialForm.FILAMENT, 1.20),
    "HIPS": (MaterialForm.FILAMENT, 1.04),
    "PVA": (MaterialForm.FILAMENT, 1.23),
    "Standard resin": (MaterialForm.RESIN, 1.10),
    "ABS-like resin": (MaterialForm.RESIN, 1.10),
    "Water-washable resin": (MaterialForm.RESIN, 1.10),
}


def type_density(material_type: str) -> float | None:
    """The built-in density of a type, matched ignoring case."""
    return next(
        (
            density
            for name, (_, density) in MATERIAL_TYPES.items()
            if name.casefold() == material_type.casefold()
        ),
        None,
    )


@dataclass
class FixedPrice:
    """Fixed Cost Source: pack price and pack size as on the receipt."""

    pack_price: float
    pack_size: float
    pack_unit: PackUnit

    def per_gram(self, density: float) -> float:
        grams_per_unit = density if self.pack_unit is PackUnit.MILLILITRE else 1
        return self.pack_price / (self.pack_size * grams_per_unit)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "fixed",
            "pack_price": self.pack_price,
            "pack_size": self.pack_size,
            "pack_unit": self.pack_unit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixedPrice:
        return cls(data["pack_price"], data["pack_size"], PackUnit(data["pack_unit"]))


@dataclass
class SpoolmanPrice:
    """Spoolman Cost Source: the linked Filament and the last price per gram read."""

    filament_id: int
    last_read: float | None = None

    def per_gram(self, density: float) -> float:
        return self.last_read or 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "spoolman",
            "filament_id": self.filament_id,
            "per_gram": self.last_read,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpoolmanPrice:
        return cls(data["filament_id"], data.get("per_gram"))


PRICE_SOURCES: dict[str, type[FixedPrice] | type[SpoolmanPrice]] = {
    "fixed": FixedPrice,
    "spoolman": SpoolmanPrice,
}


def price_from_dict(data: dict[str, Any]) -> FixedPrice | SpoolmanPrice:
    return PRICE_SOURCES[data["source"]].from_dict(data)


@dataclass
class Material:
    """One catalogue entry; archived ones leave pickers and Slot matching."""

    id: str
    name: str
    form: MaterialForm
    type: str
    density: float
    price: FixedPrice | SpoolmanPrice
    vendor: str | None = None
    colour: str | None = None
    diameter: float | None = None
    default_for_type: bool = False
    archived: bool = False
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def price_per_gram(self) -> float:
        return self.price.per_gram(self.density)

    def as_dict(self) -> dict[str, Any]:
        return self.unknown | {
            "id": self.id,
            "name": self.name,
            "form": self.form,
            "type": self.type,
            "density": self.density,
            "vendor": self.vendor,
            "colour": self.colour,
            "diameter": self.diameter,
            "default_for_type": self.default_for_type,
            "archived": self.archived,
            "price": self.price.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Material:
        return cls(
            id=data["id"],
            name=data["name"],
            form=MaterialForm(data["form"]),
            type=data["type"],
            density=data["density"],
            price=price_from_dict(data["price"]),
            vendor=data["vendor"],
            colour=data["colour"],
            diameter=data["diameter"],
            default_for_type=data["default_for_type"],
            archived=data["archived"],
            unknown=unknown_fields(cls, data),
        )
