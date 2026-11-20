"""Material Line Items: measured usage in grams, priced from a Material's price per gram."""

from collections.abc import Callable
from dataclasses import replace
import math

from custom_components.coinop.materials import Material
from custom_components.coinop.models import (
    LineItem,
    LineItemKind,
    MaterialCopy,
    SlotReport,
    Usage,
    UsageUnit,
)

GRAM = "g"
MILLILITRE = "ml"


def grams_of_length(length: float, material: Material) -> float | None:
    """Grams in `length` mm of the Material's filament; None without a diameter."""
    if material.diameter is None:
        return None
    cubic_mm = length * math.pi * (material.diameter / 2) ** 2
    return cubic_mm / 1000 * material.density


def unit_price(material: Material, unit: str) -> float:
    """The Material's current price per gram, or per millilitre."""
    per_gram = material.price_per_gram
    return per_gram * material.density if unit == MILLILITRE else per_gram


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
    """
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
