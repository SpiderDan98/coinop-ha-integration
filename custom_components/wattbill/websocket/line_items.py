"""Line Items of a Run for the panel: override, reset, add, delete, save as template.

Every command answers with the Run in full, as `wattbill/runs/get` does, except
saving as a template, which answers with the new template.
"""

import math
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from custom_components.wattbill.models import VALUES, LineItem, LineItemKind, Run
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.templates import template_fields

from .command import command
from .runs import _find, _send_run, _text


def _number(value: Any) -> float:
    if isinstance(value, bool) or not math.isfinite(number := float(value)):
        raise vol.Invalid("not a number")
    return number


_ITEM = {vol.Required("run_id"): str, vol.Required("line_item_id"): str}
_QUANTITY = vol.Any(None, vol.All(_number, vol.Range(min=0)))
_PRICES = {vol.Optional("unit_price"): _number, vol.Optional("amount"): _number}


def _find_item(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
    *,
    unlocked: bool = True,
) -> tuple[Run, LineItem] | None:
    """The Run and the (unlocked) Line Item the message names; answers the error if not."""
    if (run := _find(connection, msg, wattbill)) is None:
        return None
    item = next((i for i in run.line_items if i.id == msg["line_item_id"]), None)
    if item is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Line Item with this id"
        )
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
        vol.Required("type"): "wattbill/line_items/update",
        **_ITEM,
        vol.Optional("label"): vol.Any(None, str),
        vol.Optional("unit"): str,
        vol.Optional("quantity"): _QUANTITY,
        **_PRICES,
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (found := _find_item(connection, msg, wattbill)) is None:
        return
    run, item = found
    if "unit" in msg and item.is_computed:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "WattBill sets this unit"
        )
        return
    values = {name: msg[name] for name in VALUES if name in msg}
    if not _allowed(connection, msg, item, values):
        return
    if "label" in msg:
        item.label = _text(msg["label"])
    if "unit" in msg:
        item.unit = msg["unit"].strip()
    if values:
        item.override(values)
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command({vol.Required("type"): "wattbill/line_items/reset", **_ITEM})
async def _reset(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Back to the computed values; a Line Item without overrides stays as it is."""
    if (found := _find_item(connection, msg, wattbill)) is None:
        return
    run, item = found
    if item.computed is not None:
        item.reset()
        await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "wattbill/line_items/add",
        vol.Required("run_id"): str,
        vol.Required("kind"): vol.All(vol.Coerce(LineItemKind), LineItemKind.OTHER),
        vol.Optional("label"): vol.Any(None, str),
        vol.Optional("unit", default=""): str,
        vol.Optional("quantity", default=1): _QUANTITY,
        **_PRICES,
    }
)
async def _add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """A Line Item entered by hand; it is added to an open Run too."""
    if (run := _find(connection, msg, wattbill)) is None:
        return
    item = LineItem(
        id=ulid_now(),
        kind=msg["kind"],
        label=_text(msg.get("label")),
        quantity=None,
        unit=msg["unit"].strip(),
        unit_price=0.0,
        amount=0.0,
    )
    values = {name: msg[name] for name in VALUES if name in msg}
    if not _allowed(connection, msg, item, values):
        return
    item.override(values)
    run.line_items.append(item)
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "wattbill/line_items/add_template",
        vol.Required("run_id"): str,
        vol.Required("template_id"): str,
        vol.Optional("quantity"): vol.All(_number, vol.Range(min=0)),
    }
)
async def _add_template(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """A copy of the template; `quantity` replaces an entered default quantity."""
    if (run := _find(connection, msg, wattbill)) is None:
        return
    if (template := wattbill.catalog.template(msg["template_id"])) is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Line Item Template with this id"
        )
        return
    run.line_items.append(
        template.line_item(run, dt_util.utcnow(), msg.get("quantity"))
    )
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command(
    {
        vol.Required("type"): "wattbill/line_items/save_as_template",
        **_ITEM,
        vol.Optional("label"): str,
    }
)
async def _save_as_template(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """A new template from the Line Item's current values, under `label` if given.

    Computed Line Items have no label of their own, so they need one.
    """
    if (found := _find_item(connection, msg, wattbill, unlocked=False)) is None:
        return
    _, item = found
    if (label := _text(msg.get("label")) or item.label) is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, "A template needs a label"
        )
        return
    template = await wattbill.catalog.async_create_template(
        template_fields(item) | {"label": label}
    )
    connection.send_result(msg["id"], {"template": template.as_dict()})


@command({vol.Required("type"): "wattbill/line_items/delete", **_ITEM})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (found := _find_item(connection, msg, wattbill)) is None:
        return
    run, item = found
    if not run.deletable(item):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "This Line Item is kept"
        )
        return
    run.line_items.remove(item)
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


COMMANDS = (_update, _reset, _add, _add_template, _save_as_template, _delete)
