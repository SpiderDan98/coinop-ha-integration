"""Runs for the panel: the gallery list (live via subscription), one Run in full,
and the user's corrections: fields, Flags, "End Run now" and deletion.

Summaries carry what a gallery tile shows (with its Cover Image); `get` returns
the stored Run with amounts rounded to the currency, the derived subtotals and
total, and every image with the URLs to fetch it from.
Corrections never recompute a cost (ADR 0002).
"""

from datetime import datetime
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.util import dt as dt_util

from custom_components.wattbill.aggregates import run_measures
from custom_components.wattbill.const import DOMAIN
from custom_components.wattbill.cost.rounding import (
    currency_decimals,
    round_amount,
    rounded_sum,
)
from custom_components.wattbill.cost.running_time import running_time
from custom_components.wattbill.images import image_info
from custom_components.wattbill.models import LineItem, LineItemKind, Outcome, Run
from custom_components.wattbill.run_book import RunBook, RunChange
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.tags import tag_name

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
    total = rounded_sum((i.amount for i in run.line_items), decimals)
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
        "total": float(total),
        "part_count": run.part_count,
        "cost_per_part": float(round_amount(float(total) / run.part_count, decimals)),
        "flags": list(run.flags),
        "tags": list(run.tags),
        "cover": None if (cover := run.cover) is None else image_info(run, cover),
    }


def _line_item(run: Run, item: LineItem, decimals: int) -> dict[str, Any]:
    def rounded(values: dict[str, Any]) -> dict[str, Any]:
        return values | {"amount": float(round_amount(values["amount"], decimals))}

    return rounded(item.as_dict()) | {
        "computed": None if item.computed is None else rounded(item.computed),
        "locked": run.locked(item),
        "deletable": run.deletable(item),
    }


def _detail(run: Run, now: datetime, decimals: int) -> dict[str, Any]:
    # Meter readings are long on an open Run and of no use to the panel.
    stored = {key: value for key, value in run.as_dict().items() if key != "readings"}
    return {
        **stored,
        **_summary(run, now, decimals),
        "line_items": [_line_item(run, item, decimals) for item in run.line_items],
        "images": [image_info(run, image) for image in run.images_in_order],
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


def _find(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> Run | None:
    """The Run `msg["run_id"]` names; answers `not_found` when there is none."""
    if (run := wattbill.book.run(msg["run_id"])) is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Run with this id"
        )
    return run


def _send_run(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg_id: int,
    run: Run,
) -> None:
    connection.send_result(
        msg_id, {"run": _detail(run, dt_util.utcnow(), _decimals(hass))}
    )


@command({vol.Required("type"): "wattbill/runs/get", vol.Required("run_id"): str})
def _get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if run := _find(connection, msg, wattbill):
        _send_run(hass, connection, msg["id"], run)


def _moment(value: Any) -> datetime:
    moment = cv.datetime(value)
    if moment.tzinfo is None:
        raise vol.Invalid("a time needs its UTC offset")
    return dt_util.as_utc(moment)


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


# Start, end and Outcome belong to the Run engine until it has finalised the Run.
_FINAL_FIELDS = ("started", "ended", "outcome")


@command(
    {
        vol.Required("type"): "wattbill/runs/update",
        vol.Required("run_id"): str,
        vol.Optional("name"): vol.Any(None, str),
        vol.Optional("note"): vol.Any(None, str),
        vol.Optional("started"): _moment,
        vol.Optional("ended"): _moment,
        vol.Optional("outcome"): vol.Coerce(Outcome),
        vol.Optional("part_count"): vol.All(int, vol.Range(min=1)),
        vol.Optional("tags"): [tag_name],
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (run := _find(connection, msg, wattbill)) is None:
        return
    if not run.finalised and any(key in msg for key in _FINAL_FIELDS):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run is not final yet"
        )
        return
    started, ended = msg.get("started", run.started), msg.get("ended", run.ended)
    if ended is not None and ended <= started:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, "A Run ends after it starts"
        )
        return
    run.started, run.ended = started, ended
    if "name" in msg:
        run.name = _text(msg["name"])
    if "note" in msg:
        run.note = _text(msg["note"])
    run.outcome = msg.get("outcome", run.outcome)
    run.part_count = msg.get("part_count", run.part_count)
    if "tags" in msg:
        run.tags = await wattbill.catalog.async_add_tags(msg["tags"])
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "wattbill/runs/clear_flag",
        vol.Required("run_id"): str,
        vol.Required("flag"): str,
    }
)
async def _clear_flag(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (run := _find(connection, msg, wattbill)) is None:
        return
    if msg["flag"] in run.flags:
        run.flags.remove(msg["flag"])
        await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command({vol.Required("type"): "wattbill/runs/end", vol.Required("run_id"): str})
def _end(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """End Run now: the open Run ends as Unknown, finalised like any other end."""
    if (run := _find(connection, msg, wattbill)) is None:
        return
    tracker = next(
        (
            tracker
            for device, tracker in zip(wattbill.devices, wattbill.trackers, strict=True)
            if device.device_id == run.device_id
        ),
        None,
    )
    if run.ended is not None or tracker is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run is not open"
        )
        return
    tracker.async_end_run()
    _send_run(hass, connection, msg["id"], run)


def _deletable(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> list[Run] | None:
    """The Runs `msg["run_ids"]` names, if all exist and are final."""
    runs = [wattbill.book.run(run_id) for run_id in msg["run_ids"]]
    found = [run for run in runs if run is not None]
    if len(found) < len(runs):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Run with this id"
        )
        return None
    if not all(run.finalised for run in found):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "End the Run before deleting it"
        )
        return None
    return found


_DELETE_SCHEMA = {vol.Required("run_ids"): vol.All([str], vol.Unique())}


@command({vol.Required("type"): "wattbill/runs/delete_preview", **_DELETE_SCHEMA})
def _delete_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """What `delete` would take off the sensor totals, for the confirmation."""
    if (runs := _deletable(connection, msg, wattbill)) is not None:
        connection.send_result(
            msg["id"], {"drop": run_measures(runs, dt_util.utcnow(), _decimals(hass))}
        )


@command({vol.Required("type"): "wattbill/runs/delete", **_DELETE_SCHEMA})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (runs := _deletable(connection, msg, wattbill)) is None:
        return
    drop = run_measures(runs, dt_util.utcnow(), _decimals(hass))
    await wattbill.book.async_delete(runs)
    connection.send_result(msg["id"], {"drop": drop})


COMMANDS = (
    _list,
    _subscribe,
    _get,
    _update,
    _clear_flag,
    _end,
    _delete_preview,
    _delete,
)
