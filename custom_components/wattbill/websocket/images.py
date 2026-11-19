"""A Run's images for the panel: pick the Cover Image, delete one image.

Uploads go through the multipart view (`images/upload.py`). Every command
answers with the Run in full, as `wattbill/runs/get` does.
"""

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.wattbill.models import Run, RunImage
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol

from .command import command, found
from .runs import _send_run, find_run

_IMAGE = {vol.Required("run_id"): str, vol.Required("image_id"): str}


def _find_image(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any], wattbill: WattBill
) -> tuple[Run, RunImage] | None:
    """The Run and image the message names; answers `not_found` if there is none."""
    if (run := find_run(connection, msg, wattbill)) is None:
        return None
    images = (i for i in run.images if i.id == msg["image_id"])
    if (image := found(connection, msg, next(images, None), "image")) is None:
        return None
    return run, image


@command({vol.Required("type"): "wattbill/images/set_cover", **_IMAGE})
async def _set_cover(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (found := _find_image(connection, msg, wattbill)) is None:
        return
    run, image = found
    run.cover_id = image.id
    await wattbill.book.async_correct(run)
    _send_run(hass, connection, msg["id"], run)


@command({vol.Required("type"): "wattbill/images/delete", **_IMAGE})
async def _delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    if (found := _find_image(connection, msg, wattbill)) is None:
        return
    run, image = found
    await wattbill.images.async_delete(run, image)
    _send_run(hass, connection, msg["id"], run)


COMMANDS = (_set_cover, _delete)
