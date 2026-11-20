"""The Line Item Templates catalogue for the panel: create, edit, delete.

Template fields travel nested under `template`, since `type` names the command.
Changes reach open panels through the catalogue subscription (`catalog.py`);
Runs keep their copies whatever happens to a template.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.models import QuantityBasis
from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol
from custom_components.coinop.templates import LineItemTemplate

from .command import command, found
from .line_items import _number

FIELDS = {
    "label": vol.All(str, vol.Strip, vol.Length(min=1)),
    "unit": vol.All(str, vol.Strip),
    "unit_price": _number,
    "default_quantity": vol.All(_number, vol.Range(min=0)),
    "basis": vol.Coerce(QuantityBasis),
}
_DEFAULTS = {"unit": "", "default_quantity": 1}
_TEMPLATE_ID = vol.Required("template_id")


def find_template(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], coinop: CoinOp
) -> LineItemTemplate | None:
    template = coinop.catalog.template(msg["template_id"])
    return found(connection, msg, template, "Line Item Template")


@command(
    {
        vol.Required("type"): "coinop/templates/create",
        vol.Required("template"): {
            (
                vol.Optional(key, default=_DEFAULTS[key])
                if key in _DEFAULTS
                else vol.Required(key)
            ): schema
            for key, schema in FIELDS.items()
        },
    }
)
async def _create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    template = await coinop.catalog.async_create_template(msg["template"])
    connection.send_result(msg["id"], {"template": template.as_dict()})


@command(
    {
        vol.Required("type"): "coinop/templates/update",
        _TEMPLATE_ID: str,
        vol.Required("template"): {
            vol.Optional(key): schema for key, schema in FIELDS.items()
        },
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if template := find_template(connection, msg, coinop):
        updated = await coinop.catalog.async_update_template(template, msg["template"])
        connection.send_result(msg["id"], {"template": updated.as_dict()})


@command({vol.Required("type"): "coinop/templates/delete", _TEMPLATE_ID: str})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Also leaves every Device's automatic templates; Runs keep their copies."""
    if template := find_template(connection, msg, coinop):
        await coinop.catalog.async_delete_template(template)
        await coinop.settings.async_drop_template(template.id)
        connection.send_result(msg["id"], {})


COMMANDS = (_create, _update, _delete)
