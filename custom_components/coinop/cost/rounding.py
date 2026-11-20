"""Money as people see it: Line Item amounts rounded to the currency's decimals.

Totals and subtotals shown anywhere are sums of rounded amounts, so a receipt
always adds up. Stored values stay unrounded.
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 minor units that differ from the usual two.
_DECIMALS = {
    **dict.fromkeys(
        [
            *["BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG"],
            *["RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF"],
        ],
        0,
    ),
    **dict.fromkeys(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"], 3),
    **dict.fromkeys(["CLF", "UYW"], 4),
}


def currency_decimals(currency: str) -> int:
    return _DECIMALS.get(currency.upper(), 2)


def round_amount(amount: float, decimals: int) -> Decimal:
    # repr() keeps 0.125 from becoming 0.12499999... before rounding half up.
    return Decimal(repr(amount)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)


def rounded_sum(amounts: Iterable[float], decimals: int) -> Decimal:
    return sum(
        (round_amount(amount, decimals) for amount in amounts),
        Decimal(0).scaleb(-decimals),
    )
