"""What fills Coin-op: an in-process websocket connection and what a load creates."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
import json
import logging
import random
from typing import Any

from homeassistant.auth.models import User
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.components.websocket_api.http import WebSocketAdapter
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from PIL import Image, ImageDraw

from custom_components.coinop.models import ImageKind
from custom_components.coinop.runtime import CoinOpConfigEntry

from .data import (
    COFFEE_PRODUCTS,
    DENSITY,
    DISHWASHER_PRODUCTS,
    DRYER_PRODUCTS,
    LAUNDRY,
    MATERIALS,
    TAGS,
    Product,
)

_LOGGER = logging.getLogger(__name__)


class ScenarioError(Exception):
    """A websocket command a Scenario sent failed."""


class Api:
    """A websocket connection inside HA, as the panel has one."""

    def __init__(self, hass: HomeAssistant, user: User) -> None:
        self._hass = hass
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._connection = ActiveConnection(
            WebSocketAdapter(_LOGGER, {"connid": "coinop_dev"}),
            hass,
            self._receive,
            user,
            None,
            None,
        )
        self._last_id = 0

    async def call(self, type_: str, **fields: Any) -> Any:
        self._last_id += 1
        future = self._pending[self._last_id] = self._hass.loop.create_future()
        self._connection.async_handle({"id": self._last_id, "type": type_, **fields})
        return await future

    def _receive(self, message: bytes | str | dict[str, Any]) -> None:
        msg = message if isinstance(message, dict) else json.loads(message)
        if msg.get("type") != "result" or not (
            future := self._pending.pop(msg["id"], None)
        ):
            return
        if msg["success"]:
            future.set_result(msg["result"])
        else:
            future.set_exception(ScenarioError(msg["error"]))


class Seed:
    """What a Scenario fills Coin-op with."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: Api,
        entry: CoinOpConfigEntry,
        devices: Mapping[str, str],
    ) -> None:
        self.hass = hass
        self.api = api
        self.entry = entry
        # Each Device with history's subentry id, by its Piece's name.
        self.devices = devices
        self.random = random.Random(42)
        self.now = dt_util.now().replace(second=0, microsecond=0)
        self.materials: dict[str, dict[str, Any]] = {}
        self.templates: dict[str, dict[str, Any]] = {}
        # Materials archived once every Piece is filled.
        self.retired: set[str] = set()

    async def add_filaments(self) -> None:
        for name, type_, colour, vendor, pack_price in MATERIALS:
            material = {
                "name": name,
                "form": "filament",
                "type": type_,
                "density": DENSITY[type_],
                "price": {
                    "source": "fixed",
                    "pack_price": pack_price,
                    "pack_size": 1000,
                },
                "colour": colour,
                "vendor": vendor,
                "diameter": 1.75,
            }
            created = await self.api.call("coinop/materials/create", material=material)
            self.materials[name] = created["material"]

    async def add_products(self, products: Iterable[Product]) -> None:
        for product in products:
            material = {
                "name": product.name,
                "form": product.form,
                "type": product.type,
                "density": product.density,
                "price": {
                    "source": "fixed",
                    "pack_price": product.pack_price,
                    "pack_size": product.pack_size,
                    "pack_unit": product.pack_unit,
                },
            }
            created = await self.api.call("coinop/materials/create", material=material)
            self.materials[product.name] = created["material"]

    async def add_tags(self) -> None:
        for tag in TAGS:
            await self.api.call("coinop/tags/create", name=tag)

    async def add_template(self) -> None:
        template = {"label": "Shipping box", "unit_price": 1.5, "basis": "entered"}
        created = await self.api.call("coinop/templates/create", template=template)
        self.templates["Shipping box"] = created["template"]

    async def add_run(
        self,
        printer: str,
        name: str,
        started: datetime,
        hours: float,
        outcome: str = "completed",
        *,
        tags: list[str] | None = None,
        material: str | None = None,
        grams: float | None = None,
        note: str | None = None,
        parts: int | None = None,
        thumbnail: bool = True,
    ) -> dict[str, Any]:
        ended = started + timedelta(hours=hours)
        run: dict[str, Any] = (
            await self.api.call(
                "coinop/runs/create",
                device_id=self.devices[printer],
                name=name,
                started=started.isoformat(),
                ended=ended.isoformat(),
                outcome=outcome,
                tags=tags or [],
            )
        )["run"]
        if material is not None:
            [item] = [i for i in run["line_items"] if i["kind"] == "material"]
            run = (
                await self.api.call(
                    "coinop/line_items/update",
                    run_id=run["id"],
                    line_item_id=item["id"],
                    material_id=self.materials[material]["id"],
                    quantity=grams,
                )
            )["run"]
        if note is not None or parts is not None:
            changes = {"note": note} | ({"part_count": parts} if parts else {})
            run = (
                await self.api.call("coinop/runs/update", run_id=run["id"], **changes)
            )["run"]
        if thumbnail:
            colour = self.materials[material]["colour"] if material else "#9e9e9e"
            await self._thumbnail(run["id"], colour)
        return run

    async def _thumbnail(self, run_id: str, colour: str) -> None:
        # The panel API has no command for a Thumbnail; the image entity hands it over.
        runtime = self.entry.runtime_data
        if run := runtime.book.run(run_id):
            data = await self.hass.async_add_executor_job(
                _picture, colour, self.random.randrange(4)
            )
            await runtime.images.async_add(run, ImageKind.THUMBNAIL, data)


# The shared data a Piece can need, each created once per load, in this order.
SHARED: dict[str, Callable[[Seed], Awaitable[None]]] = {
    "filaments": Seed.add_filaments,
    "laundry": partial(Seed.add_products, products=LAUNDRY),
    "dishwasher": partial(Seed.add_products, products=DISHWASHER_PRODUCTS),
    "dryer": partial(Seed.add_products, products=DRYER_PRODUCTS),
    "coffee": partial(Seed.add_products, products=COFFEE_PRODUCTS),
    "tags": Seed.add_tags,
    "template": Seed.add_template,
}


async def async_set(hass: HomeAssistant, entity_id: str, value: str | float) -> None:
    domain = entity_id.split(".")[0]
    service, key = (
        ("select_option", "option")
        if domain == "input_select"
        else ("set_value", "value")
    )
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, key: value}, blocking=True
    )


def _picture(colour: str, shape: int) -> bytes:
    """A Thumbnail-like render: one part in the Material's colour."""
    image = Image.new("RGB", (480, 480), "#eceff1")
    draw = ImageDraw.Draw(image)
    box = (110, 110, 370, 370)
    outline = "#37474f"
    if shape == 0:
        draw.ellipse(box, fill=colour, outline=outline, width=6)
    elif shape == 1:
        draw.rounded_rectangle(box, 40, fill=colour, outline=outline, width=6)
    elif shape == 2:
        draw.polygon(
            [(240, 90), (390, 370), (90, 370)], fill=colour, outline=outline, width=6
        )
    else:
        draw.rectangle((150, 90, 330, 390), fill=colour, outline=outline, width=6)
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


async def replay_meters(
    hass: HomeAssistant, meters: Mapping[str, float], at: datetime
) -> None:
    for key, value in meters.items():
        await replay(hass, f"input_number.{key}", value, at)


async def replay(
    hass: HomeAssistant, entity_id: str, value: float | str, at: datetime
) -> None:
    """Report a helper's value as of `at`, which its services can't backdate."""
    # A task started eagerly, as the service call's is, isn't tracked before it waits.
    await asyncio.sleep(0)
    attributes = state.attributes if (state := hass.states.get(entity_id)) else None
    # Awaits only what the report starts: async_block_till_done would also wait for
    # the service call that is waiting for this load.
    before = set(hass._tasks)
    hass.states.async_set(entity_id, str(value), attributes, timestamp=at.timestamp())
    # Older Home Assistant runs state listeners a loop iteration after the change.
    await asyncio.sleep(0)
    while started := hass._tasks - before:
        await asyncio.wait(started)
