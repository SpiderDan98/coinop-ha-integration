"""Runs for the panel: the gallery list (live via subscription) and one Run in full.

Summaries carry what a gallery tile shows; `get` returns the stored Run with
amounts rounded to the currency and the derived subtotals and total.
"""

from datetime import datetime
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.util import dt as dt_util

from custom_components.wattbill.const import DOMAIN
from custom_components.wattbill.cost.rounding import (
    currency_decimals,
    round_amount,
    rounded_sum,
)
from custom_components.wattbill.cost.running_time import running_time
from custom_components.wattbill.models import LineItemKind, Run
from custom_components.wattbill.run_book import RunBook, RunChange
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol

from .command import command

# Outlives a reload of the hub entry, so open subscriptions keep receiving.
SIGNAL_RUN_CHANGED = f"{DOMAIN}_run_changed"


@callback
def async_announce(hass: HomeAssistant, book: RunBook) -> CALLBACK_TYPE:
    """Forward the book's Run changes to every panel subscription."""
    return book.async_listen(
        lambda change, run: async_dispatcher_send(hass, SIGNAL_RUN_CHANGED, change, run)
    )


def _summary(run: Run, now: datetime, decimals: int) -> dict[str, Any]:
    return {
        "id": run.id,
        "device_id": run.device_id,
        "device_name": run.device_name,
        "name": run.name,
        "started": run.started.isoformat(),
        "ended": None if run.ended is None else run.ended.isoformat(),
        "outcome": run.outcome,
        "finalised": run.finalised,
        "running_seconds": round(running_time(run, now).total_seconds()),
        "total": float(rounded_sum((i.amount for i in run.line_items), decimals)),
    }


def _detail(run: Run, now: datetime, decimals: int) -> dict[str, Any]:
    # Meter readings are long on an open Run and of no use to the panel.
    stored = {key: value for key, value in run.as_dict().items() if key != "readings"}
    return {
        **stored,
        **_summary(run, now, decimals),
        "line_items": [
            item.as_dict() | {"amount": float(round_amount(item.amount, decimals))}
            for item in run.line_items
        ],
        "subtotals": {
            kind: float(
                rounded_sum(
                    (i.amount for i in run.line_items if i.kind is kind), decimals
                )
            )
            for kind in LineItemKind
        },
    }


def _decimals(hass: HomeAssistant) -> int:
    return currency_decimals(hass.config.currency)


@command({vol.Required("type"): "wattbill/runs/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    now, decimals = dt_util.utcnow(), _decimals(hass)
    connection.send_result(
        msg["id"],
        {"runs": [_summary(run, now, decimals) for run in wattbill.book.runs()]},
    )


@command({vol.Required("type"): "wattbill/runs/subscribe"})
def _subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """First event: `{"runs": [...]}`; then `{"change": ..., "run": summary}`."""

    @callback
    def forward(change: RunChange, run: Run) -> None:
        connection.send_event(
            msg["id"],
            {"change": change, "run": _summary(run, dt_util.utcnow(), _decimals(hass))},
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_RUN_CHANGED, forward
    )
    connection.send_result(msg["id"])
    now, decimals = dt_util.utcnow(), _decimals(hass)
    connection.send_event(
        msg["id"],
        {"runs": [_summary(run, now, decimals) for run in wattbill.book.runs()]},
    )


@command({vol.Required("type"): "wattbill/runs/get", vol.Required("run_id"): str})
def _get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    run = next((r for r in wattbill.book.runs() if r.id == msg["run_id"]), None)
    if run is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Run with this id"
        )
        return
    connection.send_result(
        msg["id"], {"run": _detail(run, dt_util.utcnow(), _decimals(hass))}
    )


COMMANDS = (_list, _subscribe, _get)
