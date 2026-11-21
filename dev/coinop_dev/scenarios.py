"""The Scenarios: Coin-op set up from scratch with the picked Pieces, then filled
through its own websocket API the way the panel fills it, so the data goes through
the same code as a user's."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
import json
import logging
import random
from types import MappingProxyType
from typing import Any, ClassVar

from homeassistant.auth.models import User
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.components.websocket_api.http import WebSocketAdapter
from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from PIL import Image, ImageDraw

from custom_components.coinop.const import DOMAIN as COINOP, SUBENTRY_DEVICE
from custom_components.coinop.device_config import DEVICE_TYPES, stored_capabilities
from custom_components.coinop.models import ImageKind
from custom_components.coinop.runtime import CoinOpConfigEntry

from .stand_ins import Registration, printers

_LOGGER = logging.getLogger(__name__)

# Each Device's inputs are helpers from the dev configuration.yaml.
PRINTERS = {"prusa": 120.0, "bambu": 150.0}

MATERIALS = [
    ("Prusament PLA Galaxy Black", "PLA", "#1d1d24", "Prusa", 29.99),
    ("Extrudr PETG White", "PETG", "#f3f3f3", "Extrudr", 24.90),
    ("Polymaker ASA Red", "ASA", "#c0262d", "Polymaker", 32.50),
    ("eSun PLA+ Blue", "PLA", "#1f5fbf", "eSun", 19.99),
    ("Bambu PLA Matte Ivory", "PLA", "#e9e3d3", "Bambu Lab", 22.99),
    ("Prusament PETG Orange", "PETG", "#f26b1d", "Prusa", 29.99),
    ("Polymaker PC Grey", "PC", "#8a8d91", "Polymaker", 39.00),
    ("Sunlu TPU Clear", "TPU", "#d8e6ea", "Sunlu", 27.00),
]
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ASA": 1.07, "PC": 1.20, "TPU": 1.21}

PARTS = [
    "Desk cable holder",
    "Sensor box enclosure",
    "Plant pot",
    "Camera mount",
    "Dishwasher spare part",
    "Headphone stand",
    "Drawer organiser",
    "Phone stand",
    "Raspberry Pi case",
    "Wall hook",
    "Lamp shade",
    "Gridfinity bins",
    "Filament clip",
    "Cookie cutter",
    "Keychain",
    "Spiral vase",
    "Spool holder",
    "Bike light mount",
    "Fan duct",
    "Board game insert",
]
# Name, type, form, density, pack unit, pack price, pack size.
LAUNDRY = [
    ("Liquid detergent Color", "Liquid detergent", "detergent", 1.04, "ml", 9.95, 1500),
    (
        "Fabric softener Sensitive",
        "Fabric softener",
        "fabric_softener",
        1.0,
        "ml",
        2.49,
        1000,
    ),
    ("Oxygen whitener", "Whitener", "laundry_additive", 0.9, "g", 3.95, 750),
    (
        "Colour catcher sheets",
        "Colour catcher sheets",
        "laundry_additive",
        None,
        "pcs",
        3.49,
        20,
    ),
]
# Days ago, Program (None: never recognised), minutes into the load it is
# recognised, minutes, kWh, litres, grams of detergent off the scale, Outcome.
LOADS = [
    (26, "Cotton 60°", 0, 128, 1.12, 58.0, 78, "finished"),
    (23, "Eco 40-60", 0, 218, 0.71, 49.0, 72, "finished"),
    (20, "Wool", 0, 62, 0.38, 44.0, 41, "finished"),
    (17, None, 0, 95, 0.85, 52.0, 76, "finished"),
    (14, "Cotton 60°", 0, 125, 1.18, 56.5, 80, "finished"),
    (12, "Quick 30", 8, 31, 0.32, 38.0, 50, "finished"),
    (9, "Eco 40-60", 0, 40, 0.35, 30.5, 70, "cancelled"),
    (6, "Cotton 60°", 0, 131, 1.09, 57.0, 77, "finished"),
    (3, "Eco 40-60", 0, 221, 0.74, 48.0, 74, "finished"),
    (1, "Wool", 0, 60, 0.41, 46.0, 39, "finished"),
]
# A Program's minutes, kWh, litres and grams of detergent, for the long history.
TYPICAL = {
    "Cotton 60°": (128, 1.12, 57.0, 78),
    "Eco 40-60": (219, 0.72, 48.5, 72),
    "Wool": (61, 0.4, 45.0, 40),
    "Quick 30": (31, 0.32, 38.0, 50),
}
# Days ago, hour it starts at, minutes, litres.
WATERINGS = [
    (12, 6, 20, 182.0),
    (9, 6, 20, 176.5),
    (6, 20, 35, 311.0),
    (4, 6, 20, 180.5),
    (2, 6, 25, 224.0),
    (1, 20, 15, 133.5),
]
# How much history the Devices with history get: none leaves each alone.
HISTORIES = ("none", "short", "long")
TAGS = ["Customer Miller", "Household", "Garden", "Electronics", "Gifts", "Prototypes"]


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

    def __init__(self, hass: HomeAssistant, api: Api, entry: CoinOpConfigEntry) -> None:
        self.hass = hass
        self.api = api
        self.entry = entry
        self.devices = {
            name: subentry.subentry_id
            for name, piece in PIECES.items()
            for subentry in entry.subentries.values()
            if isinstance(piece, DeviceWithHistory) and subentry.title == piece.title
        }
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

    async def add_laundry(self) -> None:
        for name, type_, form, density, pack_unit, pack_price, pack_size in LAUNDRY:
            material = {
                "name": name,
                "form": form,
                "type": type_,
                "density": density,
                "price": {
                    "source": "fixed",
                    "pack_price": pack_price,
                    "pack_size": pack_size,
                    "pack_unit": pack_unit,
                },
            }
            created = await self.api.call("coinop/materials/create", material=material)
            self.materials[name] = created["material"]

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

    async def set_printer(self, printer: str, status: str, job: str = "") -> None:
        """Set a printer's helpers, as its integration would report a job."""
        await _async_set(self.hass, f"input_text.{printer}_job", job)
        await _async_set(self.hass, f"input_select.{printer}_status", status)


# The shared data a Piece can need, each created once per load, in this order.
SHARED: dict[str, Callable[[Seed], Awaitable[None]]] = {
    "filaments": Seed.add_filaments,
    "laundry": Seed.add_laundry,
    "tags": Seed.add_tags,
    "template": Seed.add_template,
}


async def _async_set(hass: HomeAssistant, entity_id: str, value: str | float) -> None:
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


async def _prusa(seed: Seed) -> None:
    black, white, red = (name for name, *_ in MATERIALS[:3])

    def ago(days: int) -> datetime:
        return seed.now - timedelta(days=days)

    customer = ["Customer Miller", "Electronics"]
    add = seed.add_run
    await add(
        "prusa", "Benchy", ago(48), 1.2, tags=["Prototypes"], material=black, grams=14
    )
    await add(
        "prusa",
        "Desk cable holder",
        ago(42),
        2.6,
        tags=["Household"],
        material=black,
        grams=38,
    )
    await add(
        "prusa",
        "Sensor box enclosure",
        ago(35),
        6.7,
        tags=customer,
        material=white,
        grams=112,
        note="Lid printed separately.",
    )
    await add(
        "prusa",
        "Sensor box enclosure v2",
        ago(33),
        1.2,
        "failed",
        tags=customer,
        material=white,
        grams=21,
    )
    await add(
        "prusa", "Plant pot", ago(26), 15.5, tags=["Garden"], material=red, grams=260
    )
    await add(
        "prusa",
        "Dishwasher spare part",
        ago(9),
        0.7,
        "cancelled",
        tags=["Household"],
        material=black,
        grams=6,
    )
    await add(
        "prusa",
        "Camera mount",
        ago(2),
        3.3,
        tags=["Customer Miller"],
        material=red,
        grams=54,
        parts=2,
    )


async def _bambu(seed: Seed) -> None:
    rng = seed.random
    names = [name for name, *_ in MATERIALS[:5]]
    for day in sorted(rng.sample(range(1, 42), 10), reverse=True):
        hours = round(rng.uniform(0.5, 9), 1)
        await seed.add_run(
            "bambu",
            rng.choice(PARTS),
            seed.now - timedelta(days=day, hours=rng.randrange(12)),
            hours,
            rng.choices(["completed", "failed", "cancelled"], [90, 6, 4])[0],
            tags=rng.sample(TAGS, rng.choice([0, 1, 2])),
            material=rng.choice(names),
            grams=round(hours * rng.uniform(8, 18), 1),
        )


async def _long_history(seed: Seed, printer: str, gaps: list[int]) -> None:
    """Two years of Runs, `gaps` days apart."""
    box = seed.templates["Shipping box"]
    rng = seed.random
    names = [name for name, *_ in MATERIALS]
    day = 730
    while (day := day - rng.choice(gaps)) > 0:
        started = (
            seed.now
            - timedelta(days=day, hours=rng.randrange(14))
            - timedelta(hours=10)
        )
        hours = round(rng.lognormvariate(1.0, 0.8), 1) + 0.2
        outcome = rng.choices(["completed", "failed", "cancelled"], [88, 7, 5])[0]
        part = rng.choice(PARTS)
        material = rng.choice(names[:-1] if day < 200 else names)
        weighed = rng.random() > 0.02
        run = await seed.add_run(
            printer,
            part if rng.random() > 0.2 else f"{part} v{rng.randrange(2, 5)}",
            started,
            hours,
            outcome,
            tags=rng.sample(TAGS, rng.choice([0, 1, 1, 1, 2])),
            material=material,
            grams=round(hours * rng.uniform(8, 18), 1) if weighed else None,
            note="Customer pickup on Friday." if rng.random() < 0.05 else None,
            parts=rng.choice([2, 4, 6]) if rng.random() < 0.1 else None,
            thumbnail=rng.random() < 0.7,
        )
        if rng.random() < 0.1:
            await seed.api.call(
                "coinop/line_items/add_template",
                run_id=run["id"],
                template_id=box["id"],
            )
    # TPU went unused for the last 200 days.
    seed.retired.add(names[-1])


async def _prusa_long(seed: Seed) -> None:
    await _long_history(seed, "prusa", [1, 2, 3, 4, 5, 6])


async def _bambu_long(seed: Seed) -> None:
    await _long_history(seed, "bambu", [3, 4, 5, 6, 7, 8, 9])


async def _prusa_start(seed: Seed) -> None:
    await seed.set_printer("prusa", "printing", "Gridfinity bins 3x2.gcode")


async def _bambu_start(seed: Seed) -> None:
    await seed.set_printer("bambu", "printing", "Spool holder.gcode")


async def _washer_settings(seed: Seed) -> None:
    detergent, softener, whitener, sheets = (
        seed.materials[name]["id"] for name, *_ in LAUNDRY
    )
    await seed.api.call(
        "coinop/devices/update_settings",
        device_id=seed.devices["washer"],
        settings={
            "doses": [
                {
                    "id": "detergent",
                    "material_id": detergent,
                    "stock": {"entity_id": "input_number.detergent_scale"},
                },
                {"id": "softener", "material_id": softener},
                {"id": "whitener", "material_id": whitener},
                {"id": "sheets", "material_id": sheets},
            ],
            "program_defaults": {
                "default": {
                    "kwh": 0.9,
                    "litres": 50,
                    "doses": {"detergent": 75, "softener": 30},
                },
                "programs": {
                    "Cotton 60°": {
                        "kwh": 1.1,
                        "litres": 56,
                        "doses": {
                            "detergent": 75,
                            "softener": 30,
                            "whitener": 20,
                            "sheets": 1,
                        },
                    },
                    "Eco 40-60": {
                        "kwh": 0.72,
                        "litres": 48,
                        "doses": {"detergent": 70, "softener": 30},
                    },
                    "Wool": {"kwh": 0.4, "litres": 45, "doses": {"detergent": 40}},
                },
            },
        },
    )


async def _washer_short(seed: Seed) -> None:
    await _wash(seed, LOADS)


async def _washer_long(seed: Seed) -> None:
    """A load every few days for two years, then the short level's."""
    rng = seed.random
    loads, day = [], 730
    while day > 30:
        program = rng.choice([*TYPICAL, None])
        minutes, kwh, litres, grams = TYPICAL[program or "Cotton 60°"]
        outcome = rng.choices(["finished", "cancelled"], [95, 5])[0]
        share = rng.uniform(0.2, 0.6) if outcome == "cancelled" else 1
        loads.append(
            (
                day,
                program,
                0,
                round(minutes * share * rng.uniform(0.95, 1.05)),
                round(kwh * share * rng.uniform(0.9, 1.1), 2),
                round(litres * share * rng.uniform(0.9, 1.1), 1),
                round(grams * rng.uniform(0.9, 1.1)),
                outcome,
            )
        )
        day -= rng.randrange(4, 11)
    await _wash(seed, [*loads, *LOADS])


async def _wash(seed: Seed, loads: list[tuple[Any, ...]]) -> None:
    meters = {"washer_energy": 412.5, "washer_water": 18250.0, "detergent_scale": 650.0}
    for days, program, recognised, minutes, kwh, litres, grams, outcome in loads:
        if meters["detergent_scale"] < grams:
            # A new bottle; a refill between loads counts nothing.
            meters["detergent_scale"] += 1500
        start = seed.now.replace(hour=9, minute=30) - timedelta(days=days)
        end = start + timedelta(minutes=minutes)
        known = None if recognised else program
        await _replay(seed.hass, "input_select.washer_program", known or "", start)
        await _replay_meters(seed.hass, meters, start)
        await _replay(seed.hass, "input_select.washer_status", "running", start)
        meters["detergent_scale"] -= grams
        await _replay_meters(seed.hass, meters, start + timedelta(minutes=3))
        if program and recognised:
            at = start + timedelta(minutes=recognised)
            await _replay(seed.hass, "input_select.washer_program", program, at)
        meters["washer_energy"] = round(meters["washer_energy"] + kwh, 3)
        meters["washer_water"] = round(meters["washer_water"] + litres, 1)
        await _replay_meters(seed.hass, meters, end - timedelta(minutes=2))
        await _replay(seed.hass, "input_select.washer_status", outcome, end)
        # Reports after the end spare the wait for them.
        await _replay_meters(seed.hass, meters, end + timedelta(minutes=1))
    for key, value in meters.items():
        await _async_set(seed.hass, f"input_number.{key}", value)
    await _async_set(seed.hass, "input_select.washer_program", "Wool")
    await _async_set(seed.hass, "input_select.washer_status", "off")


async def _washer_start(seed: Seed) -> None:
    await _async_set(seed.hass, "input_select.washer_program", "Cotton 60°")
    await _async_set(seed.hass, "input_select.washer_status", "running")


async def _irrigation_short(seed: Seed) -> None:
    await _water(seed, WATERINGS)


async def _irrigation_long(seed: Seed) -> None:
    """Every few days through two summers, then the short level's waterings."""
    rng = seed.random
    waterings = []
    for summer in (1, 0):
        day = 365 * summer + 300
        while day > 365 * summer + 140:
            minutes = rng.choice([15, 20, 20, 25, 35])
            litres = round(minutes * rng.uniform(8, 9.5), 1)
            waterings.append((day, 20 if minutes > 30 else 6, minutes, litres))
            day -= rng.randrange(2, 5)
    await _water(seed, [*waterings, *WATERINGS])


async def _water(seed: Seed, waterings: list[tuple[int, int, int, float]]) -> None:
    meter = {"irrigation_water": 48200.0}
    for days, hour, minutes, litres in waterings:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        end = start + timedelta(minutes=minutes)
        await _replay_meters(seed.hass, meter, start)
        await _replay(seed.hass, "input_select.irrigation_status", "watering", start)
        meter["irrigation_water"] = round(meter["irrigation_water"] + litres, 1)
        await _replay_meters(seed.hass, meter, end - timedelta(minutes=1))
        await _replay(seed.hass, "input_select.irrigation_status", "off", end)
        # A report after the end spares the wait for it.
        await _replay_meters(seed.hass, meter, end + timedelta(minutes=1))
    await _async_set(
        seed.hass, "input_number.irrigation_water", meter["irrigation_water"]
    )
    await _async_set(seed.hass, "input_select.irrigation_status", "off")


async def _irrigation_start(seed: Seed) -> None:
    await _async_set(seed.hass, "input_select.irrigation_status", "watering")


async def _replay_meters(
    hass: HomeAssistant, meters: dict[str, float], at: datetime
) -> None:
    for key, value in meters.items():
        await _replay(hass, f"input_number.{key}", value, at)


async def _replay(
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


def _printer(key: str) -> dict[str, Any]:
    """The printer's subentry data, as Add Device writes it."""
    return {
        "device_type": "3d_printer",
        "printer_device_id": None,
        "status": {"entity_id": f"input_select.{key}_status", "attribute": None},
        "mapping": {
            "running": ["printing"],
            "paused": ["paused"],
            "finished": ["finished"],
            "cancelled": ["cancelled"],
            "ended": [],
            "fault": ["error"],
            "ignored": ["idle"],
        },
        "job": {
            "entity_id": f"input_text.{key}_job",
            "attribute": None,
            "material": None,
            "slots": [],
            "colour_attribute": None,
            "loaded_slot": None,
        },
        "images": {"thumbnail": None, "camera": None, "snapshot": False},
        "consumption": {
            "source": "estimate",
            "running_power": PRINTERS[key],
            "paused_power": 15.0,
        },
        "price": {"source": "fixed", "value": 0.32},
    }


def _washer() -> dict[str, Any]:
    return {
        "device_type": "washing_machine",
        "printer_device_id": None,
        "status": {"entity_id": "input_select.washer_status", "attribute": None},
        "mapping": {
            "running": ["running"],
            "paused": ["paused"],
            "finished": ["finished"],
            "cancelled": ["cancelled"],
            "ended": [],
            "fault": [],
            "ignored": ["off"],
        },
        "program": {"entity_id": "input_select.washer_program", "attribute": None},
        "consumption": {
            "source": "energy",
            "entity_id": "input_number.washer_energy",
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.32},
        "water": {
            "source": "meter",
            "entity_id": "input_number.washer_water",
            "attribute": None,
            "unit": "L",
            "factor": None,
        },
        # Per m³, wastewater included.
        "water_price": {"source": "fixed", "value": 4.2},
    }


def _garden_valve() -> dict[str, Any]:
    """A battery-driven valve: an Other Device that has water and no electricity."""
    return {
        "device_type": "other",
        "type_name": "Irrigation",
        "capabilities": stored_capabilities(["water"]),
        "printer_device_id": None,
        "status": {"entity_id": "input_select.irrigation_status", "attribute": None},
        "mapping": {
            "running": ["watering"],
            "paused": [],
            "finished": ["off"],
            "cancelled": [],
            "ended": [],
            "fault": [],
            "ignored": [],
        },
        "consumption": {"source": "none"},
        "water": {
            "source": "meter",
            "entity_id": "input_number.irrigation_water",
            "attribute": None,
            "unit": "L",
            "factor": None,
        },
        # Per m³; garden water is billed without wastewater.
        "water_price": {"source": "fixed", "value": 2.1},
    }


@dataclass(frozen=True)
class Piece:
    group: str
    title: str
    description: str
    # Each helper it uses, with the value loading resets it to, in this order.
    helpers: Mapping[str, str | float]


@dataclass(frozen=True)
class DeviceWithHistory(Piece):
    """A Device set up as Add Device sets one up, named as the Piece, with Runs."""

    section: ClassVar[str] = "device"
    device: Mapping[str, Any]
    # The Runs of each history level but none, which leaves the Device alone.
    short: Callable[[Seed], Awaitable[None]]
    long: Callable[[Seed], Awaitable[None]]
    # Starts a Run through its helpers, as its integration would report one.
    start: Callable[[Seed], Awaitable[None]]
    needs: tuple[str, ...] = ()
    # The panel settings it gets whatever its history, before its Runs.
    setup: Callable[[Seed], Awaitable[None]] | None = None

    async def fill(self, seed: Seed, history: str) -> None:
        if self.setup:
            await self.setup(seed)
        if history != "none":
            await (self.short if history == "short" else self.long)(seed)


@dataclass(frozen=True)
class QuickStartPiece(Piece):
    """An HA device of a stand-in's config entry, for Quick Start to offer."""

    section: ClassVar[str] = "quick_start"
    domain: str
    # What the stand-in's config flow is started with.
    data: Mapping[str, str] | None = None

    async def fill(self, seed: Seed) -> None:
        await seed.hass.config_entries.flow.async_init(
            self.domain, context={"source": SOURCE_USER}, data=self.data
        )


# What a static stand-in's config entry is started with: the Device Type keys picked.
KINDS = "kinds"


@dataclass(frozen=True)
class StaticPiece(Piece):
    """An HA device of a static stand-in (`static.py`), registered from its
    integration's description; a contributor sets its Status in the developer tools."""

    section: ClassVar[str] = "quick_start"
    registration: Callable[[], Registration]

    @property
    def domain(self) -> str:
        return self.registration().domain

    async def fill(self, seed: Seed) -> None:
        """Adds its kind to the account's entry where the integration keeps one."""
        hass = seed.hass
        account = self.registration().account
        if account and (entries := hass.config_entries.async_entries(self.domain)):
            [entry] = entries
            kinds = [*entry.data[KINDS], self.group]
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, KINDS: kinds}
            )
            await hass.config_entries.async_reload(entry.entry_id)
            return
        await hass.config_entries.flow.async_init(
            self.domain, context={"source": SOURCE_USER}, data={KINDS: [self.group]}
        )


def _printer_helpers(key: str, idle: str = "idle") -> dict[str, str | float]:
    return {f"input_text.{key}_job": "", f"input_select.{key}_status": idle}


PIECES: dict[str, DeviceWithHistory | QuickStartPiece | StaticPiece] = {
    "prusa": DeviceWithHistory(
        "3d_printer",
        "Prusa MK4",
        "Short history: 7 Runs over seven weeks on 3 of the 8 filaments; long: two "
        "years of Runs on all 8. With Tags and Thumbnails.",
        _printer_helpers("prusa"),
        device=_printer("prusa"),
        short=_prusa,
        long=_prusa_long,
        start=_prusa_start,
        needs=("filaments", "tags", "template"),
    ),
    "bambu": DeviceWithHistory(
        "3d_printer",
        "Bambu Lab X1C",
        "Short history: 10 Runs over six weeks on 5 of the 8 filaments; long: two "
        "years of Runs on all 8. With Tags and Thumbnails.",
        _printer_helpers("bambu"),
        device=_printer("bambu"),
        short=_bambu,
        long=_bambu_long,
        start=_bambu_start,
        needs=("filaments", "tags", "template"),
    ),
    "anycubic.3d_printer": StaticPiece(
        "3d_printer",
        "Anycubic Kobra S1 · Anycubic 3D Printer - Local Control",
        "A printer with an ACE Pro and its plug sensor as meter; set its print "
        "event's state and `event_type` in the developer tools to run it.",
        {"input_number.anycubic_kobra_power": 0},
        registration=printers.anycubic_local,
    ),
    "anycubic_cloud.3d_printer": QuickStartPiece(
        "3d_printer",
        "Kobra S1 · Anycubic Cloud & LAN",
        "A printer with its plug sensor as meter; the Kobra's helpers run it.",
        _printer_helpers("kobra") | {"input_number.kobra_power": 0},
        domain="anycubic_cloud",
    ),
    "bambu_lab.3d_printer": StaticPiece(
        "3d_printer",
        "P1S · Bambu Lab",
        "A printer with an AMS and its plug sensor as meter; set its print status "
        "in the developer tools to run it.",
        {"input_number.p1s_power": 0},
        registration=printers.bambu_lab,
    ),
    "prusalink.3d_printer": StaticPiece(
        "3d_printer",
        "Prusa Core One · PrusaLink",
        "A printer with its job preview and its plug sensor as meter; set its state "
        "in the developer tools to run it.",
        {"input_number.core_one_power": 0},
        # Named apart from the Prusa MK4 Device with history.
        registration=partial(printers.prusalink, title="Prusa Core One"),
    ),
    "octoprint.3d_printer": StaticPiece(
        "3d_printer",
        "OctoPrint · OctoPrint",
        "A printer with a webcam and its plug sensor as meter; set its current "
        "state in the developer tools to run it.",
        {"input_number.octoprint_power": 0},
        registration=printers.octoprint,
    ),
    "ha_creality_ws.3d_printer": StaticPiece(
        "3d_printer",
        "K1C · Creality",
        "A printer with its print preview and its plug sensor as meter; set its "
        "print status, with the job's `file` attribute, in the developer tools to "
        "run it.",
        {"input_number.k1c_power": 0},
        registration=printers.creality,
    ),
    "elegoo_printer.3d_printer": StaticPiece(
        "3d_printer",
        "Centauri Carbon · Elegoo",
        "A printer with its cover image and its plug sensor as meter; set its print "
        "status in the developer tools to run it.",
        {"input_number.centauri_carbon_power": 0},
        registration=printers.elegoo,
    ),
    "moonraker.3d_printer": QuickStartPiece(
        "3d_printer",
        "Voron 2.4 · Moonraker",
        "A printer with its preview camera, a webcam and its plug sensor as meter; "
        "the Voron's helpers run it.",
        _printer_helpers("voron", "standby")
        | {"input_number.voron_filament": 0, "input_number.voron_power": 0},
        domain="moonraker",
    ),
    "washer": DeviceWithHistory(
        "washing_machine",
        "Washing machine",
        "Energy and water meters, a detergent scale, 4 laundry products as Doses "
        "and Program Defaults. Short history: 10 loads over four weeks; long: a load "
        "every few days for two years.",
        {"input_select.washer_status": "off"},
        device=_washer(),
        short=_washer_short,
        long=_washer_long,
        start=_washer_start,
        needs=("laundry",),
        setup=_washer_settings,
    ),
    "ha_washdata.washing_machine": QuickStartPiece(
        "washing_machine",
        "Washing machine · WashData",
        "A washing machine WashData follows, with its plug sensor as meter; the "
        "washing machine's helpers run it.",
        {"input_select.washer_status": "off"},
        domain="ha_washdata",
    ),
    "ha_washdata.dishwasher": QuickStartPiece(
        "dishwasher",
        "Dishwasher · WashData",
        "A dishwasher WashData follows, with its plug sensor as meter; the "
        "dishwasher's helpers run it.",
        {"input_select.dishwasher_status": "off"},
        domain="ha_washdata",
        data={"name": "Dishwasher", "device_type": "dishwasher"},
    ),
    "tesla_wall_connector.ev_charger": QuickStartPiece(
        "ev_charger",
        "Tesla Wall Connector · Tesla Wall Connector",
        "A charger with its own lifetime energy meter; the Wall Connector's helpers "
        "run it.",
        {"input_select.wall_connector_status": "not_connected"},
        domain="tesla_wall_connector",
    ),
    "irrigation": DeviceWithHistory(
        "other",
        "Garden valve",
        'An Other Device under the Type Name "Irrigation" with water on a water '
        "meter and the electricity source None, each watering costing only its "
        "water. Short history: 6 waterings over two weeks; long: two summers of them.",
        {"input_select.irrigation_status": "off"},
        device=_garden_valve(),
        short=_irrigation_short,
        long=_irrigation_long,
        start=_irrigation_start,
    ),
}


@dataclass(frozen=True)
class Preset:
    title: str
    description: str
    pieces: tuple[str, ...]
    history: str = "short"
    open_run: bool = False

    @property
    def selection(self) -> dict[str, Any]:
        return {
            "pieces": ordered(self.pieces),
            "history": self.history,
            "open_run": self.open_run,
        }


PRESETS = {
    "empty": Preset("Empty", "The hub without any Device.", ()),
    "quick-start": Preset(
        "Quick Start",
        "The hub without any Device, and every Quick Start Piece: Add Device offers "
        "each HA device in Quick Start as its Device Type.",
        tuple(n for n, p in PIECES.items() if p.section == "quick_start"),
    ),
    "few-runs": Preset(
        "3D printer, a few Runs", "The Prusa with its 7 Runs.", ("prusa",)
    ),
    "printing-now": Preset(
        "3D printer, printing now",
        "Like a few Runs, with an open Run; the printer's helpers end it.",
        ("prusa",),
        open_run=True,
    ),
    "two-printers": Preset(
        "Two printers", "The Prusa and the Bambu with their Runs.", ("prusa", "bambu")
    ),
    "long-history": Preset(
        "Long history",
        "Two years of Runs on two printers, 8 Materials (one archived), a Line Item "
        "Template.",
        ("prusa", "bambu"),
        history="long",
    ),
    "washing-machine": Preset(
        "Washing machine", "The washing machine with its 10 loads.", ("washer",)
    ),
    "irrigation": Preset(
        "Irrigation (Other Device)",
        "The garden valve with its 6 waterings.",
        ("irrigation",),
    ),
}


def ordered(names: Iterable[str]) -> list[str]:
    """The Pieces `names` in group, then Piece order."""
    picked = set(names)
    return sorted(
        (name for name in PIECES if name in picked),
        key=lambda name: DEVICE_TYPES.index(PIECES[name].group),
    )


async def async_load(
    hass: HomeAssistant, choice: str | Mapping[str, Any], user: User | None
) -> dict[str, Any]:
    """Replace whatever Coin-op holds by a Preset or a selection of Pieces; returns
    the selection loaded."""
    if isinstance(choice, str):
        choice = PRESETS[choice].selection
    pieces = ordered(choice["pieces"])
    history, open_run = choice.get("history", "short"), choice.get("open_run", False)
    user = user or await hass.auth.async_get_owner()
    if user is None:
        raise ScenarioError("No user to load the Scenario as")
    stand_ins = {
        p.domain
        for p in PIECES.values()
        if isinstance(p, (QuickStartPiece, StaticPiece))
    }
    for domain in (COINOP, *stand_ins):
        for old in hass.config_entries.async_entries(domain):
            await hass.config_entries.async_remove(old.entry_id)
    for piece in PIECES.values():
        for entity_id, value in piece.helpers.items():
            if hass.states.get(entity_id):
                await _async_set(hass, entity_id, value)
    entry = await _async_add_hub(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    with_history = [p for n in pieces if isinstance(p := PIECES[n], DeviceWithHistory)]
    for piece in with_history:
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=MappingProxyType(dict(piece.device)),
                subentry_type=SUBENTRY_DEVICE,
                title=piece.title,
                unique_id=None,
            ),
        )
    await hass.config_entries.async_setup(entry.entry_id)
    seed = Seed(hass, Api(hass, user), entry)
    needs = {need for piece in with_history for need in piece.needs}
    for need, add in SHARED.items():
        if need in needs:
            await add(seed)
    for piece in (PIECES[name] for name in pieces):
        if isinstance(piece, DeviceWithHistory):
            await piece.fill(seed, history)
        else:
            await piece.fill(seed)
    for name in seed.retired:
        await seed.api.call(
            "coinop/materials/archive", material_id=seed.materials[name]["id"]
        )
    if open_run:
        for piece in with_history:
            await piece.start(seed)
    return {"pieces": pieces, "history": history, "open_run": open_run}


async def _async_add_hub(hass: HomeAssistant) -> ConfigEntry:
    """The hub entry through its config flow, without the Add Device that follows."""
    result = await hass.config_entries.flow.async_init(
        COINOP, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    if next_flow := result.get("next_flow"):
        hass.config_entries.subentries.async_abort(next_flow[1])
    entry: ConfigEntry = result["result"]
    return entry
