"""Spoolman for the Materials tab: reading it, and merging own Materials into it.

Reading Spoolman brings the Materials up to date (see `spoolman.py`), so opening
the tab creates, refreshes and archives the linked Materials; it answers which
own Materials have Filaments waiting to be merged into them.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol
from custom_components.coinop.spoolman import Merge, SpoolmanUnreachable, StaleMerge

from .command import command

ERR_SPOOLMAN_UNREACHABLE = "spoolman_unreachable"


def _ok(merges: list[Merge]) -> dict[str, Any]:
    return {
        "status": "ok",
        "merges": [
            {
                "material_id": merge.material.id,
                "candidates": [filament.as_dict() for filament in merge.candidates],
            }
            for merge in merges
        ],
    }


@command({vol.Required("type"): "coinop/spoolman/read"})
async def _read(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """`status` is "ok", "unreachable" or "not_configured" (no URL in the options);
    `merges` the own Materials with the Filaments they can be merged into, best first."""
    if coinop.spoolman.url is None:
        connection.send_result(msg["id"], {"status": "not_configured", "merges": []})
        return
    try:
        merges = await coinop.spoolman.async_read()
    except SpoolmanUnreachable:
        connection.send_result(msg["id"], {"status": "unreachable", "merges": []})
        return
    connection.send_result(msg["id"], _ok(merges))


@command(
    {
        vol.Required("type"): "coinop/spoolman/merge",
        vol.Required("picks"): [
            {
                vol.Required("material_id"): str,
                vol.Required("filament_id"): vol.Any(None, int),
            }
        ],
    }
)
async def _merge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Each pick merges its Material into the Filament, or keeps it own (`null`).
    Answers like `read`; `not_allowed` when a pick no longer waits (read again)."""
    picks = {pick["material_id"]: pick["filament_id"] for pick in msg["picks"]}
    try:
        merges = await coinop.spoolman.async_merge(picks)
    except SpoolmanUnreachable:
        connection.send_error(
            msg["id"], ERR_SPOOLMAN_UNREACHABLE, "Spoolman can't be reached"
        )
        return
    except StaleMerge:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_ALLOWED,
            "Not every pick waits to be merged any more",
        )
        return
    connection.send_result(msg["id"], _ok(merges))


COMMANDS = (_read, _merge)
