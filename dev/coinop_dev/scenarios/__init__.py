"""The Scenarios: Coin-op set up from scratch with the picked Pieces, then filled
through its own websocket API the way the panel fills it, so the data goes through
the same code as a user's."""

from .load import async_load
from .pieces import KINDS, PIECES, DeviceWithHistory, QuickStartPiece
from .presets import HISTORIES, PRESETS, Preset
from .seed import ScenarioError

__all__ = [
    "HISTORIES",
    "KINDS",
    "PIECES",
    "PRESETS",
    "DeviceWithHistory",
    "Preset",
    "QuickStartPiece",
    "ScenarioError",
    "async_load",
]
