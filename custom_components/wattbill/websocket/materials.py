"""The Materials catalogue for the panel: list, create, edit, archive, restore, delete.

Material fields travel nested under `material`, since `type` names the command.
Changes reach open panels through the catalogue subscription (`catalog.py`).
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.materials import (
    MATERIAL_TYPES,
    Material,
    MaterialForm,
    PackUnit,
)
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol

from .command import command

_TEXT = vol.All(str, vol.Strip, vol.Length(min=1))
_POSITIVE = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))
_PRICE = {
    vol.Required("source"): "fixed",
    vol.Required("pack_price"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Required("pack_size"): _POSITIVE,
    vol.Optional("pack_unit"): vol.In([unit.value for unit in PackUnit]),
}
_FIELDS = {
    "name": _TEXT,
    "form": vol.In([form.value for form in MaterialForm]),
    "type": _TEXT,
    "density": _POSITIVE,
    "price": _PRICE,
    "vendor": vol.Any(None, _TEXT),
    "colour": vol.Any(None, vol.Match(r"^#[0-9a-fA-F]{6}$")),
    "diameter": vol.Any(None, _POSITIVE),
    "default_for_type": bool,
}
_REQUIRED = ("name", "form", "type", "density", "price")
_MATERIAL_ID = vol.Required("material_id")


def material_dict(material: Material) -> dict[str, Any]:
    return material.as_dict() | {"price_per_gram": material.price_per_gram}


def _found(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> Material | None:
    material = wattbill.catalog.material(msg["material_id"])
    if material is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Material with this id"
        )
    return material


def pickable(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
    material_id: str,
) -> Material | None:
    """The Material if it can be picked (it exists and isn't archived); else answers the error."""
    material = wattbill.catalog.material(material_id)
    if material is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "No Material with this id"
        )
    elif material.archived:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "This Material is archived"
        )
        return None
    return material


@command({vol.Required("type"): "wattbill/materials/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    connection.send_result(
        msg["id"],
        {"materials": [material_dict(m) for m in wattbill.catalog.materials()]},
    )


@command({vol.Required("type"): "wattbill/materials/types"})
def _types(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Built-in types with their form and density, for suggestions and pre-filling."""
    connection.send_result(
        msg["id"],
        {
            "types": [
                {"type": name, "form": form, "density": density}
                for name, (form, density) in MATERIAL_TYPES.items()
            ]
        },
    )


@command(
    {
        vol.Required("type"): "wattbill/materials/create",
        vol.Required("material"): {
            (vol.Required if key in _REQUIRED else vol.Optional)(key): schema
            for key, schema in _FIELDS.items()
        },
    }
)
async def _create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    material = await wattbill.catalog.async_create_material(msg["material"])
    connection.send_result(msg["id"], {"material": material_dict(material)})


@command(
    {
        vol.Required("type"): "wattbill/materials/update",
        _MATERIAL_ID: str,
        vol.Required("material"): {
            vol.Optional(key): schema for key, schema in _FIELDS.items()
        },
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if material := _found(connection, msg, wattbill):
        updated = await wattbill.catalog.async_update_material(
            material, msg["material"]
        )
        connection.send_result(msg["id"], {"material": material_dict(updated)})


@command({vol.Required("type"): "wattbill/materials/archive", _MATERIAL_ID: str})
async def _archive(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if material := _found(connection, msg, wattbill):
        await wattbill.catalog.async_archive_material(material)
        connection.send_result(msg["id"], {"material": material_dict(material)})


@command({vol.Required("type"): "wattbill/materials/restore", _MATERIAL_ID: str})
async def _restore(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if material := _found(connection, msg, wattbill):
        await wattbill.catalog.async_restore_material(material)
        connection.send_result(msg["id"], {"material": material_dict(material)})


@command({vol.Required("type"): "wattbill/materials/delete", _MATERIAL_ID: str})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """Answers `{"deleted": false}` when a Run uses the Material: it is archived."""
    if material := _found(connection, msg, wattbill):
        deleted = await wattbill.catalog.async_delete_material(material)
        connection.send_result(msg["id"], {"deleted": deleted})


COMMANDS = (_list, _types, _create, _update, _archive, _restore, _delete)
