"""The statement's words and numbers in its language: strings from `strings/<lang>.json`,
money in the HA currency, dates in the HA time zone.
"""

from datetime import datetime, timedelta, tzinfo
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from custom_components.coinop.cost.rounding import currency_decimals

from .export import LANGUAGES

# Read at import, which Home Assistant does outside the event loop.
STRINGS: dict[str, dict[str, Any]] = {
    language: json.loads(
        (Path(__file__).parent / "strings" / f"{language}.json").read_text("utf-8")
    )
    for language in LANGUAGES
}

QUANTITY_DECIMALS = {"kWh": 3, "L": 1, "g": 1, "ml": 1, "h": 2, "pcs": 0}
SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "CN¥",
    "INR": "₹",
    "KRW": "₩",
    "CAD": "CA$",
    "AUD": "A$",
}
# Decimal and grouping separators.
SEPARATORS = {"en": (".", ","), "de": (",", ".")}


class Text:
    def __init__(self, language: str, currency: str, time_zone: tzinfo) -> None:
        self.language = language
        self.decimals = currency_decimals(currency)
        self._strings = STRINGS[language]
        self._symbol = SYMBOLS.get(currency.upper(), currency.upper())
        self._time_zone = time_zone

    def __call__(self, key: str, **values: Any) -> str:
        text: Any = self._strings
        for part in key.split("."):
            text = text[part]
        return str(text).format(**values)

    def number(self, value: float | Decimal, most: int, least: int = 0) -> str:
        whole, _, fraction = f"{abs(value):,.{most}f}".partition(".")
        fraction = fraction.rstrip("0").ljust(least, "0")
        point, group = SEPARATORS[self.language]
        text = whole.replace(",", group) + (point + fraction if fraction else "")
        return f"-{text}" if value < 0 and text.strip("0.,") else text

    def _money(self, amount: float | Decimal, most: int) -> str:
        number = self.number(amount, most, self.decimals)
        sign, number = ("-", number[1:]) if number[0] == "-" else ("", number)
        if self.language == "de":
            return f"{sign}{number} {self._symbol}"
        space = " " if self._symbol.isalpha() else ""
        return f"{sign}{self._symbol}{space}{number}"

    def money(self, amount: Decimal) -> str:
        return self._money(amount, self.decimals)

    def unit_price(self, price: float) -> str:
        return self._money(price, max(4, self.decimals))

    def quantity(self, quantity: float, unit: str) -> str:
        return f"{self.number(quantity, QUANTITY_DECIMALS.get(unit, 2))} {unit}"

    def percent(self, percent: float) -> str:
        return self.number(percent, 2)

    def date(self, moment: datetime) -> str:
        local = moment.astimezone(self._time_zone)
        return self(
            "date",
            day=local.day,
            dd=f"{local.day:02}",
            month=self("months").split()[local.month - 1],
            mm=f"{local.month:02}",
            year=local.year,
        )

    def duration(self, duration: timedelta) -> str:
        minutes = round(duration.total_seconds() / 60)
        return self("duration", hours=minutes // 60, minutes=minutes % 60)
