"""Runs for the panel: the gallery list (live via subscription), one Run in full,
and the user's corrections: fields, Flags, "End Run now" and deletion.

Summaries carry what a gallery tile shows (with its Cover Image); `get` returns
the stored Run with amounts rounded to the currency, the derived subtotals and
total, and every image with the URLs to fetch it from.
Corrections never recompute a cost, except that a corrected Program re-applies
its defaults (ADR 0002).
"""

from collections.abc import Container
from datetime import datetime
from typing import Any, cast

from homeassistant.components import websocket_api
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.util import dt as dt_util

from custom_components.coinop.aggregates import run_measures
from custom_components.coinop.const import DOMAIN
from custom_components.coinop.cost.projection import projected_total
from custom_components.coinop.cost.rounding import (
    currency_decimals,
    round_amount,
    rounded_sum,
)
from custom_components.coinop.cost.running_time import running_time
from custom_components.coinop.device_config import Capability
from custom_components.coinop.images import image_info, upload_rules
from custom_components.coinop.models import (
    ImageKind,
    LineItem,
    LineItemKind,
    Outcome,
    ProjectedPart,
    Projection,
    Run,
)
from custom_components.coinop.run_book import RunBook, RunChange
from custom_components.coinop.runtime import CoinOp, CoinOpConfigEntry
from custom_components.coinop.schema import vol
from custom_components.coinop.tags import tag_name
from custom_components.coinop.tracker import DeviceTracker

from .command import command, found

# Outlives a reload of the hub entry, so open subscriptions keep receiving.
SIGNAL_RUN_CHANGED = f"{DOMAIN}_run_changed"


@callback
def async_announce(hass: HomeAssistant, book: RunBook) -> CALLBACK_TYPE:
    """Forward the book's Run changes to every panel subscription."""
    return book.async_listen(
        lambda change, run: async_dispatcher_send(hass, SIGNAL_RUN_CHANGED, change, run)
    )


def _cover_kind(hass: HomeAssistant, run: Run) -> ImageKind:
    """Looked up on each call: a subscription outlives a reload of the hub entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        return ImageKind.THUMBNAIL
    return cast(CoinOpConfigEntry, entries[0]).runtime_data.settings.cover_kind(
        run.device_id
    )


def _summary(
    hass: HomeAssistant, run: Run, now: datetime, decimals: int
) -> dict[str, Any]:
    total = rounded_sum((i.amount for i in run.line_items), decimals)
    projected = projected_total(run, decimals)
    ends_at = None if run.projection is None else run.projection.ends_at
    return {
        "id": run.id,
        "device_id": run.device_id,
        "device_name": run.device_name,
        "name": run.name,
        "program": run.program,
        "started": run.started.isoformat(),
        "ended": None if run.ended is None else run.ended.isoformat(),
        "outcome": run.outcome,
        "finalised": run.finalised,
        "running_seconds": round(running_time(run, now).total_seconds()),
        "total": float(total),
        "projected_total": None if projected is None else float(projected),
        "projected_end": None if ends_at is None else ends_at.isoformat(),
        "part_count": run.part_count,
        "cost_per_part": None
        if run.part_count is None
        else float(round_amount(float(total) / run.part_count, decimals)),
        "flags": list(run.flags),
        "tags": list(run.tags),
        "cover": None
        if (cover := run.cover(_cover_kind(hass, run))) is None
        else image_info(run, cover),
    }


def _line_item(run: Run, item: LineItem, decimals: int) -> dict[str, Any]:
    def rounded(values: dict[str, Any]) -> dict[str, Any]:
        return values | {"amount": float(round_amount(values["amount"], decimals))}

    return rounded(item.as_dict()) | {
        "computed": None if item.computed is None else rounded(item.computed),
        "locked": run.locked(item),
        "deletable": run.deletable(item),
    }


def _in_order(parts: Container[ProjectedPart]) -> list[ProjectedPart]:
    return [part for part in ProjectedPart if part in parts]


def _detail(
    hass: HomeAssistant, run: Run, now: datetime, decimals: int
) -> dict[str, Any]:
    # Meter readings are long on an open Run and of no use to the panel.
    stored = run.as_dict()
    projection = run.projection or Projection({}, None)
    for timeline in stored.get("timelines", {}).values():
        del timeline["readings"]
    return {
        **stored,
        **_summary(hass, run, now, decimals),
        "line_items": [_line_item(run, item, decimals) for item in run.line_items],
        "images": [image_info(run, image) for image in run.images_in_order],
        "uploads": upload_rules(),
        "projected_parts": _in_order(projection.rests),
        "projected_pending": _in_order(projection.pending),
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


@command({vol.Required("type"): "coinop/runs/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    now, decimals = dt_util.utcnow(), _decimals(hass)
    connection.send_result(
        msg["id"],
        {"runs": [_summary(hass, run, now, decimals) for run in coinop.book.runs()]},
    )


@command({vol.Required("type"): "coinop/runs/subscribe"})
def _subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """First event: `{"runs": [...]}`; then `{"change": ..., "run": summary}`."""

    @callback
    def forward(change: RunChange, run: Run) -> None:
        connection.send_event(
            msg["id"],
            {
                "change": change,
                "run": _summary(hass, run, dt_util.utcnow(), _decimals(hass)),
            },
        )

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_RUN_CHANGED, forward
    )
    connection.send_result(msg["id"])
    now, decimals = dt_util.utcnow(), _decimals(hass)
    connection.send_event(
        msg["id"],
        {"runs": [_summary(hass, run, now, decimals) for run in coinop.book.runs()]},
    )


def find_run(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
    run_id: str | None = None,
) -> Run | None:
    """The Run `run_id` (else `msg["run_id"]`) names; answers `not_found` if none."""
    return found(connection, msg, coinop.book.run(run_id or msg["run_id"]), "Run")


def _send_run(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg_id: int,
    run: Run,
) -> None:
    connection.send_result(
        msg_id, {"run": _detail(hass, run, dt_util.utcnow(), _decimals(hass))}
    )


@command({vol.Required("type"): "coinop/runs/get", vol.Required("run_id"): str})
def _get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if run := find_run(connection, msg, coinop):
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
        vol.Required("type"): "coinop/runs/update",
        vol.Required("run_id"): str,
        vol.Optional("name"): vol.Any(None, str),
        vol.Optional("note"): vol.Any(None, str),
        vol.Optional("started"): _moment,
        vol.Optional("ended"): _moment,
        vol.Optional("outcome"): vol.Coerce(Outcome),
        vol.Optional("part_count"): vol.All(int, vol.Range(min=1)),
        vol.Optional("program"): vol.Any(None, str),
        vol.Optional("tags"): [tag_name],
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if (run := find_run(connection, msg, coinop)) is None:
        return
    if not run.finalised and any(key in msg for key in _FINAL_FIELDS):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run is not final yet"
        )
        return
    if "part_count" in msg and run.part_count is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run has no Part Count"
        )
        return
    if "program" in msg and not _has_program(coinop, run):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run has no Program"
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
    if "program" in msg:
        if tracker := _tracker(coinop, run.device_id):
            tracker.correct_program(run, _text(msg["program"]))
        else:
            run.program = _text(msg["program"])
    if "tags" in msg:
        run.tags = await coinop.catalog.async_add_tags(msg["tags"])
    await coinop.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "coinop/runs/create",
        vol.Required("device_id"): str,
        vol.Optional("name"): vol.Any(None, str),
        vol.Required("started"): _moment,
        vol.Required("ended"): _moment,
        vol.Required("outcome"): vol.Coerce(Outcome),
        vol.Optional("tags"): [tag_name],
        vol.Optional("program"): vol.Any(None, str),
    }
)
async def _create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A manual Run, e.g. for a print made while Home Assistant was down."""
    tracker = found(connection, msg, _tracker(coinop, msg["device_id"]), "Device")
    if tracker is None:
        return
    if not msg["started"] < msg["ended"] <= dt_util.utcnow():
        connection.send_error(
            msg["id"],
            websocket_api.ERR_INVALID_FORMAT,
            "A manual Run ends after it starts, and not in the future",
        )
        return
    program = _text(msg.get("program"))
    if program is not None and not tracker.has_programs:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Device has no Programs"
        )
        return
    run = await tracker.async_create_run(
        msg["started"],
        msg["ended"],
        msg["outcome"],
        _text(msg.get("name")),
        await coinop.catalog.async_add_tags(msg["tags"]) if "tags" in msg else None,
        program,
    )
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "coinop/runs/clear_flag",
        vol.Required("run_id"): str,
        vol.Required("flag"): str,
    }
)
async def _clear_flag(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if (run := find_run(connection, msg, coinop)) is None:
        return
    if msg["flag"] in run.flags:
        run.flags.remove(msg["flag"])
        await coinop.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


def _has_program(coinop: CoinOp, run: Run) -> bool:
    """Whether the Run's Device Type has Programs; for a removed Device, whether it had one."""
    device = next((d for d in coinop.devices if d.device_id == run.device_id), None)
    if device is None:
        return run.program is not None
    return Capability.PROGRAM in device.capabilities


def _tracker(coinop: CoinOp, device_id: str) -> DeviceTracker | None:
    return next(
        (
            tracker
            for device, tracker in zip(coinop.devices, coinop.trackers, strict=True)
            if device.device_id == device_id
        ),
        None,
    )


@command({vol.Required("type"): "coinop/runs/end", vol.Required("run_id"): str})
def _end(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """End Run now: the open Run ends as Unknown, finalised like any other end."""
    if (run := find_run(connection, msg, coinop)) is None:
        return
    tracker = _tracker(coinop, run.device_id)
    if run.ended is not None or tracker is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run is not open"
        )
        return
    tracker.async_end_run()
    _send_run(hass, connection, msg["id"], run)


def _deletable(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], coinop: CoinOp
) -> list[Run] | None:
    """The Runs `msg["run_ids"]` names, if all exist and are final."""
    runs = [run for run_id in msg["run_ids"] if (run := coinop.book.run(run_id))]
    complete = runs if len(runs) == len(msg["run_ids"]) else None
    if found(connection, msg, complete, "Run") is None:
        return None
    if not all(run.finalised for run in runs):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "End the Run before deleting it"
        )
        return None
    return runs


_DELETE_SCHEMA = {vol.Required("run_ids"): vol.All([str], vol.Unique())}


@command({vol.Required("type"): "coinop/runs/delete_preview", **_DELETE_SCHEMA})
def _delete_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """What `delete` would take off the sensor totals, for the confirmation."""
    if (runs := _deletable(connection, msg, coinop)) is not None:
        connection.send_result(
            msg["id"], {"drop": run_measures(runs, dt_util.utcnow(), _decimals(hass))}
        )


@command({vol.Required("type"): "coinop/runs/delete", **_DELETE_SCHEMA})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if (runs := _deletable(connection, msg, coinop)) is None:
        return
    drop = run_measures(runs, dt_util.utcnow(), _decimals(hass))
    await coinop.book.async_delete(runs)
    connection.send_result(msg["id"], {"drop": drop})


COMMANDS = (
    _list,
    _subscribe,
    _get,
    _update,
    _create,
    _clear_flag,
    _end,
    _delete_preview,
    _delete,
)
