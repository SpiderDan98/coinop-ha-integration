"""The quantities a Run consumes and Coin-op prices by its timelines, such as electricity."""

from dataclasses import dataclass

from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    EnergyConverter,
    PowerConverter,
    VolumeConverter,
    VolumeFlowRateConverter,
)

from .device_config import ConsumptionSource, WaterSource
from .models import LineItemKind


@dataclass(frozen=True)
class Quantity:
    """A consumed quantity: how its inputs read and how its Line Item is priced.

    A meter (source `total_source`) reports a running total, a rate input
    (`rate_source`) a rate, of which 1 held for `unit_seconds` makes one `unit`.
    Readings are kept in `unit` and `rate_unit`, prices per `unit`; the user
    enters and reads prices per `price_unit`, and a price entity's unit is one of
    `price_units` (`{currency}` stands for the currency) or converted by a factor.
    The Device keeps its sections under `source_key` and `price_key`; a Program
    Defaults row its amount per Run under `default_key`. Amounts are shown to
    `decimals`, those under 1 `unit` to `small_decimals`, so that a coffee's
    0.04 L doesn't read as 0.
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
    price_unit: str
    price_units: tuple[str, ...]
    default_key: str
    decimals: int
    small_decimals: int

    def shown_decimals(self, amount: float) -> int:
        """The decimals `amount` is shown to."""
        return self.small_decimals if abs(amount) < 1 else self.decimals

    def units(self, source: str) -> tuple[type[BaseUnitConverter], str]:
        """The converter and the unit readings of `source` are kept in."""
        if source == self.total_source:
            return self.total_converter, self.unit
        return self.rate_converter, self.rate_unit

    def per_unit(self, price: float) -> float:
        """A price per `price_unit` as the price per `unit`."""
        return price * self.total_converter.get_unit_ratio(self.price_unit, self.unit)


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
    price_unit=UnitOfEnergy.KILO_WATT_HOUR,
    price_units=("{currency}/kWh", "ct/kWh", "{currency}/MWh"),
    default_key="kwh",
    decimals=3,
    small_decimals=3,
)

WATER = Quantity(
    kind=LineItemKind.WATER,
    unit=UnitOfVolume.LITERS,
    total_source=WaterSource.METER,
    total_converter=VolumeConverter,
    rate_source=WaterSource.FLOW,
    rate_unit=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
    rate_converter=VolumeFlowRateConverter,
    unit_seconds=60,
    source_key="water",
    price_key="water_price",
    price_unit=UnitOfVolume.CUBIC_METERS,
    price_units=("{currency}/m³", "{currency}/L", "ct/L"),
    default_key="litres",
    decimals=1,
    small_decimals=3,
)

QUANTITIES = {quantity.kind: quantity for quantity in (ELECTRICITY, WATER)}
