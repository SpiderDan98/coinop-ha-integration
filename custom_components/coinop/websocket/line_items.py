"""Line Items of a Run for the panel: override, reset, add, delete, save as template.

Every command answers with the Run in full, as `coinop/runs/get` does, except
saving as a template, which answers with the new template.
"""

import math
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from custom_components.coinop.cost.material import (
    GRAM,
    MILLILITRE,
    PIECES,
    change_material,
    material_line_item,
)
from custom_components.coinop.models import (
    CONSUMED_KINDS,
    VALUES,
    ConsumptionMethod,
    LineItem,
    LineItemKind,
    Run,
)
from custom_components.coinop.quantities import WATER
from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol
from custom_components.coinop.templates import template_fields

from .command import command, found
from .materials import pickable
from .runs import _send_run, _text, find_run


def _number(value: Any) -> float:
    if isinstance(value, bool) or not math.isfinite(number := float(value)):
        raise vol.Invalid("not a number")
    return number


_ITEM = {vol.Required("run_id"): str, vol.Required("line_item_id"): str}
_QUANTITY = vol.Any(None, vol.All(_number, vol.Range(min=0)))
_PRICES = {vol.Optional("unit_price"): _number, vol.Optional("amount"): _number}


async def _correct(coinop: CoinOp, run: Run) -> None:
    run.drop_fixed_flags()
    await coinop.book.async_correct(run)


def _find_item(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
    *,
    unlocked: bool = True,
) -> tuple[Run, LineItem] | None:
    """The Run and the (unlocked) Line Item the message names; answers the error if not."""
    if (run := find_run(connection, msg, coinop)) is None:
        return None
    items = (i for i in run.line_items if i.id == msg["line_item_id"])
    if (item := found(connection, msg, next(items, None), "Line Item")) is None:
        return None
    if unlocked and run.locked(item):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "Live until the Run is final"
        )
        return None
    return run, item


def _allowed(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    item: LineItem,
    values: dict[str, Any],
) -> bool:
    """Whether the Line Item may take these values; answers the error if not."""
    prices = (values.get(name) for name in ("unit_price", "amount"))
    if not item.negative_prices and any(p is not None and p < 0 for p in prices):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_INVALID_FORMAT,
            "Only Other Line Items have negative prices",
        )
        return False
    return True


@command(
    {
        vol.Required("type"): "coinop/line_items/update",
        **_ITEM,
        vol.Optional("label"): vol.Any(None, str),
        vol.Optional("unit"): str,
        vol.Optional("quantity"): _QUANTITY,
        **_PRICES,
        vol.Optional("material_id"): str,
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A new Material re-prices the Line Item first (`change_material`)."""
    if (found := _find_item(connection, msg, coinop)) is None:
        return
    run, item = found
    material_item = item.kind is LineItemKind.MATERIAL
    for field, refused, message in (
        (
            "unit",
            item.is_computed or material_item or item.kind in CONSUMED_KINDS,
            "Coin-op sets this unit",
        ),
        ("material_id", not material_item, "Only Material Line Items have one"),
    ):
        if field in msg and refused:
            connection.send_error(msg["id"], websocket_api.ERR_NOT_ALLOWED, message)
            return
    values = {name: msg[name] for name in VALUES if name in msg}
    if not _allowed(connection, msg, item, values):
        return
    if "material_id" in msg:
        if not (material := pickable(connection, msg, coinop, msg["material_id"])):
            return
        change_material(item, material)
    if "label" in msg:
        item.label = _text(msg["label"])
    if "unit" in msg:
        item.unit = msg["unit"].strip()
    if values:
        item.override(values)
    await _correct(coinop, run)
    _send_run(hass, connection, msg["id"], run)


@command({vol.Required("type"): "coinop/line_items/reset", **_ITEM})
async def _reset(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Back to the computed values; a Line Item without overrides stays as it is."""
    if (found := _find_item(connection, msg, coinop)) is None:
        return
    run, item = found
    if item.computed is not None:
        item.reset()
        await _correct(coinop, run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "coinop/line_items/add",
        vol.Required("run_id"): str,
        vol.Required("kind"): vol.All(
            vol.Coerce(LineItemKind),
            vol.In([LineItemKind.OTHER, LineItemKind.MATERIAL, LineItemKind.WATER]),
        ),
        vol.Optional("label"): vol.Any(None, str),
        vol.Optional("unit"): str,
        vol.Optional("quantity"): _QUANTITY,
        **_PRICES,
        vol.Optional("material_id"): str,
    }
)
async def _add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A Line Item entered by hand; it is added to an open Run too.

    A Material Line Item names its Material and counts g (the default) or ml,
    or pieces of a Material priced per piece, at the Material's current price;
    a Water one counts litres, one per Run; an Other one defaults to 1 piece.
    """
    if (run := find_run(connection, msg, coinop)) is None:
        return
    if msg["kind"] is LineItemKind.WATER:
        if any(i.kind is LineItemKind.WATER for i in run.line_items):
            connection.send_error(
                msg["id"], websocket_api.ERR_NOT_ALLOWED, "The Run has its Water"
            )
            return
        item = LineItem(
            id=ulid_now(),
            kind=LineItemKind.WATER,
            quantity=None,
            unit=WATER.unit,
            unit_price=0.0,
            amount=0.0,
            method=ConsumptionMethod.ENTERED,
        )
    elif msg["kind"] is LineItemKind.MATERIAL:
        if "material_id" not in msg:
            connection.send_error(
                msg["id"],
                websocket_api.ERR_INVALID_FORMAT,
                "A Material Line Item names its Material",
            )
            return
        if not (material := pickable(connection, msg, coinop, msg["material_id"])):
            return
        units = (PIECES,) if material.by_piece else (GRAM, MILLILITRE)
        if (unit := msg.get("unit", units[0])) not in units:
            connection.send_error(
                msg["id"],
                websocket_api.ERR_INVALID_FORMAT,
                f"This Material counts {' or '.join(units)}",
            )
            return
        item = material_line_item(ulid_now(), None, material, measured=False, unit=unit)
        item.label = _text(msg.get("label"))
    else:
        item = LineItem(
            id=ulid_now(),
            kind=msg["kind"],
            label=_text(msg.get("label")),
            quantity=1,
            unit=msg.get("unit", "").strip(),
            unit_price=0.0,
            amount=0.0,
        )
    values = {name: msg[name] for name in VALUES if name in msg}
    if not _allowed(connection, msg, item, values):
        return
    item.override(values)
    run.line_items.append(item)
    await _correct(coinop, run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "coinop/line_items/add_template",
        vol.Required("run_id"): str,
        vol.Required("template_id"): str,
        vol.Optional("quantity"): vol.All(_number, vol.Range(min=0)),
    }
)
async def _add_template(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A copy of the template; `quantity` replaces an entered default quantity."""
    if (run := find_run(connection, msg, coinop)) is None:
        return
    template = coinop.catalog.template(msg["template_id"])
    if (template := found(connection, msg, template, "Line Item Template")) is None:
        return
    run.line_items.append(
        template.line_item(run, dt_util.utcnow(), msg.get("quantity"))
    )
    await _correct(coinop, run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "coinop/line_items/save_as_template",
        **_ITEM,
        vol.Optional("label"): str,
    }
)
async def _save_as_template(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A new template from the Line Item's current values, under `label` if given.

    Computed Line Items have no label of their own, so they need one.
    """
    if (found := _find_item(connection, msg, coinop, unlocked=False)) is None:
        return
    _, item = found
    if (label := _text(msg.get("label")) or item.label) is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, "A template needs a label"
        )
        return
    template = await coinop.catalog.async_create_template(
        template_fields(item) | {"label": label}
    )
    connection.send_result(msg["id"], {"template": template.as_dict()})


@command({vol.Required("type"): "coinop/line_items/delete", **_ITEM})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if (found := _find_item(connection, msg, coinop)) is None:
        return
    run, item = found
    if not run.deletable(item):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "This Line Item is kept"
        )
        return
    run.line_items.remove(item)
    await _correct(coinop, run)
    _send_run(hass, connection, msg["id"], run)


COMMANDS = (_update, _reset, _add, _add_template, _save_as_template, _delete)
