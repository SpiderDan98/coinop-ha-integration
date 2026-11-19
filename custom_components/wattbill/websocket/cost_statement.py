"""The export dialog: its defaults, and creating a Cost Statement to download."""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.statement import (
    LANGUAGES,
    Detail,
    Options,
    language_for,
    signed_path,
)

from .command import command
from .runs import find_run


@command({vol.Required("type"): "wattbill/cost_statement/defaults"})
def _defaults(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    connection.send_result(msg["id"], {"markup": wattbill.statements.markup})


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


@command(
    {
        vol.Required("type"): "wattbill/cost_statement/create",
        vol.Required("run_ids"): vol.All([str], vol.Length(min=1)),
        vol.Optional("title"): vol.Any(None, str),
        vol.Optional("note"): vol.Any(None, str),
        vol.Optional("detail", default=Detail.DETAILED): vol.Coerce(Detail),
        vol.Optional("images", default=True): bool,
        vol.Optional("language"): vol.In(LANGUAGES),
        vol.Optional("markup"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)
def _create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """`{"path": ...}`: the signed path the browser downloads the PDF from."""
    for run_id in msg["run_ids"]:
        if (run := find_run(connection, msg, wattbill, run_id)) is None:
            return
        if not run.finalised:
            connection.send_error(
                msg["id"], websocket_api.ERR_NOT_ALLOWED, "Only final Runs"
            )
            return
    options = Options(
        language=msg.get("language", language_for(hass.config.language)),
        markup=msg.get("markup", wattbill.statements.markup),
        title=_text(msg.get("title")),
        note=_text(msg.get("note")),
        detail=msg["detail"],
        images=msg["images"],
    )
    token = wattbill.statements.add(msg["run_ids"], options, dt_util.utcnow())
    connection.send_result(
        msg["id"], {"path": signed_path(hass, token, connection.refresh_token_id)}
    )


COMMANDS = (_defaults, _create)
