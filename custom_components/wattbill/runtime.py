"""What a loaded hub entry holds while it runs."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .device_config import DeviceConfig
from .images import ImageLibrary
from .run_book import RunBook
from .tracker import DeviceTracker


@dataclass
class WattBill:
    book: RunBook
    images: ImageLibrary
    devices: list[DeviceConfig]
    trackers: list[DeviceTracker]


type WattBillConfigEntry = ConfigEntry[WattBill]
