"""The Line Item Templates catalogue for the panel: create, edit, delete.

Template fields travel nested under `template`, since `type` names the command.
Changes reach open panels through the catalogue subscription (`catalog.py`);
Runs keep their copies whatever happens to a template.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.models import QuantityBasis
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.templates import LineItemTemplate

from .command import command
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


def _found(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> LineItemTemplate | None:
    template = wattbill.catalog.template(msg["template_id"])
    if template is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Line Item Template with this id"
        )
    return template


@command(
    {
        vol.Required("type"): "wattbill/templates/create",
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
    wattbill: WattBill,
) -> None:
    template = await wattbill.catalog.async_create_template(msg["template"])
    connection.send_result(msg["id"], {"template": template.as_dict()})


@command(
    {
        vol.Required("type"): "wattbill/templates/update",
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
    wattbill: WattBill,
) -> None:
    if template := _found(connection, msg, wattbill):
        updated = await wattbill.catalog.async_update_template(
            template, msg["template"]
        )
        connection.send_result(msg["id"], {"template": updated.as_dict()})


@command({vol.Required("type"): "wattbill/templates/delete", _TEMPLATE_ID: str})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Also leaves every Device's automatic templates; Runs keep their copies."""
    if template := _found(connection, msg, wattbill):
        await wattbill.catalog.async_delete_template(template)
        connection.send_result(msg["id"], {})


COMMANDS = (_create, _update, _delete)
