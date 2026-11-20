"""The Scenarios: Coin-op set up from scratch, then filled through its own websocket
API the way the panel fills it, so the data goes through the same code as a user's."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
import json
import logging
import random
from types import MappingProxyType
from typing import Any

from homeassistant.auth.models import User
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.components.websocket_api.http import WebSocketAdapter
from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from PIL import Image, ImageDraw

from custom_components.coinop.const import DOMAIN as COINOP, SUBENTRY_DEVICE
from custom_components.coinop.models import ImageKind
from custom_components.coinop.runtime import CoinOpConfigEntry

_LOGGER = logging.getLogger(__name__)

# Each Device's inputs are helpers from the dev configuration.yaml.
PRINTERS = {"prusa": ("Prusa MK4", 120.0), "bambu": ("Bambu Lab X1C", 150.0)}
WASHER = "washer"
TITLES = {key: name for key, (name, _) in PRINTERS.items()} | {
    WASHER: "Washing machine"
}

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
            key: subentry.subentry_id
            for key, name in TITLES.items()
            for subentry in entry.subentries.values()
            if subentry.title == name
        }
        self.random = random.Random(42)
        self.now = dt_util.now().replace(second=0, microsecond=0)
        self.materials: dict[str, dict[str, Any]] = {}

    async def add_materials(self, count: int) -> None:
        for name, type_, colour, vendor, pack_price in MATERIALS[:count]:
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
        await _async_set_printer(self.hass, printer, status, job)


async def _async_set_printer(
    hass: HomeAssistant, printer: str, status: str, job: str = ""
) -> None:
    """Set a printer's helpers, as its integration would report a job."""
    await hass.services.async_call(
        "input_text",
        "set_value",
        {"entity_id": f"input_text.{printer}_job", "value": job},
        blocking=True,
    )
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": f"input_select.{printer}_status", "option": status},
        blocking=True,
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


async def _few_runs(seed: Seed) -> None:
    await seed.add_materials(3)
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


async def _long_history(seed: Seed) -> None:
    await seed.add_materials(len(MATERIALS))
    box = (
        await seed.api.call(
            "coinop/templates/create",
            template={"label": "Shipping box", "unit_price": 1.5, "basis": "entered"},
        )
    )["template"]
    rng = seed.random
    names = [name for name, *_ in MATERIALS]
    day = 730
    while day > 0:
        day -= rng.choice([1, 1, 2, 3, 4])
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
            rng.choice(["prusa", "prusa", "bambu"]),
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
    await seed.api.call(
        "coinop/materials/archive", material_id=seed.materials[names[-1]]["id"]
    )


async def _two_printers(seed: Seed) -> None:
    await seed.add_materials(5)
    rng = seed.random
    names = [name for name, *_ in MATERIALS[:5]]
    for printer in ("prusa", "bambu"):
        for day in sorted(rng.sample(range(1, 120), 30), reverse=True):
            hours = round(rng.uniform(0.5, 9), 1)
            await seed.add_run(
                printer,
                rng.choice(PARTS),
                seed.now - timedelta(days=day, hours=rng.randrange(12)),
                hours,
                rng.choices(["completed", "failed", "cancelled"], [90, 6, 4])[0],
                tags=rng.sample(TAGS, rng.choice([0, 1, 2])),
                material=rng.choice(names),
                grams=round(hours * rng.uniform(8, 18), 1),
            )


async def _washing(seed: Seed) -> None:
    materials = []
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
        created = await seed.api.call("coinop/materials/create", material=material)
        materials.append(created["material"]["id"])
    detergent, softener, whitener, sheets = materials
    await seed.api.call(
        "coinop/devices/update_settings",
        device_id=seed.devices[WASHER],
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
    meters = {"washer_energy": 412.5, "washer_water": 18250.0, "detergent_scale": 650.0}
    for days, program, recognised, minutes, kwh, litres, grams, outcome in LOADS:
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
        await seed.hass.services.async_call(
            "input_number",
            "set_value",
            {"entity_id": f"input_number.{key}", "value": value},
            blocking=True,
        )
    await _async_set_washer(seed.hass, "off", "Wool")


async def _replay_meters(
    hass: HomeAssistant, meters: dict[str, float], at: datetime
) -> None:
    for key, value in meters.items():
        await _replay(hass, f"input_number.{key}", value, at)


async def _replay(
    hass: HomeAssistant, entity_id: str, value: float | str, at: datetime
) -> None:
    """Report a helper's value as of `at`, which its services can't backdate."""
    attributes = state.attributes if (state := hass.states.get(entity_id)) else None
    hass.states.async_set(entity_id, str(value), attributes, timestamp=at.timestamp())
    await hass.async_block_till_done()


async def _async_set_washer(hass: HomeAssistant, status: str, program: str) -> None:
    for entity_id, option in (
        ("input_select.washer_program", program),
        ("input_select.washer_status", status),
    ):
        await hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )


async def _printing_now(seed: Seed) -> None:
    await _few_runs(seed)
    await seed.set_printer("prusa", "printing", "Gridfinity bins 3x2.gcode")


async def _nothing(seed: Seed) -> None:
    pass


@dataclass(frozen=True)
class Scenario:
    title: str
    description: str
    devices: tuple[str, ...]
    fill: Callable[[Seed], Awaitable[None]]


SCENARIOS = {
    "empty": Scenario("Empty", "The hub without any Device.", (), _nothing),
    "few-runs": Scenario(
        "3D printer, a few Runs",
        "One printer, 3 Materials and 7 Runs.",
        ("prusa",),
        _few_runs,
    ),
    "printing-now": Scenario(
        "3D printer, printing now",
        "Like a few Runs, with an open Run; the printer's helpers end it.",
        ("prusa",),
        _printing_now,
    ),
    "two-printers": Scenario(
        "Two printers",
        "Two printers with 30 Runs each over four months.",
        ("prusa", "bambu"),
        _two_printers,
    ),
    "long-history": Scenario(
        "Long history",
        "Two years of Runs on two printers, 8 Materials (one archived), a Line Item Template.",
        ("prusa", "bambu"),
        _long_history,
    ),
    "washing-machine": Scenario(
        "Washing machine",
        "A washer with energy and water meters, a detergent scale and Program "
        "Defaults; 10 loads over four weeks. Its helpers start the next one.",
        (WASHER,),
        _washing,
    ),
}


def _device(key: str) -> dict[str, Any]:
    """The Device's subentry data, as Add Device writes it."""
    if key == WASHER:
        return _washer()
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
            "running_power": PRINTERS[key][1],
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


async def async_load(hass: HomeAssistant, name: str, user: User | None) -> None:
    """Replace whatever Coin-op holds by the Scenario `name`."""
    scenario = SCENARIOS[name]
    user = user or await hass.auth.async_get_owner()
    if user is None:
        raise ScenarioError("No user to load the Scenario as")
    for old in hass.config_entries.async_entries(COINOP):
        await hass.config_entries.async_remove(old.entry_id)
    for key in PRINTERS:
        if hass.states.get(f"input_select.{key}_status"):
            await _async_set_printer(hass, key, "idle")
    if program := hass.states.get("input_select.washer_program"):
        await _async_set_washer(hass, "off", program.state)
    entry = await _async_add_hub(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    for key in scenario.devices:
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=MappingProxyType(_device(key)),
                subentry_type=SUBENTRY_DEVICE,
                title=TITLES[key],
                unique_id=None,
            ),
        )
    await hass.config_entries.async_setup(entry.entry_id)
    await scenario.fill(Seed(hass, Api(hass, user), entry))


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
