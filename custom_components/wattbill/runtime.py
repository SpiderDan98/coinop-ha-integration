"""What a loaded hub entry holds while it runs."""

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry

from .catalog import Catalog
from .device_config import DeviceConfig
from .device_settings import DeviceSettings
from .images import ImageLibrary
from .run_book import RunBook
from .spoolman import Spoolman
from .statement import CostStatements
from .tracker import DeviceTracker


@dataclass
class WattBill:
    book: RunBook
    catalog: Catalog
    images: ImageLibrary
    devices: list[DeviceConfig]
    settings: DeviceSettings
    spoolman: Spoolman
    trackers: list[DeviceTracker]
    statements: CostStatements = field(default_factory=CostStatements)


type WattBillConfigEntry = ConfigEntry[WattBill]
