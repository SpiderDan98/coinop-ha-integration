"""The Pieces: what a Scenario is made of."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar

from homeassistant.config_entries import SOURCE_USER

from custom_components.coinop.const import DOMAIN as COINOP
from custom_components.coinop.device_config import DEVICE_TYPES

from ..stand_ins import Registration, appliances, ev_chargers, printers
from . import devices, histories
from .data import (
    COOKINGS,
    DISHES,
    DISHWASHER_METERS,
    DRINKS,
    DRYER_METERS,
    IRRIGATION_WATER,
    LOADS,
    MOWS,
    SESSIONS,
    TUMBLES,
    WASHER_METERS,
    WATERINGS,
)
from .seed import Seed, async_set


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
    # Its Device is a subentry of Coin-op's own config entry.
    domain: ClassVar[str] = COINOP
    device: Mapping[str, Any]
    # The Runs of each history level but none, which leaves the Device alone.
    short: Callable[[Seed], Awaitable[None]]
    long: Callable[[Seed], Awaitable[None]]
    # The helper states that start a Run, set in this order, as its integration would
    # report one.
    start: Mapping[str, str | float]
    needs: tuple[str, ...] = ()
    # The panel settings it gets whatever its history, before its Runs.
    setup: Callable[[Seed], Awaitable[None]] | None = None

    async def fill(self, seed: Seed) -> None:
        if self.setup:
            await self.setup(seed)
        if seed.history != "none":
            await (self.short if seed.history == "short" else self.long)(seed)

    async def open_run(self, seed: Seed) -> None:
        for entity_id, value in self.start.items():
            await async_set(seed.hass, entity_id, value)


# What a stand-in's config entry is started with: the Device Type keys picked.
KINDS = "kinds"


@dataclass(frozen=True)
class QuickStartPiece(Piece):
    """An HA device of a stand-in (`stand_in.py`), registered from its integration's
    description, for Quick Start to offer."""

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


def _washdata_helpers(key: str, program: str) -> dict[str, str | float]:
    return {
        f"input_select.{key}_status": "off",
        f"input_select.{key}_program": program,
        f"input_number.{key}_energy": 0,
    }


# One ThinQ device, which the integration registers as an HA device per half.
_washtower = partial(
    appliances.lg_thinq,
    "DEVICE_WASHTOWER",
    name="WashTower",
    device_id="WT1-5B2E0C14-7F3A-4D8E-9A61-0C2D4E6F8A10",
)


PIECES: dict[str, DeviceWithHistory | QuickStartPiece] = {
    "prusa": DeviceWithHistory(
        "3d_printer",
        "Prusa MK4",
        "Short history: 7 Runs over seven weeks on 3 of the 8 filaments; long: two "
        "years of Runs on all 8. With Tags and Thumbnails.",
        _printer_helpers("prusa"),
        device=devices.printer("prusa"),
        short=histories.prusa,
        long=partial(histories.printer_years, printer="prusa", gaps=range(1, 7)),
        start={
            "input_text.prusa_job": "Gridfinity bins 3x2.gcode",
            "input_select.prusa_status": "printing",
        },
        needs=("filaments", "tags", "template"),
    ),
    "bambu": DeviceWithHistory(
        "3d_printer",
        "Bambu Lab X1C",
        "Short history: 10 Runs over six weeks on 5 of the 8 filaments; long: two "
        "years of Runs on all 8. With Tags and Thumbnails.",
        _printer_helpers("bambu"),
        device=devices.printer("bambu"),
        short=histories.bambu,
        long=partial(histories.printer_years, printer="bambu", gaps=range(3, 10)),
        start={
            "input_text.bambu_job": "Spool holder.gcode",
            "input_select.bambu_status": "printing",
        },
        needs=("filaments", "tags", "template"),
    ),
    "anycubic.3d_printer": QuickStartPiece(
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
        registration=printers.anycubic_cloud,
    ),
    "bambu_lab.3d_printer": QuickStartPiece(
        "3d_printer",
        "P1S · Bambu Lab",
        "A printer with an AMS and its plug sensor as meter; set its print status "
        "in the developer tools to run it.",
        {"input_number.p1s_power": 0},
        registration=printers.bambu_lab,
    ),
    "prusalink.3d_printer": QuickStartPiece(
        "3d_printer",
        "Prusa Core One · PrusaLink",
        "A printer with its job preview and its plug sensor as meter; set its state "
        "in the developer tools to run it.",
        {"input_number.core_one_power": 0},
        # Named apart from the Prusa MK4 Device with history.
        registration=partial(printers.prusalink, title="Prusa Core One"),
    ),
    "octoprint.3d_printer": QuickStartPiece(
        "3d_printer",
        "OctoPrint · OctoPrint",
        "A printer with a webcam and its plug sensor as meter; set its current "
        "state in the developer tools to run it.",
        {"input_number.octoprint_power": 0},
        registration=printers.octoprint,
    ),
    "ha_creality_ws.3d_printer": QuickStartPiece(
        "3d_printer",
        "K1C · Creality",
        "A printer with its print preview and its plug sensor as meter; set its "
        "print status, with the job's `file` attribute, in the developer tools to "
        "run it.",
        {"input_number.k1c_power": 0},
        registration=printers.creality,
    ),
    "elegoo_printer.3d_printer": QuickStartPiece(
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
        registration=printers.moonraker,
    ),
    "washer": DeviceWithHistory(
        "washing_machine",
        "Washing machine",
        "Energy and water meters, a detergent scale, 4 laundry products as Doses "
        "and Program Defaults. Short history: 10 loads over four weeks; long: a load "
        "every few days for two years.",
        {
            "input_select.washer_status": "off",
            "input_select.washer_program": "Cotton 60°",
            **{f"input_number.{key}": value for key, value in WASHER_METERS.items()},
        },
        device=devices.appliance("washing_machine", "washer"),
        short=partial(histories.wash, loads=LOADS),
        long=histories.washer_long,
        start={
            "input_select.washer_program": "Cotton 60°",
            "input_select.washer_status": "running",
        },
        needs=("laundry",),
        setup=histories.washer_settings,
    ),
    "ha_washdata.washing_machine": QuickStartPiece(
        "washing_machine",
        "Washing machine · WashData",
        "A washing machine WashData follows, with its plug sensor as meter; the "
        "washing machine's helpers run it.",
        _washdata_helpers("washdata_washer", "Cotton 60°"),
        registration=partial(
            appliances.washdata, "washing_machine", name="Washing machine"
        ),
    ),
    "miele.washing_machine": QuickStartPiece(
        "washing_machine",
        "Miele washing machine · Miele",
        "A washing machine with its own energy and water meters for the cycle; set "
        "its status in the developer tools to run it.",
        {},
        registration=partial(
            appliances.miele, serial="000111000001", name="Miele washing machine"
        ),
    ),
    "home_connect.washing_machine": QuickStartPiece(
        "washing_machine",
        "Siemens washer · Home Connect",
        "A washer with its plug sensor as meter; set its operation state in the "
        "developer tools to run it.",
        {"input_number.siemens_washer_energy": 0},
        registration=partial(appliances.home_connect, "Washer", name="Siemens washer"),
    ),
    "home_connect_alt.washing_machine": QuickStartPiece(
        "washing_machine",
        "Bosch washer · Home Connect Alt",
        "A washer whose kind its integration doesn't tell, so Quick Start asks for "
        "the Device Type, with its plug sensor as meter; set its operation state "
        "(`BSH.Common.EnumType.OperationState.Run`) in the developer tools to run it.",
        {"input_number.bosch_washer_energy": 0},
        registration=partial(appliances.home_connect_alt, name="Bosch washer"),
    ),
    "lg_thinq.washing_machine": QuickStartPiece(
        "washing_machine",
        "WashTower washer · LG ThinQ",
        "The washer half of a WashTower, with its plug sensor as meter, on the "
        "LG ThinQ entry its dryer half shares; set its current state in the "
        "developer tools to run it.",
        {"input_number.washtower_washer_energy": 0},
        registration=partial(_washtower, sub_id="washer"),
    ),
    "smartthings.washing_machine": QuickStartPiece(
        "washing_machine",
        "Samsung washer · SmartThings",
        "A washer, with its own energy meter; set its machine state in the "
        "developer tools to run it.",
        {},
        registration=partial(
            appliances.smartthings,
            "washer",
            name="Samsung washer",
            device_id="3b7e5c1a-2f40-4d6b-9a8e-1c5d7f9b2e04",
        ),
    ),
    "dishwasher": DeviceWithHistory(
        "dishwasher",
        "Kitchen dishwasher",
        "Energy and water meters, tabs, salt and rinse aid as Doses and Program "
        "Defaults. Short history: 10 cycles over four weeks; long: a cycle every few "
        "days for two years.",
        {
            "input_select.dishwasher_status": "off",
            "input_select.dishwasher_program": "Eco 50°",
            **{
                f"input_number.{key}": value for key, value in DISHWASHER_METERS.items()
            },
        },
        device=devices.appliance("dishwasher", "dishwasher"),
        short=partial(
            histories.replay_cycles,
            key="dishwasher",
            meters=DISHWASHER_METERS,
            cycles=DISHES,
        ),
        long=partial(
            histories.replay_years,
            key="dishwasher",
            meters=DISHWASHER_METERS,
            cycles=DISHES,
            gaps=range(3, 8),
            hours=(13, 20, 21),
        ),
        start={
            "input_select.dishwasher_program": "Eco 50°",
            "input_select.dishwasher_status": "running",
        },
        needs=("dishwasher",),
        setup=partial(
            histories.set_doses,
            device="dishwasher",
            doses={
                "tabs": "All-in-one tabs",
                "salt": "Dishwasher salt",
                "rinse_aid": "Rinse aid Shine",
            },
            defaults={
                "default": {
                    "kwh": 0.9,
                    "litres": 10,
                    "doses": {"tabs": 1, "salt": 15, "rinse_aid": 3},
                },
                "programs": {
                    "Eco 50°": {
                        "kwh": 0.8,
                        "litres": 9.5,
                        "doses": {"tabs": 1, "salt": 12, "rinse_aid": 3},
                    },
                    "Intensive 70°": {
                        "kwh": 1.45,
                        "litres": 14.5,
                        "doses": {"tabs": 1, "salt": 20, "rinse_aid": 4},
                    },
                },
            },
        ),
    ),
    "ha_washdata.dishwasher": QuickStartPiece(
        "dishwasher",
        "Dishwasher · WashData",
        "A dishwasher WashData follows, with its plug sensor as meter; the "
        "dishwasher's helpers run it.",
        _washdata_helpers("washdata_dishwasher", "Eco 50°"),
        registration=partial(appliances.washdata, "dishwasher", name="Dishwasher"),
    ),
    "miele.dishwasher": QuickStartPiece(
        "dishwasher",
        "Miele dishwasher · Miele",
        "A dishwasher with its own energy and water meters for the cycle; set its "
        "status in the developer tools to run it.",
        {},
        registration=partial(
            appliances.miele,
            "Dishwasher",
            serial="000111000002",
            name="Miele dishwasher",
        ),
    ),
    "home_connect.dishwasher": QuickStartPiece(
        "dishwasher",
        "Siemens dishwasher · Home Connect",
        "A dishwasher with its plug sensor as meter; set its operation state in the "
        "developer tools to run it.",
        {"input_number.siemens_dishwasher_energy": 0},
        registration=partial(
            appliances.home_connect, "Dishwasher", name="Siemens dishwasher"
        ),
    ),
    "homeconnect_ws.dishwasher": QuickStartPiece(
        "dishwasher",
        "Bosch Dishwasher · Home Connect Local",
        "A dishwasher whose kind its integration doesn't tell, so Quick Start asks "
        "for the Device Type, with its plug sensor as meter; set its operation state "
        "in the developer tools to run it.",
        {"input_number.bosch_dishwasher_energy": 0},
        registration=appliances.home_connect_local,
    ),
    "lg_thinq.dishwasher": QuickStartPiece(
        "dishwasher",
        "LG dishwasher · LG ThinQ",
        "A dishwasher with its washing course as program and its plug sensor as "
        "meter; set its current state in the developer tools to run it.",
        {"input_number.lg_dishwasher_energy": 0},
        registration=partial(
            appliances.lg_thinq,
            "DEVICE_DISH_WASHER",
            name="LG dishwasher",
            device_id="DW1-3C7A9E21-6B4D-4F10-8E2A-5D9C1B3F7E64",
        ),
    ),
    "smartthings.dishwasher": QuickStartPiece(
        "dishwasher",
        "Samsung dishwasher · SmartThings",
        "A dishwasher, with its own energy meter; set its machine state in the "
        "developer tools to run it.",
        {},
        registration=partial(
            appliances.smartthings,
            "dishwasher",
            name="Samsung dishwasher",
            device_id="8c1f4e2d-6a93-4b07-b5d2-9e3a7c1f6d58",
        ),
    ),
    "dryer": DeviceWithHistory(
        "tumble_dryer",
        "Heat pump dryer",
        "An energy meter, dryer sheets and fragrance as Doses and Program Defaults, "
        "no water. Short history: 9 loads over four weeks; long: a load every week or "
        "so for two years.",
        {
            "input_select.dryer_status": "off",
            "input_select.dryer_program": "Cotton cupboard dry",
            **{f"input_number.{key}": value for key, value in DRYER_METERS.items()},
        },
        device=devices.appliance("tumble_dryer", "dryer", water=None),
        short=partial(
            histories.replay_cycles, key="dryer", meters=DRYER_METERS, cycles=TUMBLES
        ),
        long=partial(
            histories.replay_years,
            key="dryer",
            meters=DRYER_METERS,
            cycles=TUMBLES,
            gaps=range(4, 11),
            hours=(10, 11, 18),
        ),
        start={
            "input_select.dryer_program": "Cotton cupboard dry",
            "input_select.dryer_status": "running",
        },
        needs=("dryer",),
        setup=partial(
            histories.set_doses,
            device="dryer",
            doses={
                "sheets": "Dryer sheets Fresh",
                "fragrance": "Dryer fragrance Lavender",
            },
            defaults={
                "default": {"kwh": 1.2, "doses": {"sheets": 1}},
                "programs": {
                    "Cotton cupboard dry": {
                        "kwh": 1.32,
                        "doses": {"sheets": 1, "fragrance": 5},
                    },
                    "Wool finish": {"kwh": 0.08, "doses": {}},
                },
            },
        ),
    ),
    "ha_washdata.tumble_dryer": QuickStartPiece(
        "tumble_dryer",
        "Tumble dryer · WashData",
        "A tumble dryer WashData follows, with its plug sensor as meter; the "
        "WashData dryer's helpers run it.",
        _washdata_helpers("washdata_dryer", "Cotton dry"),
        registration=partial(appliances.washdata, "dryer", name="Tumble dryer"),
    ),
    "miele.tumble_dryer": QuickStartPiece(
        "tumble_dryer",
        "Miele tumble dryer · Miele",
        "A tumble dryer with its own energy meter for the cycle; set its status in "
        "the developer tools to run it.",
        {},
        registration=partial(
            appliances.miele,
            "Tumble dryer",
            serial="000111000003",
            name="Miele tumble dryer",
        ),
    ),
    "home_connect.tumble_dryer": QuickStartPiece(
        "tumble_dryer",
        "Siemens dryer · Home Connect",
        "A dryer with its plug sensor as meter; set its operation state in the "
        "developer tools to run it.",
        {"input_number.siemens_dryer_energy": 0},
        registration=partial(appliances.home_connect, "Dryer", name="Siemens dryer"),
    ),
    "lg_thinq.tumble_dryer": QuickStartPiece(
        "tumble_dryer",
        "WashTower dryer · LG ThinQ",
        "The dryer half of a WashTower, with its plug sensor as meter, on the "
        "LG ThinQ entry its washer half shares; set its current state in the "
        "developer tools to run it.",
        {"input_number.washtower_dryer_energy": 0},
        registration=partial(_washtower, sub_id="dryer"),
    ),
    "smartthings.tumble_dryer": QuickStartPiece(
        "tumble_dryer",
        "Samsung dryer · SmartThings",
        "A dryer, with its own energy meter; set its machine state in the "
        "developer tools to run it.",
        {},
        registration=partial(
            appliances.smartthings,
            "dryer",
            name="Samsung dryer",
            device_id="5e9a2c7b-1d84-4f3e-a6c0-2b8d4f7e1a93",
        ),
    ),
    "coffee": DeviceWithHistory(
        "coffee_machine",
        "Espresso machine",
        "Electricity and water per Program, coffee beans and milk as Doses. Short "
        "history: 12 drinks over ten days; long: a drink every few days for two years.",
        {
            "input_select.coffee_status": "off",
            "input_select.coffee_program": "Espresso",
        },
        device=devices.appliance(
            "coffee_machine", "coffee", metered=False, water="per_program"
        ),
        short=partial(histories.replay_cycles, key="coffee", meters={}, cycles=DRINKS),
        long=partial(
            histories.replay_years,
            key="coffee",
            meters={},
            cycles=DRINKS,
            gaps=range(3, 9),
            hours=(7, 8, 15),
        ),
        start={
            "input_select.coffee_program": "Cappuccino",
            "input_select.coffee_status": "running",
        },
        needs=("coffee",),
        setup=partial(
            histories.set_doses,
            device="coffee",
            doses={"beans": "Espresso beans Crema", "milk": "Whole milk"},
            defaults={
                "default": {"kwh": 0.02, "litres": 0.125, "doses": {"beans": 8}},
                "programs": {
                    "Espresso": {"kwh": 0.012, "litres": 0.04, "doses": {"beans": 8}},
                    "Cappuccino": {
                        "kwh": 0.025,
                        "litres": 0.06,
                        "doses": {"beans": 9, "milk": 120},
                    },
                    "Latte macchiato": {
                        "kwh": 0.03,
                        "litres": 0.06,
                        "doses": {"beans": 9, "milk": 180},
                    },
                },
            },
        ),
    ),
    "miele.coffee_machine": QuickStartPiece(
        "coffee_machine",
        "Miele coffee system · Miele",
        "A coffee machine with its plug sensor as meter; set its status in the "
        "developer tools to run it.",
        {"input_number.miele_coffee_system_energy": 0},
        registration=partial(
            appliances.miele,
            "Coffee system",
            serial="000111000004",
            name="Miele coffee system",
        ),
    ),
    "home_connect.coffee_machine": QuickStartPiece(
        "coffee_machine",
        "Siemens coffee maker · Home Connect",
        "A coffee maker with its plug sensor as meter; set its operation state in "
        "the developer tools to run it.",
        {"input_number.siemens_coffee_maker_energy": 0},
        registration=partial(
            appliances.home_connect, "CoffeeMaker", name="Siemens coffee maker"
        ),
    ),
    "oven": DeviceWithHistory(
        "oven",
        "Kitchen oven",
        "A Program input and electricity from Program Defaults, without a meter. "
        "Short history: 10 meals over four weeks; long: a meal every few days for "
        "two years.",
        {
            "input_select.kitchen_oven_status": "off",
            "input_select.kitchen_oven_program": "Fan plus 180°",
        },
        device=devices.appliance("oven", "kitchen_oven", metered=False, water=None),
        short=partial(
            histories.replay_cycles, key="kitchen_oven", meters={}, cycles=COOKINGS
        ),
        long=partial(
            histories.replay_years,
            key="kitchen_oven",
            meters={},
            cycles=COOKINGS,
            gaps=range(3, 10),
            hours=(12, 13, 17, 18, 19),
        ),
        start={
            "input_select.kitchen_oven_program": "Pizza 220°",
            "input_select.kitchen_oven_status": "running",
        },
        setup=histories.oven_settings,
    ),
    "miele.oven": QuickStartPiece(
        "oven",
        "Miele oven · Miele",
        "An oven with its plug sensor as meter; set its status in the developer "
        "tools to run it.",
        {"input_number.miele_oven_energy": 0},
        registration=partial(
            appliances.miele, "Oven", serial="000111000005", name="Miele oven"
        ),
    ),
    "home_connect.oven": QuickStartPiece(
        "oven",
        "Siemens oven · Home Connect",
        "An oven with its plug sensor as meter; set its operation state in the "
        "developer tools to run it.",
        {"input_number.siemens_oven_energy": 0},
        registration=partial(appliances.home_connect, "Oven", name="Siemens oven"),
    ),
    "lg_thinq.oven": QuickStartPiece(
        "oven",
        "LG oven · LG ThinQ",
        "An oven with its plug sensor as meter; set its oven current state in the "
        "developer tools to run it.",
        {"input_number.lg_oven_energy": 0},
        registration=partial(
            appliances.lg_thinq,
            "DEVICE_OVEN",
            name="LG oven",
            device_id="OV1-8D4F2A63-1E5B-4C97-B3D0-7A6E9F2C4B18",
        ),
    ),
    "smartthings.oven": QuickStartPiece(
        "oven",
        "Samsung oven · SmartThings",
        "An oven, with its own energy meter; set its machine state in the "
        "developer tools to run it.",
        {},
        registration=partial(
            appliances.smartthings,
            "oven",
            name="Samsung oven",
            device_id="a4d81f6e-7c25-4e9b-8f13-6d2b9a5c3e70",
        ),
    ),
    "charger": DeviceWithHistory(
        "ev_charger",
        "Carport charger",
        "A session energy sensor that counts each charge from 0; a car left plugged "
        "in once full is Paused. Short history: 10 charges over four weeks; long: a "
        "charge every few days for two years.",
        {
            "input_select.carport_charger_status": "disconnected",
            "input_number.carport_charger_session": 0,
        },
        device=devices.charger(),
        short=partial(histories.charge, sessions=SESSIONS),
        long=histories.charger_long,
        start={"input_select.carport_charger_status": "charging"},
    ),
    "tesla_wall_connector.ev_charger": QuickStartPiece(
        "ev_charger",
        "Tesla Wall Connector · Tesla Wall Connector",
        "A charger with its own lifetime energy meter; the Wall Connector's helpers "
        "run it.",
        {"input_select.wall_connector_status": "not_connected"},
        registration=ev_chargers.wall_connector,
    ),
    "evcc_intg.ev_charger": QuickStartPiece(
        "ev_charger",
        "evcc ☀️🚘 Solar Charging [evcc] · evcc",
        "A site with one loadpoint, metered by its session counter, and a vehicle; "
        "set its charging state to `on` in the developer tools to run it.",
        {},
        registration=ev_chargers.evcc_site,
    ),
    "ocpp.ev_charger": QuickStartPiece(
        "ev_charger",
        "charger Connector 1 and 2 · OCPP",
        "A charge point with two connectors, each a Device of its own with its "
        "energy meter; set a connector's status to `Charging` in the developer "
        "tools to run it.",
        {},
        registration=partial(ev_chargers.charge_point, connectors=2),
    ),
    "easee.ev_charger": QuickStartPiece(
        "ev_charger",
        "Garage · Easee",
        "A charger with its lifetime energy counter; set its status to `charging` "
        "in the developer tools to run it.",
        {},
        registration=ev_chargers.easee,
    ),
    "zaptec.ev_charger": QuickStartPiece(
        "ev_charger",
        "Driveway · Zaptec",
        "A charger in its installation, metered by its session counter; set its "
        "operation mode to `connected_charging` in the developer tools to run it.",
        {},
        registration=ev_chargers.zaptec,
    ),
    "goecharger_mqtt.ev_charger": QuickStartPiece(
        "ev_charger",
        "go-eCharger · go-e Charger MQTT",
        "A charger with its lifetime energy counter in Wh; set its car state to "
        "`charging` in the developer tools to run it.",
        {},
        registration=ev_chargers.goe_mqtt,
    ),
    "goecharger_api2.ev_charger": QuickStartPiece(
        "ev_charger",
        "go-e Charger · go-e Charger API v2",
        "A charger with its lifetime energy counter; set its car state to "
        "`Charging` in the developer tools to run it.",
        {},
        registration=ev_chargers.goe_api2,
    ),
    "wallbox.ev_charger": QuickStartPiece(
        "ev_charger",
        "Wallbox Garage · Wallbox",
        "A charger with its session energy counter; set its status description "
        "to `Charging` in the developer tools to run it.",
        {},
        registration=ev_chargers.wallbox,
    ),
    "mower": DeviceWithHistory(
        "robotic_mower",
        "Robotic mower",
        "Its charging station's energy meter, charging after mowing as Paused, and "
        "a mow it got stuck on as a Fault. Short history: 10 mows over three weeks; "
        "long: two summers of them.",
        {
            "input_select.robotic_mower_status": "parked",
            "input_number.robotic_mower_station_energy": 85.0,
        },
        device=devices.mower(),
        short=partial(histories.mow, mows=MOWS),
        long=histories.mower_long,
        start={"input_select.robotic_mower_status": "mowing"},
    ),
    "irrigation": DeviceWithHistory(
        "other",
        "Garden valve",
        'An Other Device under the Type Name "Irrigation" with water on a water '
        "meter and the electricity source None, each watering costing only its "
        "water. Short history: 6 waterings over two weeks; long: two summers of them.",
        {
            "input_select.irrigation_status": "off",
            "input_number.irrigation_water": IRRIGATION_WATER,
        },
        device=devices.garden_valve(),
        short=partial(histories.water, waterings=WATERINGS),
        long=histories.irrigation_long,
        start={"input_select.irrigation_status": "watering"},
    ),
}


def ordered(names: Iterable[str]) -> list[str]:
    """The Pieces `names` in group, then Piece order."""
    picked = set(names)
    return sorted(
        (name for name in PIECES if name in picked),
        key=lambda name: DEVICE_TYPES.index(PIECES[name].group),
    )
