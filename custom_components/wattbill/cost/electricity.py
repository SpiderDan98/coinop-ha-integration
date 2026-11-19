"""Electricity cost: Σ price_i x energy within segment_i, split at every price change."""

from collections.abc import Callable, Sequence
from datetime import datetime

from custom_components.wattbill.models import (
    ElectricityMethod,
    LineItem,
    LineItemKind,
    PriceSegment,
)

type Prices = Sequence[tuple[datetime, float | None]]


def _spans(
    prices: Prices, end: datetime
) -> list[tuple[datetime, datetime, float | None]]:
    return [
        (since, prices[i + 1][0] if i + 1 < len(prices) else end, price)
        for i, (since, price) in enumerate(prices)
    ]


def price_gap(start: datetime, end: datetime, prices: Prices) -> bool:
    """Whether the price was unavailable during part of [start, end]."""
    return any(
        price is None and max(since, start) < min(until, end)
        for since, until, price in _spans(prices, end)
    )


def _filled(prices: Prices, end: datetime) -> list[tuple[datetime, float]]:
    """Each gap at the last valid price, else the first one before `end`, else 0."""
    first = next((p for t, p in prices if p is not None and t < end), 0.0)
    filled: list[tuple[datetime, float]] = []
    for since, price in prices:
        price = (filled[-1][1] if filled else first) if price is None else price
        if not filled or filled[-1][1] != price:
            filled.append((since, price))
    return filled


def price_segments(
    start: datetime,
    end: datetime,
    kwh: Callable[[datetime, datetime], float],
    prices: Prices,
) -> list[PriceSegment]:
    """Split [start, end] at each price change; `prices` are (since, price) by time."""
    prices = _filled(prices, end)
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
    prices: Prices,
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
