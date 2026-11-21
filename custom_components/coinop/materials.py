"""Materials: what a Device uses up, priced per gram (or per piece) from a Cost Source.

Free of Home Assistant types; `as_dict` / `from_dict` give the catalog Store's
JSON shape. A Cost Source is one entry of `PRICE_SOURCES` ("fixed" or
"spoolman") with a `per_gram(density)` and a `per_piece()` price. A Material
bought by the piece (pods, sheets) has no density and no price per gram.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .models import unknown_fields


class MaterialForm(StrEnum):
    FILAMENT = "filament"
    RESIN = "resin"
    DETERGENT = "detergent"
    FABRIC_SOFTENER = "fabric_softener"
    LAUNDRY_ADDITIVE = "laundry_additive"
    DISHWASHER_PRODUCT = "dishwasher_product"
    BEVERAGE_INGREDIENT = "beverage_ingredient"
    OTHER = "other"


class PackUnit(StrEnum):
    GRAM = "g"
    MILLILITRE = "ml"
    PIECE = "pcs"


# The pack unit of a form's Materials unless one is given; grams for a form not listed.
USUAL_UNITS = {
    MaterialForm.RESIN: PackUnit.MILLILITRE,
    MaterialForm.DISHWASHER_PRODUCT: PackUnit.PIECE,
}
# Forms whose Materials are never linked to a Spoolman Filament.
UNLINKED_FORMS = frozenset(
    {
        MaterialForm.DISHWASHER_PRODUCT,
        MaterialForm.BEVERAGE_INGREDIENT,
        MaterialForm.OTHER,
    }
)

DEFAULT_DIAMETER = 1.75

# Built-in types with their usual form, density (g/cm³) and pack unit, for pre-filling.
MATERIAL_TYPES: dict[str, tuple[MaterialForm, float | None, PackUnit]] = {
    "PLA": (MaterialForm.FILAMENT, 1.24, PackUnit.GRAM),
    "PLA-CF": (MaterialForm.FILAMENT, 1.29, PackUnit.GRAM),
    "PETG": (MaterialForm.FILAMENT, 1.27, PackUnit.GRAM),
    "PETG-CF": (MaterialForm.FILAMENT, 1.30, PackUnit.GRAM),
    "ABS": (MaterialForm.FILAMENT, 1.04, PackUnit.GRAM),
    "ASA": (MaterialForm.FILAMENT, 1.07, PackUnit.GRAM),
    "TPU": (MaterialForm.FILAMENT, 1.21, PackUnit.GRAM),
    "PA": (MaterialForm.FILAMENT, 1.14, PackUnit.GRAM),
    "PC": (MaterialForm.FILAMENT, 1.20, PackUnit.GRAM),
    "HIPS": (MaterialForm.FILAMENT, 1.04, PackUnit.GRAM),
    "PVA": (MaterialForm.FILAMENT, 1.23, PackUnit.GRAM),
    "Standard resin": (MaterialForm.RESIN, 1.10, PackUnit.MILLILITRE),
    "ABS-like resin": (MaterialForm.RESIN, 1.10, PackUnit.MILLILITRE),
    "Water-washable resin": (MaterialForm.RESIN, 1.10, PackUnit.MILLILITRE),
    "Liquid detergent": (MaterialForm.DETERGENT, 1.04, PackUnit.MILLILITRE),
    "Powder detergent": (MaterialForm.DETERGENT, 0.7, PackUnit.GRAM),
    "Detergent pods": (MaterialForm.DETERGENT, None, PackUnit.PIECE),
    "Fabric softener": (MaterialForm.FABRIC_SOFTENER, 1.0, PackUnit.MILLILITRE),
    "Whitener": (MaterialForm.LAUNDRY_ADDITIVE, 0.9, PackUnit.GRAM),
    "Stain remover": (MaterialForm.LAUNDRY_ADDITIVE, 1.02, PackUnit.MILLILITRE),
    "Colour catcher sheets": (MaterialForm.LAUNDRY_ADDITIVE, None, PackUnit.PIECE),
    "Dishwasher tabs": (MaterialForm.DISHWASHER_PRODUCT, None, PackUnit.PIECE),
    "Dishwasher powder": (MaterialForm.DISHWASHER_PRODUCT, 0.95, PackUnit.GRAM),
    "Dishwasher salt": (MaterialForm.DISHWASHER_PRODUCT, 1.2, PackUnit.GRAM),
    "Rinse aid": (MaterialForm.DISHWASHER_PRODUCT, 1.02, PackUnit.MILLILITRE),
    "Coffee beans": (MaterialForm.BEVERAGE_INGREDIENT, 0.4, PackUnit.GRAM),
    "Ground coffee": (MaterialForm.BEVERAGE_INGREDIENT, 0.35, PackUnit.GRAM),
    "Milk": (MaterialForm.BEVERAGE_INGREDIENT, 1.03, PackUnit.MILLILITRE),
}


def type_density(material_type: str) -> float | None:
    """The built-in density of a type, matched ignoring case."""
    return next(
        (
            density
            for name, (_, density, _) in MATERIAL_TYPES.items()
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

    def per_gram(self, density: float | None) -> float | None:
        if self.pack_unit is PackUnit.PIECE:
            return None
        if self.pack_unit is PackUnit.GRAM:
            return self.pack_price / self.pack_size
        return None if density is None else self.pack_price / (self.pack_size * density)

    def per_piece(self) -> float | None:
        if self.pack_unit is not PackUnit.PIECE:
            return None
        return self.pack_price / self.pack_size

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
    pack_unit = PackUnit.GRAM

    def per_gram(self, density: float | None) -> float:
        return self.last_read or 0.0

    def per_piece(self) -> None:
        return None

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
    density: float | None
    price: FixedPrice | SpoolmanPrice
    vendor: str | None = None
    colour: str | None = None
    diameter: float | None = None
    default_for_type: bool = False
    archived: bool = False
    unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def by_piece(self) -> bool:
        return self.price.pack_unit is PackUnit.PIECE

    @property
    def linkable(self) -> bool:
        """Whether the Material can be linked to a Spoolman Filament."""
        return not self.by_piece and self.form not in UNLINKED_FORMS

    @property
    def price_per_gram(self) -> float | None:
        return self.price.per_gram(self.density)

    @property
    def price_per_piece(self) -> float | None:
        return self.price.per_piece()

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
