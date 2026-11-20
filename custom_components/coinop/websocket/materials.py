"""The Materials catalogue for the panel: list, create, edit, archive, restore, delete.

Material fields travel nested under `material`, since `type` names the command.
Changes reach open panels through the catalogue subscription (`catalog.py`).
"""

from collections.abc import Awaitable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.materials import (
    MATERIAL_TYPES,
    Material,
    MaterialForm,
    PackUnit,
)
from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol

from .command import command, found
from .spoolman import spoolman_call

_TEXT = vol.All(str, vol.Strip, vol.Length(min=1))
_POSITIVE = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))
_FIXED_PRICE = {
    vol.Required("source"): "fixed",
    vol.Required("pack_price"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Required("pack_size"): _POSITIVE,
    vol.Optional("pack_unit"): vol.In([unit.value for unit in PackUnit]),
}
# Linking reads the price and the synced fields from Spoolman; a new Material
# comes from a Filament through `create_from_spoolman`.
_LINK = {vol.Required("source"): "spoolman", vol.Required("filament_id"): int}
_FIELDS = {
    "name": _TEXT,
    "form": vol.In([form.value for form in MaterialForm]),
    "type": _TEXT,
    "density": vol.Any(None, _POSITIVE),
    "price": _FIXED_PRICE,
    "vendor": vol.Any(None, _TEXT),
    "colour": vol.Any(None, vol.Match(r"^#[0-9a-fA-F]{6}$")),
    "diameter": vol.Any(None, _POSITIVE),
    "default_for_type": bool,
}
# A density is checked once the pack unit is known (`Catalog` raises ValueError).
_REQUIRED = ("name", "form", "type", "price")
_MATERIAL_ID = vol.Required("material_id")


def material_dict(material: Material) -> dict[str, Any]:
    return material.as_dict() | {
        "price_per_gram": material.price_per_gram,
        "price_per_piece": material.price_per_piece,
    }


async def _saved(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    save: Awaitable[Material],
) -> Material | None:
    """The saved Material; a Material by weight or volume without a density answers `invalid_format`."""
    try:
        return await save
    except ValueError as error:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(error))
        return None


def _found(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], coinop: CoinOp
) -> Material | None:
    return found(
        connection, msg, coinop.catalog.material(msg["material_id"]), "Material"
    )


def pickable(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
    material_id: str,
) -> Material | None:
    """The Material if it can be picked (it exists and isn't archived); else answers the error."""
    material = found(connection, msg, coinop.catalog.material(material_id), "Material")
    if material is not None and material.archived:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "This Material is archived"
        )
        return None
    return material


@command({vol.Required("type"): "coinop/materials/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    connection.send_result(
        msg["id"],
        {"materials": [material_dict(m) for m in coinop.catalog.materials()]},
    )


@command({vol.Required("type"): "coinop/materials/types"})
def _types(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Built-in types with their form, density and pack unit, for suggestions and pre-filling."""
    connection.send_result(
        msg["id"],
        {
            "types": [
                {"type": name, "form": form, "density": density, "pack_unit": unit}
                for name, (form, density, unit) in MATERIAL_TYPES.items()
            ]
        },
    )


@command(
    {
        vol.Required("type"): "coinop/materials/create",
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
    coinop: CoinOp,
) -> None:
    if material := await _saved(
        connection, msg, coinop.catalog.async_create_material(msg["material"])
    ):
        connection.send_result(msg["id"], {"material": material_dict(material)})


@command(
    {
        vol.Required("type"): "coinop/materials/update",
        _MATERIAL_ID: str,
        vol.Required("material"): {
            vol.Optional(key): schema
            for key, schema in (
                _FIELDS | {"price": vol.Any(_FIXED_PRICE, _LINK)}
            ).items()
        },
    }
)
async def _update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if not (material := _found(connection, msg, coinop)):
        return
    changes = msg["material"]
    if changes.get("price", {}).get("source") == "spoolman":
        if material.by_piece:
            connection.send_error(
                msg["id"],
                websocket_api.ERR_NOT_ALLOWED,
                "A Material priced per piece can't be linked to Spoolman",
            )
            return
        filament_id = changes["price"]["filament_id"]
        updated = await spoolman_call(
            connection,
            msg,
            coinop.spoolman.async_link(material, filament_id, changes),
        )
    else:
        updated = await _saved(
            connection, msg, coinop.catalog.async_update_material(material, changes)
        )
    if updated:
        connection.send_result(msg["id"], {"material": material_dict(updated)})


@command({vol.Required("type"): "coinop/materials/archive", _MATERIAL_ID: str})
async def _archive(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if material := _found(connection, msg, coinop):
        await coinop.catalog.async_archive_material(material)
        connection.send_result(msg["id"], {"material": material_dict(material)})


@command({vol.Required("type"): "coinop/materials/restore", _MATERIAL_ID: str})
async def _restore(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    if material := _found(connection, msg, coinop):
        await coinop.catalog.async_restore_material(material)
        connection.send_result(msg["id"], {"material": material_dict(material)})


@command({vol.Required("type"): "coinop/materials/delete", _MATERIAL_ID: str})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Answers `{"deleted": false}` when a Run uses the Material: it is archived."""
    if material := _found(connection, msg, coinop):
        deleted = await coinop.catalog.async_delete_material(material)
        connection.send_result(msg["id"], {"deleted": deleted})


@command(
    {
        vol.Required("type"): "coinop/materials/create_from_spoolman",
        vol.Required("filament_id"): int,
    }
)
async def _create_from_spoolman(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """A Material linked to the Filament, named and filled in from it."""
    material = await spoolman_call(
        connection, msg, coinop.spoolman.async_create_material(msg["filament_id"])
    )
    if material:
        connection.send_result(msg["id"], {"material": material_dict(material)})


COMMANDS = (
    _list,
    _types,
    _create,
    _create_from_spoolman,
    _update,
    _archive,
    _restore,
    _delete,
)
