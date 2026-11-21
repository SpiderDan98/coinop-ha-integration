"""The Presets: named Scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from custom_components.coinop.schema import vol

from .pieces import PIECES, QuickStartPiece, ordered

# How much history the Devices with history get: none leaves each alone.
HISTORIES = ("none", "short", "long")
# A selection with its Pieces in order and the Options it leaves out at their defaults.
SELECTION = vol.Schema(
    {
        vol.Required("pieces"): vol.All([vol.In(list(PIECES))], ordered),
        vol.Optional("history", default="short"): vol.In(HISTORIES),
        vol.Optional("open_run", default=False): bool,
        vol.Optional("spoolman", default=False): bool,
    }
)


@dataclass(frozen=True)
class Preset:
    title: str
    description: str
    pieces: tuple[str, ...]
    # The Options it doesn't leave at their defaults.
    options: Mapping[str, Any] = MappingProxyType({})

    @property
    def selection(self) -> dict[str, Any]:
        selection: dict[str, Any] = SELECTION(
            {"pieces": list(self.pieces), **self.options}
        )
        return selection


PRESETS = {
    "empty": Preset("Empty", "The hub without any Device.", ()),
    "quick-start": Preset(
        "Quick Start",
        "Every Quick Start Piece, for Add Device to offer each HA device in Quick Start.",
        tuple(n for n, p in PIECES.items() if isinstance(p, QuickStartPiece)),
    ),
    "few-runs": Preset(
        "3D printer, a few Runs", "The Prusa with its 7 Runs.", ("prusa",)
    ),
    "printing-now": Preset(
        "3D printer, printing now",
        "Like a few Runs, with an open Run; the printer's helpers end it.",
        ("prusa",),
        {"open_run": True},
    ),
    "two-printers": Preset(
        "Two printers", "The Prusa and the Bambu with their Runs.", ("prusa", "bambu")
    ),
    "long-history": Preset(
        "Long history",
        "Two years of Runs on two printers, 8 Materials (one archived), a Line Item "
        "Template.",
        ("prusa", "bambu"),
        {"history": "long"},
    ),
    "spoolman": Preset(
        "3D printer on Spoolman",
        "Like a few Runs, with the 8 filaments linked to Spoolman, which prices them.",
        ("prusa",),
        {"spoolman": True},
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


def preset_of(selection: Mapping[str, Any]) -> str | None:
    """The name of the Preset that has the selection, if one has it."""
    return next((n for n, p in PRESETS.items() if p.selection == selection), None)
