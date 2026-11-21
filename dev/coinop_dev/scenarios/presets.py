"""The Presets: named Scenarios."""

from dataclasses import dataclass
from typing import Any

from .pieces import PIECES, QuickStartPiece, ordered

# How much history the Devices with history get: none leaves each alone.
HISTORIES = ("none", "short", "long")


@dataclass(frozen=True)
class Preset:
    title: str
    description: str
    pieces: tuple[str, ...]
    history: str = "short"
    open_run: bool = False

    @property
    def selection(self) -> dict[str, Any]:
        return {
            "pieces": ordered(self.pieces),
            "history": self.history,
            "open_run": self.open_run,
        }


PRESETS = {
    "empty": Preset("Empty", "The hub without any Device.", ()),
    "quick-start": Preset(
        "Quick Start",
        "The hub without any Device, and every Quick Start Piece: Add Device offers "
        "each HA device in Quick Start as its Device Type.",
        tuple(n for n, p in PIECES.items() if isinstance(p, QuickStartPiece)),
    ),
    "few-runs": Preset(
        "3D printer, a few Runs", "The Prusa with its 7 Runs.", ("prusa",)
    ),
    "printing-now": Preset(
        "3D printer, printing now",
        "Like a few Runs, with an open Run; the printer's helpers end it.",
        ("prusa",),
        open_run=True,
    ),
    "two-printers": Preset(
        "Two printers", "The Prusa and the Bambu with their Runs.", ("prusa", "bambu")
    ),
    "long-history": Preset(
        "Long history",
        "Two years of Runs on two printers, 8 Materials (one archived), a Line Item "
        "Template.",
        ("prusa", "bambu"),
        history="long",
    ),
    "washing-machine": Preset(
        "Washing machine", "The washing machine with its 10 loads.", ("washer",)
    ),
    "irrigation": Preset(
        "Irrigation (Other Device)",
        "The garden valve with its 6 waterings.",
        ("irrigation",),
    ),
}
