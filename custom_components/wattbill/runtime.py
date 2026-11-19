"""What a loaded hub entry holds while it runs."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .catalog import Catalog
from .device_config import DeviceConfig
from .device_settings import DeviceSettings
from .run_book import RunBook
from .tracker import DeviceTracker


@dataclass
class WattBill:
    book: RunBook
    catalog: Catalog
    devices: list[DeviceConfig]
    settings: DeviceSettings
    trackers: list[DeviceTracker]


type WattBillConfigEntry = ConfigEntry[WattBill]
