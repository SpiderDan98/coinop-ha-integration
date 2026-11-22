"""Integration Profiles for washing machines: WashData, Miele and Home Connect."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_WATER,
    add_hub,
    configure,
    open_device_types,
    start_add_device,
    start_reconfigure,
)
from .registry import (
    HaDevice,
    add_anycubic_local,
    add_home_connect,
    add_miele,
    add_washdata,
)
from .test_device_flow import suggested
from .test_integration_profiles import accepted
from .test_program_consumption import set_rows
from .test_quick_start import quick_start, register
from .test_runs import stored_runs
from .websocket import PanelClient

# What WashData's program sensor reports while no program is recognised.
WASHDATA_PLACEHOLDERS = [
    "off",
    "starting",
    "detecting...",
    "restored...",
    "none",
    "unknown",
]

ANSWERS = {
    "name": {"name": "Washer"},
    "consumption": {"next_step_id": "energy"},
    "price": {"next_step_id": "fixed_price"},
    "fixed_price": {"price": 0.30},
    "water": {"next_step_id": "water_none"},
    "water_price": {"next_step_id": "water_fixed_price"},
    "water_fixed_price": {"price": 4.0},
}


async def walk_pre_filled(
    hass: HomeAssistant,
    entry: ConfigEntry,
    washer: HaDevice,
    device_type: str = "washing_machine",
    **answers: Any,
) -> tuple[list[str], ConfigSubentry]:
    """Add Device as `device_type`, accepting every pre-filled form; `answers` (by
    step id) answer the menus and the forms nothing pre-fills. Returns the steps
    shown and the Device."""
    answers = ANSWERS | answers
    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=washer.device.id, device_type=device_type
        ),
        answers["name"],
    )
    shown = []
    while result["type"] is not FlowResultType.CREATE_ENTRY:
        step = result["step_id"]
        shown.append(step)
        result = await configure(
            hass, result, answers[step] if step in answers else accepted(result)
        )
        assert not result.get("errors"), result["errors"]
    return shown, list(entry.subentries.values())[-1]


async def test_washdata_fills_status_mapping_and_program(hass: HomeAssistant) -> None:
    washer = add_washdata(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(
        hass, entry, washer, energy={"entity_id": WASHER_ENERGY}
    )

    assert shown == [
        "status",
        "mapping",
        "program",
        "progress",
        "consumption",
        "energy",
        "price",
        "fixed_price",
        "water",
    ]
    data = subentry.data
    assert data["status"] == {"entity_id": washer["washer_state"], "attribute": None}
    assert data["mapping"] == {
        "running": ["running", "ending"],
        "paused": ["paused", "user_paused"],
        "finished": ["finished", "anti_wrinkle", "clean"],
        "cancelled": ["interrupted", "force_stopped"],
        "ended": [],
        "fault": [],
        "ignored": ["off", "idle", "starting", "delay_wait", "unknown"],
    }
    assert data["program"] == {
        "entity_id": washer["washer_program"],
        "attribute": None,
        "ignored": WASHDATA_PLACEHOLDERS,
    }
    assert data["progress"] == {
        "remaining_time": washer["time_remaining"],
        "progress": washer["cycle_progress"],
        "expected_energy": {
            "entity_id": washer["cycle_progress"],
            "attribute": "projected_energy_kwh",
            "form": "total",
        },
    }
    # The plug's meter, which the user picked: WashData's own sensors are ignored.
    assert data["consumption"]["entity_id"] == WASHER_ENERGY
    stored = str(dict(data))
    for key in (
        "current_power",
        "energy_total",
        "last_cycle_energy",
        "last_cycle_cost",
    ):
        assert washer[key] not in stored


async def test_washdatas_anti_wrinkle_completes_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    washer = add_washdata(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, washer, energy={"entity_id": WASHER_ENERGY})

    async def report(state: str) -> None:
        hass.states.async_set(washer["washer_state"], state)
        await hass.async_block_till_done()

    hass.states.async_set(washer["washer_program"], "Cotton 60")
    await report("starting")
    await report("running")
    await clock.advance(minutes=90)
    await report("anti_wrinkle")
    hass.states.async_set(WASHER_ENERGY, "101.2", {"unit_of_measurement": "kWh"})
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["program"] == "Cotton 60"


async def test_washdatas_projected_energy_leaves_what_the_plug_measured(
    hass: HomeAssistant, clock: Clock
) -> None:
    washer = add_washdata(hass)
    remaining = "sensor.washer_time_left"
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    progress = {"remaining_time": remaining} | accepted_progress(washer)
    await walk_pre_filled(
        hass, entry, washer, energy={"entity_id": WASHER_ENERGY}, progress=progress
    )

    async def report(kwh: float, projected: float) -> None:
        hass.states.async_set(WASHER_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
        hass.states.async_set(
            washer["cycle_progress"], "40", {"projected_energy_kwh": projected}
        )
        await hass.async_block_till_done()

    hass.states.async_set(washer["washer_state"], "running")
    await clock.advance(minutes=30)
    hass.states.async_set(remaining, "60", {"unit_of_measurement": "min"})
    await report(100.6, 1.1)

    # 0.6 kWh so far and the 0.5 WashData expects on top, not 1.2 kW for the hour left.
    state = hass.states.get("sensor.washer_projected_run_cost")
    assert state is not None
    assert float(state.state) == pytest.approx(0.18 + 0.15)

    await clock.advance(minutes=5)
    await report(100.7, 0.5)
    state = hass.states.get("sensor.washer_projected_run_cost")
    assert state is not None
    assert float(state.state) == pytest.approx(0.21)


async def test_washdatas_projected_energy_comes_before_the_programs_default(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    washer = add_washdata(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(
        hass, entry, washer, energy={"entity_id": WASHER_ENERGY}
    )
    await set_rows(panel, subentry)

    hass.states.async_set(washer["washer_state"], "running")
    await clock.advance(minutes=30)
    hass.states.async_set(WASHER_ENERGY, "100.6", {"unit_of_measurement": "kWh"})
    hass.states.async_set(washer["cycle_progress"], "40", {"projected_energy_kwh": 1.1})
    await hass.async_block_till_done()

    # The 0.5 kWh WashData expects on top, not the 0.2 the Default row's 0.8 leave.
    state = hass.states.get("sensor.washer_projected_run_cost")
    assert state is not None
    assert float(state.state) == pytest.approx(0.18 + 0.15)


def accepted_progress(washer: HaDevice) -> dict[str, Any]:
    """The progress step's fields as WashData's profile pre-fills them."""
    return {
        "expected_energy": washer["cycle_progress"],
        "expected_energy_attribute": "projected_energy_kwh",
        "expected_energy_form": "total",
    }


async def test_miele_fills_status_program_and_both_meters(
    hass: HomeAssistant,
) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(
        hass, entry, washer, water={"next_step_id": "water_meter"}
    )

    # Pre-filled, but every step is still shown.
    assert shown == [
        "status",
        "mapping",
        "program",
        "progress",
        "consumption",
        "energy",
        "price",
        "fixed_price",
        "water",
        "water_meter",
        "water_price",
        "water_fixed_price",
    ]
    data = subentry.data
    assert data["status"] == {
        "entity_id": "sensor.washing_machine_status",
        "attribute": None,
    }
    assert data["mapping"] == {
        "running": ["in_use"],
        "paused": ["pause", "rinse_hold"],
        "finished": ["program_ended"],
        "cancelled": ["program_interrupted"],
        "ended": [],
        "fault": ["failure"],
        "ignored": [
            "off",
            "on",
            "programmed",
            "waiting_to_start",
            "idle",
            "service",
            "not_connected",
        ],
    }
    assert data["program"] == {
        "entity_id": "sensor.washing_machine_program",
        "attribute": None,
    }
    # Miele reports no progress.
    assert data["progress"] == {
        "remaining_time": "sensor.washing_machine_remaining_time",
        "progress": None,
        "expected_energy": None,
    }
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": "sensor.washing_machine_energy_consumption",
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert data["water"] == {
        "source": "meter",
        "entity_id": "sensor.washing_machine_water_consumption",
        "attribute": None,
        "unit": "L",
        "factor": None,
    }


async def test_a_miele_without_consumption_sensors_leaves_the_meters_empty(
    hass: HomeAssistant,
) -> None:
    coffee_system = add_miele(hass, "Coffee system")
    entry = await add_hub(hass)
    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=coffee_system.device.id, device_type="coffee_machine"
        ),
        {"name": "Coffee"},
    )
    while result["step_id"] != "consumption":
        result = await configure(hass, result, accepted(result))

    result = await configure(hass, result, {"next_step_id": "energy"})

    assert suggested(result, "entity_id") is None


async def test_home_connect_fills_status_mapping_and_program(
    hass: HomeAssistant,
) -> None:
    washer = add_home_connect(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(
        hass, entry, washer, energy={"entity_id": WASHER_ENERGY}
    )

    data = subentry.data
    assert data["status"] == {
        "entity_id": "sensor.washer_operation_state",
        "attribute": None,
    }
    assert data["mapping"] == {
        "running": ["run"],
        "paused": ["pause", "actionrequired"],
        "finished": ["finished"],
        "cancelled": ["aborting"],
        "ended": [],
        "fault": ["error"],
        "ignored": ["inactive", "ready", "delayedstart"],
    }
    # The active program, not the one picked for the next start.
    assert data["program"] == {
        "entity_id": "select.washer_active_program",
        "attribute": None,
    }
    assert data["progress"] == {
        "remaining_time": "sensor.washer_program_finish_time",
        "progress": "sensor.washer_program_progress",
        "expected_energy": None,
    }


@pytest.mark.parametrize(
    ("appliance_type", "device_type"),
    [
        ("Dishwasher", "dishwasher"),
        ("Dryer", "tumble_dryer"),
        ("CoffeeMaker", "coffee_machine"),
        ("Oven", "oven"),
        # The kind the integration's entities tell isn't asked: a washer as an
        # oven, and a hood, which Quick Start doesn't offer.
        ("Washer", "oven"),
        ("Hood", "washing_machine"),
    ],
)
async def test_manual_setup_pre_fills_every_device_type_home_connect_serves(
    hass: HomeAssistant, appliance_type: str, device_type: str
) -> None:
    appliance = add_home_connect(hass, appliance_type, name="Appliance")
    entry = await add_hub(hass)

    _, subentry = await walk_pre_filled(
        hass, entry, appliance, device_type, consumption={"next_step_id": "per_program"}
    )

    data = subentry.data
    assert data["device_type"] == device_type
    assert data["status"] == {
        "entity_id": "sensor.appliance_operation_state",
        "attribute": None,
    }
    assert data["mapping"]["running"] == ["run"]
    assert data["mapping"]["ignored"] == ["inactive", "ready", "delayedstart"]
    assert data["program"] == {
        "entity_id": "select.appliance_active_program",
        "attribute": None,
    }


async def test_detect_again_works_on_a_dishwasher_added_from_home_connect(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    dishwasher = add_home_connect(hass, "Dishwasher", name="Dishwasher")
    entry = await add_hub(hass)
    before = await quick_start(
        hass, entry, dishwasher.device.id, price=0.3, water_price=4.0
    )
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            dishwasher[key], new_entity_id=dishwasher[key].replace("dishwasher", "dw")
        ).entity_id
        for key in (
            "BSH.Common.Status.OperationState",
            "BSH.Common.Root.ActiveProgram",
        )
    }

    result = await configure(
        hass, await start_reconfigure(hass, entry, subentry), {"next_step_id": "detect"}
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "program", "progress"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["device_type"] == "dishwasher"
    assert data["status"]["entity_id"] == renamed["BSH.Common.Status.OperationState"]
    assert data["program"]["entity_id"] == renamed["BSH.Common.Root.ActiveProgram"]
    for section in ("consumption", "price", "water", "water_price"):
        assert data[section] == before[section]


async def test_detect_again_leaves_electricity_water_and_prices_alone(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    washer = add_miele(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_WATER, "1000", {"unit_of_measurement": "L"})
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(
        hass,
        entry,
        washer,
        energy={"entity_id": WASHER_ENERGY},
        water={"next_step_id": "water_meter"},
        water_meter={"entity_id": WASHER_WATER},
    )
    before = dict(subentry.data)
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            washer[key], new_entity_id=washer[key].replace("washing_machine", "wm")
        ).entity_id
        for key in ("state_status", "state_program_id")
    }
    menu = await start_reconfigure(hass, entry, subentry)
    assert menu["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "water",
        "water_price",
        "detect",
        "save",
    ]

    result = await configure(hass, menu, {"next_step_id": "detect"})
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "program", "progress"]
    assert result["step_id"] == "reconfigure"
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"]["entity_id"] == renamed["state_status"]
    assert data["program"]["entity_id"] == renamed["state_program_id"]
    for section in ("consumption", "price", "water", "water_price"):
        assert data[section] == before[section]


async def test_profiles_only_detect_for_their_device_type(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    washer = add_miele(hass)
    entry = await add_hub(hass)

    for device, device_type in (
        (printer.device.id, "washing_machine"),
        (washer.device.id, "3d_printer"),
    ):
        result = await configure(
            hass,
            await start_add_device(
                hass, entry, printer=device, device_type=device_type
            ),
            {"name": "Mismatched"},
        )
        assert result["step_id"] == "status"
        assert suggested(result, "entity_id") is None


@pytest.mark.parametrize("kind", ["generic", "dishwasher"])
async def test_manual_setup_pre_fills_the_chosen_device_type_whatever_kind_is_told(
    hass: HomeAssistant, kind: str
) -> None:
    plug = add_washdata(hass, kind)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(
        hass, entry, plug, "oven", consumption={"next_step_id": "per_program"}
    )

    assert shown == [
        "status",
        "mapping",
        "program",
        "progress",
        "consumption",
        "price",
        "fixed_price",
    ]
    data = subentry.data
    assert data["device_type"] == "oven"
    assert data["status"] == {"entity_id": plug["washer_state"], "attribute": None}
    assert data["mapping"]["finished"] == ["finished", "anti_wrinkle", "clean"]
    assert data["program"] == {
        "entity_id": plug["washer_program"],
        "attribute": None,
        "ignored": WASHDATA_PLACEHOLDERS,
    }


@pytest.mark.parametrize(
    ("model", "device_type", "steps"),
    [
        (
            "Dishwasher",
            "dishwasher",
            [
                "consumption",
                "energy",
                "price",
                "fixed_price",
                "water",
                "water_meter",
                "water_price",
                "water_fixed_price",
            ],
        ),
        (
            "Tumble dryer",
            "tumble_dryer",
            ["consumption", "energy", "price", "fixed_price"],
        ),
        # Miele tells a warming drawer is no Device Type; the user's choice counts.
        ("Warming drawer", "oven", ["consumption", "price", "fixed_price"]),
    ],
)
async def test_manual_setup_pre_fills_from_a_miele_appliance_of_any_kind(
    hass: HomeAssistant, model: str, device_type: str, steps: list[str]
) -> None:
    appliance = add_miele(hass, model)
    entry = await add_hub(hass)
    energy = appliance.entities.get("current_energy_consumption")
    water = appliance.entities.get("current_water_consumption")

    shown, subentry = await walk_pre_filled(
        hass,
        entry,
        appliance,
        device_type,
        consumption={"next_step_id": "energy" if energy else "per_program"},
        water={"next_step_id": "water_meter"},
    )

    assert shown == ["status", "mapping", "program", "progress", *steps]
    data = subentry.data
    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": appliance["state_status"], "attribute": None}
    assert data["mapping"]["finished"] == ["program_ended"]
    assert data["program"] == {
        "entity_id": appliance["state_program_id"],
        "attribute": None,
    }
    assert data["consumption"].get("entity_id") == energy
    assert data.get("water", {}).get("entity_id") == water


async def test_a_tumble_dryer_added_from_a_miele_washing_machine_takes_no_water(
    hass: HomeAssistant,
) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)

    shown, subentry = await walk_pre_filled(hass, entry, washer, "tumble_dryer")

    assert shown == [
        "status",
        "mapping",
        "program",
        "progress",
        "consumption",
        "energy",
        "price",
        "fixed_price",
    ]
    data = subentry.data
    assert sorted(data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "progress",
        "status",
    ]
    assert data["consumption"]["entity_id"] == washer["current_energy_consumption"]
    assert washer["current_water_consumption"] not in str(dict(data))


async def test_detect_again_works_on_a_tumble_dryer_added_from_miele(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    dryer = add_miele(hass, "Tumble dryer")
    entry = await add_hub(hass)
    before = await quick_start(hass, entry, dryer.device.id, price=0.3)
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            dryer[key], new_entity_id=dryer[key].replace("tumble_dryer", "td")
        ).entity_id
        for key in (
            "state_status",
            "state_program_id",
            "current_energy_consumption",
        )
    }

    result = await configure(
        hass, await start_reconfigure(hass, entry, subentry), {"next_step_id": "detect"}
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "program", "progress"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["device_type"] == "tumble_dryer"
    assert data["status"]["entity_id"] == renamed["state_status"]
    assert data["program"]["entity_id"] == renamed["state_program_id"]
    # The meter Quick Start took from the profile is the user's from then on.
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]


async def test_a_device_type_washdata_doesnt_serve_pre_fills_nothing(
    hass: HomeAssistant,
) -> None:
    plug = add_washdata(hass, "generic")
    entry = await add_hub(hass)

    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=plug.device.id, device_type="3d_printer"
        ),
        {"name": "Plug"},
    )

    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") is None


async def test_detect_again_works_on_a_dishwasher_added_from_washdata(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    dishwasher = add_washdata(hass, "dishwasher")
    register(hass, WASHER_ENERGY, "kWh")
    entry = await add_hub(hass)
    before = await quick_start(
        hass,
        entry,
        dishwasher.device.id,
        optional_meter=WASHER_ENERGY,
        price=0.3,
        water_price=4.0,
    )
    [subentry] = entry.subentries.values()
    # An update of the integration renamed its entities.
    renamed = {
        key: entity_registry.async_update_entity(
            dishwasher[key], new_entity_id=dishwasher[key].replace("washer", "wd")
        ).entity_id
        for key in ("washer_state", "washer_program")
    }

    result = await configure(
        hass, await start_reconfigure(hass, entry, subentry), {"next_step_id": "detect"}
    )
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping", "program", "progress"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["device_type"] == "dishwasher"
    assert data["status"]["entity_id"] == renamed["washer_state"]
    assert data["program"]["entity_id"] == renamed["washer_program"]
    assert data["program"]["ignored"] == WASHDATA_PLACEHOLDERS
    for section in ("consumption", "price", "water", "water_price"):
        assert data[section] == before[section]


@pytest.mark.parametrize(
    ("device_type", "integrations"),
    [
        (
            "3d_printer",
            "Anycubic 3D Printer - Local Control, Anycubic Cloud & LAN, Bambu Lab, "
            "PrusaLink, OctoPrint, Creality, Elegoo, Moonraker",
        ),
        (
            "washing_machine",
            "WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, "
            "LG ThinQ, SmartThings",
        ),
        (
            "dishwasher",
            "WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, "
            "LG ThinQ, SmartThings",
        ),
        (
            "tumble_dryer",
            "WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, "
            "LG ThinQ, SmartThings",
        ),
        (
            "coffee_machine",
            "WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt",
        ),
        (
            "oven",
            "WashData, Miele, Home Connect, Home Connect Local, Home Connect Alt, "
            "LG ThinQ, SmartThings",
        ),
    ],
)
async def test_the_ha_device_step_names_the_integrations_known_for_the_device_type(
    hass: HomeAssistant, device_type: str, integrations: str
) -> None:
    entry = await add_hub(hass)
    result = await open_device_types(hass, entry)

    result = await configure(hass, result, {"device_type": device_type})

    assert result["step_id"] == "device"
    assert result["description_placeholders"] == {"integrations": integrations}


async def test_a_device_type_no_integration_serves_names_none_and_pre_fills_nothing(
    hass: HomeAssistant,
) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    result = await configure(hass, result, {"device": "manual"})

    result = await configure(hass, result, {"device_type": "robotic_mower"})

    assert result["step_id"] == "device_without_profile"
    assert not result["description_placeholders"]
    result = await configure(hass, result, {"device": washer.device.id})
    assert result["step_id"] == "name"
    result = await configure(hass, result, {"name": "Mower"})
    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") is None


async def test_washdatas_placeholder_programs_never_name_a_run_or_a_row(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    washer = add_washdata(hass)
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    await walk_pre_filled(hass, entry, washer, energy={"entity_id": WASHER_ENERGY})

    async def report(state: str, program: str) -> None:
        hass.states.async_set(
            washer["washer_program"], program, {"options": ["Cotton 60", "none"]}
        )
        hass.states.async_set(washer["washer_state"], state)
        await hass.async_block_till_done()
        await clock.advance(minutes=30)

    await report("starting", "off")
    await report("running", "detecting...")
    await report("finished", "detecting...")
    await report("running", "detecting...")
    await report("running", "Cotton 60")
    await report("running", "detecting...")
    await report("finished", "off")
    hass.states.async_set(WASHER_ENERGY, "101.2", {"unit_of_measurement": "kWh"})
    await clock.advance(minutes=10)

    assert [(run.get("program"), run["name"]) for run in stored_runs(hass_storage)] == [
        (None, None),
        ("Cotton 60", "Cotton 60"),
    ]
    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["known_programs"] == ["Cotton 60"]
