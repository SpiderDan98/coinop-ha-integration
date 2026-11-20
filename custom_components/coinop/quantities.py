"""The quantities a Run consumes and Coin-op prices by its timelines, such as electricity."""

from dataclasses import dataclass

from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    PowerConverter,
)

from .device_config import ConsumptionSource
from .models import LineItemKind


@dataclass(frozen=True)
class Quantity:
    """A consumed quantity: how its inputs read and how its Line Item is priced.

    A meter (source `total_source`) reports a running total, a rate input
    (`rate_source`) a rate, of which 1 held for `unit_seconds` makes one `unit`.
    Readings are kept in `unit` and `rate_unit`, prices per `unit`. The Device
    keeps its sections under `source_key` and `price_key`.
    """

    kind: LineItemKind
    unit: str
    total_source: str
    total_converter: type[BaseUnitConverter]
    rate_source: str
    rate_unit: str
    rate_converter: type[BaseUnitConverter]
    unit_seconds: float
    source_key: str
    price_key: str

    def units(self, source: str) -> tuple[type[BaseUnitConverter], str]:
        """The converter and the unit readings of `source` are kept in."""
        if source == self.total_source:
            return self.total_converter, self.unit
        return self.rate_converter, self.rate_unit


ELECTRICITY = Quantity(
    kind=LineItemKind.ELECTRICITY,
    unit=UnitOfEnergy.KILO_WATT_HOUR,
    total_source=ConsumptionSource.ENERGY,
    total_converter=EnergyConverter,
    rate_source=ConsumptionSource.POWER,
    rate_unit=UnitOfPower.WATT,
    rate_converter=PowerConverter,
    unit_seconds=3_600_000,
    source_key="consumption",
    price_key="price",
)
