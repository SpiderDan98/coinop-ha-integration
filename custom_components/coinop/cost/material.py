"""Material Line Items: measured usage in grams, priced from a Material's price per gram.

A Material priced per piece counts pieces at its price per piece instead.
"""

from collections.abc import Callable
from dataclasses import replace
import math

from custom_components.coinop.materials import Material, PackUnit
from custom_components.coinop.models import (
    DoseSource,
    LineItem,
    LineItemKind,
    MaterialCopy,
    SlotReport,
    Usage,
    UsageUnit,
)

GRAM = "g"
MILLILITRE = "ml"
PIECES = "pcs"


def grams_of_length(length: float, material: Material) -> float | None:
    """Grams in `length` mm of the Material's filament; None without a diameter."""
    if material.diameter is None or material.density is None:
        return None
    cubic_mm = length * math.pi * (material.diameter / 2) ** 2
    return cubic_mm / 1000 * material.density


def line_unit(material: Material | None, unit: str) -> str:
    """The unit a Line Item counts the Material in: pieces for one priced per
    piece, else g or ml as before (ml when it is bought by volume)."""
    if material is None:
        return unit
    if material.by_piece:
        return PIECES
    if unit == PIECES:
        by_volume = material.price.pack_unit is PackUnit.MILLILITRE
        return MILLILITRE if by_volume else GRAM
    return unit


def unit_price(material: Material, unit: str) -> float:
    """The Material's current price per gram, millilitre or piece; 0 if it has none."""
    if unit == PIECES:
        return material.price_per_piece or 0.0
    per_gram = material.price_per_gram or 0.0
    return per_gram * (material.density or 0.0) if unit == MILLILITRE else per_gram


def copy(material: Material) -> MaterialCopy:
    return MaterialCopy(
        name=material.name,
        type=material.type,
        density=material.density,
        diameter=material.diameter,
        price_per_gram=material.price_per_gram,
    )


def _amount(quantity: float | None, price: float) -> float:
    return quantity * price if quantity else 0.0


def material_line_item(
    item_id: str,
    usage: Usage | None,
    material: Material | None,
    *,
    measured: bool = True,
    unit: str = GRAM,
    slots: list[SlotReport] | None = None,
    share: float | None = None,
) -> LineItem:
    """The Material Line Item for a measured total, in grams.

    A length needs a Material to become grams; without one the quantity stays
    empty until a Material is picked. Without a Material the price is 0.
    """
    length = usage.value if usage and usage.unit is UsageUnit.MILLIMETRE else None
    quantity = usage.value if usage and usage.unit is UsageUnit.GRAM else None
    if length is not None and material is not None:
        quantity = grams_of_length(length, material)
    unit = line_unit(material, unit)
    price = 0.0 if material is None else unit_price(material, unit)
    return LineItem(
        id=item_id,
        kind=LineItemKind.MATERIAL,
        quantity=quantity,
        unit=unit,
        unit_price=price,
        amount=_amount(quantity, price),
        material_id=None if material is None else material.id,
        material=None if material is None else copy(material),
        measured=measured,
        length=length,
        slots=slots or [],
        share=share,
    )


def dose_line_item(
    item_id: str,
    dose_id: str,
    material: Material,
    amount: float,
    source: DoseSource = DoseSource.DEFAULT_ROW,
) -> LineItem:
    """A Dose's Line Item: `amount` in the Material's pack unit at its current price."""
    item = material_line_item(
        item_id, None, material, measured=False, unit=material.price.pack_unit.value
    )
    item.quantity, item.amount = amount, _amount(amount, item.unit_price)
    item.dose_id, item.dose_source = dose_id, source
    return item


def in_pack_unit(material: Material, quantity: float, unit: str) -> float | None:
    """`quantity` g or ml in the Material's pack unit; None for one priced per piece."""
    if material.density is None:
        return None
    pack_unit = material.price.pack_unit.value
    if unit == pack_unit:
        return quantity
    return (
        quantity * material.density
        if unit == MILLILITRE
        else quantity / material.density
    )


def slot_line_items(
    usage: Usage | None,
    shares: dict[SlotReport, float],
    material_of: Callable[[SlotReport], Material | None],
    item_id: Callable[[str | None], str],
) -> list[LineItem]:
    """One measured Line Item per Material the loaded Slots held.

    With several, each gets the share of the measured total its Slots had;
    `item_id` names the Line Item of a Material id.
    """
    groups: dict[str | None, tuple[Material | None, list[SlotReport], float]] = {}
    for slot, share in shares.items():
        material = material_of(slot)
        key = None if material is None else material.id
        _, slots, total = groups.get(key, (material, [], 0.0))
        groups[key] = (material, [*slots, slot], total + share)
    split = len(groups) > 1
    return [
        material_line_item(
            item_id(key),
            replace(usage, value=usage.value * share) if usage and split else usage,
            material,
            slots=slots,
            share=share if split else None,
        )
        for key, (material, slots, share) in groups.items()
    ]


def change_material(item: LineItem, material: Material) -> None:
    """Re-price at the Material's current price and copy it.

    The grams follow the stored length unless the user overrode the quantity;
    an overridden Line Item keeps the recomputed values as its computed ones.
    Between pieces and grams the quantity stays and only the unit changes.
    """
    item.unit = line_unit(material, item.unit)
    price = unit_price(material, item.unit)
    item.material_id, item.material = material.id, copy(material)
    computed = item.computed
    measured = computed["quantity"] if computed is not None else item.quantity
    if item.length is not None:
        measured = grams_of_length(item.length, material)
    if computed is None or item.quantity == computed["quantity"]:
        item.quantity = measured
    if computed is not None:
        item.computed = {
            "quantity": measured,
            "unit_price": price,
            "amount": _amount(measured, price),
        }
    item.unit_price = price
    if item.quantity:
        item.amount = item.quantity * price
    if item.computed == item.values():
        item.computed = None
