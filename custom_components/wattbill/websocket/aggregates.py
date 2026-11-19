"""Totals across Runs for the Overview and Analysis (see `aggregates.py`)."""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.wattbill.aggregates import DIMENSIONS, aggregate
from custom_components.wattbill.cost.rounding import currency_decimals
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol

from .command import command


@command(
    {
        vol.Required("type"): "wattbill/aggregates/get",
        vol.Optional("group_by", default=[]): vol.All(
            [vol.In(DIMENSIONS)], vol.Unique()
        ),
    }
)
def _get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """`{"groups": [...]}`: each group's values along `group_by`, then its totals."""
    groups = aggregate(
        wattbill.book.runs(),
        msg["group_by"],
        dt_util.utcnow(),
        currency_decimals(hass.config.currency),
        dt_util.get_default_time_zone(),
        {material.id: material.name for material in wattbill.catalog.materials()},
    )
    connection.send_result(msg["id"], {"groups": groups})


COMMANDS = (_get,)
