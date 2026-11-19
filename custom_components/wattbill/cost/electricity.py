"""Electricity cost: Σ price_i x energy within segment_i, split at every price change."""

from collections.abc import Callable, Sequence
from datetime import datetime

from custom_components.wattbill.models import (
    ElectricityMethod,
    LineItem,
    LineItemKind,
    PriceSegment,
)


def price_segments(
    start: datetime,
    end: datetime,
    kwh: Callable[[datetime, datetime], float],
    prices: Sequence[tuple[datetime, float]],
) -> list[PriceSegment]:
    """Split [start, end] at each price change; `prices` are (since, price) by time."""
    if not prices:
        return [PriceSegment(start, end, kwh(start, end), 0.0)]
    current = next(
        (price for since, price in reversed(prices) if since <= start), prices[0][1]
    )
    segments: list[PriceSegment] = []
    for since, price in [(t, p) for t, p in prices if start < t < end] + [(end, 0.0)]:
        segments.append(PriceSegment(start, since, kwh(start, since), current))
        start, current = since, price
    return segments


def electricity_line_item(
    item_id: str,
    start: datetime,
    end: datetime,
    kwh: Callable[[datetime, datetime], float],
    prices: Sequence[tuple[datetime, float]],
    method: ElectricityMethod,
) -> LineItem:
    segments = price_segments(start, end, kwh, prices)
    quantity = sum(segment.kwh for segment in segments)
    amount = sum(segment.kwh * segment.unit_price for segment in segments)
    unit_prices = {segment.unit_price for segment in segments}
    if len(unit_prices) == 1:
        [unit_price] = unit_prices
    else:
        unit_price = amount / quantity if quantity else segments[-1].unit_price
    return LineItem(
        id=item_id,
        kind=LineItemKind.ELECTRICITY,
        quantity=quantity,
        unit="kWh",
        unit_price=unit_price,
        amount=amount,
        method=method,
        segments=segments,
    )
