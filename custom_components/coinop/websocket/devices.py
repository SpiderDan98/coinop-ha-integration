"""Devices for the Devices tab: HA-side settings (read-only) and panel settings.

Removed Devices are not listed; their Runs keep `device_id` and `device_name`.
"""

from statistics import fmean
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.coinop.device_config import Capability, DeviceConfig
from custom_components.coinop.device_inputs import offered_values
from custom_components.coinop.device_settings import (
    AUTOMATIC_TEMPLATES,
    DEFAULT_MATERIAL,
    DOSES,
    PROGRAM_DEFAULTS,
    TAGS_FOR_NEW_RUNS,
)
from custom_components.coinop.models import (
    ConsumptionMethod,
    LineItemKind,
    Outcome,
    Run,
)
from custom_components.coinop.runtime import CoinOp
from custom_components.coinop.schema import vol

from .command import command, found
from .materials import pickable


def _known_programs(
    hass: HomeAssistant, coinop: CoinOp, device: DeviceConfig
) -> list[str]:
    """The Program input's offered values, then other Programs of its Runs A-Z."""
    offered = (
        offered_values(hass, entity_id, device.program_attribute)
        if (entity_id := device.program_entity_id)
        else []
    )
    ran = sorted(
        {
            run.program
            for run in coinop.book.runs()
            if run.device_id == device.device_id and run.program
        },
        key=str.casefold,
    )
    return list(dict.fromkeys(p for v in [*offered, *ran] if (p := v.strip())))


@command({vol.Required("type"): "coinop/devices/list"})
def _list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    connection.send_result(
        msg["id"],
        {
            "devices": [
                {
                    "id": device.device_id,
                    "name": device.name,
                    "type": device.device_type,
                    "capabilities": sorted(device.capabilities),
                    "ha_settings": {
                        key: value
                        for key, value in device.flow_data.items()
                        if key != "device_type"
                    },
                    "settings": coinop.settings.get(device.device_id),
                    "known_programs": _known_programs(hass, coinop, device),
                }
                for device in coinop.devices
            ]
        },
    )


@command(
    {
        vol.Required("type"): "coinop/devices/update_settings",
        vol.Required("device_id"): str,
        vol.Required("settings"): dict,
    }
)
async def _update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """Change the named panel settings; returns all of the Device's panel settings.

    Naming a Tag that doesn't exist yet creates it; automatic templates must exist;
    the default Material and a new Dose's Material must exist and not be archived,
    and only a Device Type with Doses has a Dose list. Only a Dose counted in g or
    ml can have a stock input.
    """
    device_id = msg["device_id"]
    device = next((d for d in coinop.devices if d.device_id == device_id), None)
    if found(connection, msg, device, "Device") is None:
        return
    assert device is not None
    try:
        changes = coinop.settings.validate(msg["settings"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    if DOSES in changes and Capability.DOSES not in device.capabilities:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_ALLOWED, "This Device has no Doses"
        )
        return
    kept = {
        (dose["id"], dose["material_id"])
        for dose in coinop.settings.get(device_id)[DOSES]
    }
    picked = [
        dose["material_id"]
        for dose in changes.get(DOSES, [])
        if (dose["id"], dose["material_id"]) not in kept
    ]
    if (material_id := changes.get(DEFAULT_MATERIAL)) is not None:
        picked.append(material_id)
    if not all(pickable(connection, msg, coinop, id_) for id_ in picked):
        return
    if any(
        (material := coinop.catalog.material(dose["material_id"])) and material.by_piece
        for dose in changes.get(DOSES, [])
        if "stock" in dose
    ):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_ALLOWED,
            "A Dose counted in pieces has no stock input",
        )
        return
    templates = changes.get(AUTOMATIC_TEMPLATES, [])
    complete = len(coinop.catalog.find_templates(templates)) == len(templates)
    if (
        found(connection, msg, templates if complete else None, "Line Item Template")
        is None
    ):
        return
    if TAGS_FOR_NEW_RUNS in changes:
        changes[TAGS_FOR_NEW_RUNS] = await coinop.catalog.async_add_tags(
            changes[TAGS_FOR_NEW_RUNS]
        )
    settings = await coinop.settings.async_update(msg["device_id"], changes)
    connection.send_result(msg["id"], {"settings": settings})


# A row's key, the Line Item kind measuring it and the decimals the panel shows.
_MEASURED = {"kwh": (LineItemKind.ELECTRICITY, 3), "litres": (LineItemKind.WATER, 1)}


def _measured(run: Run, kind: LineItemKind) -> float | None:
    return next(
        (
            item.quantity
            for item in run.line_items
            if item.kind is kind
            and item.method
            in (ConsumptionMethod.MEASURED, ConsumptionMethod.FROM_HISTORY)
        ),
        None,
    )


@command(
    {
        vol.Required("type"): "coinop/devices/measured_suggestions",
        vol.Required("device_id"): str,
    }
)
def _measured_suggestions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    coinop: CoinOp,
) -> None:
    """The mean measured kWh and litres of the Device's Completed Runs, with their
    count, per Program and for the Default row (Runs whose Program has no row).

    Only measured and from-history quantities count; a key without Runs is left out.
    """
    device_id = msg["device_id"]
    device = next((d for d in coinop.devices if d.device_id == device_id), None)
    if found(connection, msg, device, "Device") is None:
        return
    programs = coinop.settings.get(device_id)[PROGRAM_DEFAULTS]["programs"]
    values: dict[str | None, dict[str, list[float]]] = {}
    for run in coinop.book.runs():
        if (
            run.device_id != device_id
            or run.outcome is not Outcome.COMPLETED
            or not run.finalised
        ):
            continue
        rows: list[str | None] = [run.program] if run.program else []
        if run.program not in programs:
            rows.append(None)
        for key, (kind, _) in _MEASURED.items():
            if (quantity := _measured(run, kind)) is not None:
                for row in rows:
                    values.setdefault(row, {}).setdefault(key, []).append(quantity)

    def means(row: str | None) -> dict[str, Any]:
        return {
            key: {
                "mean": round(fmean(measured), _MEASURED[key][1]),
                "runs": len(measured),
            }
            for key, measured in values.get(row, {}).items()
        }

    connection.send_result(
        msg["id"],
        {
            "suggestions": {
                "default": means(None),
                "programs": {row: means(row) for row in values if row is not None},
            }
        },
    )


COMMANDS = (_list, _update_settings, _measured_suggestions)
