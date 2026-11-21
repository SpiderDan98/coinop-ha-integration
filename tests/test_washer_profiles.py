"""Integration Profiles for washing machines: WashData, Miele and Home Connect."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.coinop.device_config import CAPABILITIES

from .anycubic import add_anycubic_local
from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_WATER,
    add_hub,
    configure,
    start_add_device,
    start_reconfigure,
)
from .test_device_flow import suggested
from .test_integration_profiles import accepted
from .test_runs import stored_runs
from .washers import Washer, add_home_connect, add_miele, add_washdata
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
    "consumption": {"next_step_id": "energy"},
    "price": {"next_step_id": "fixed_price"},
    "fixed_price": {"price": 0.30},
    "water": {"next_step_id": "water_none"},
    "water_price": {"next_step_id": "water_fixed_price"},
    "water_fixed_price": {"price": 4.0},
}


async def walk_pre_filled(
    hass: HomeAssistant, entry: ConfigEntry, washer: Washer, **answers: Any
) -> tuple[list[str], ConfigSubentry]:
    """Add Device accepting every pre-filled form; `answers` (by step id) answer the
    menus and the forms nothing pre-fills. Returns the steps shown and the Device."""
    answers = ANSWERS | answers
    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=washer.device.id, device_type="washing_machine"
        ),
        {"name": "Washer"},
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
    washer = add_miele(hass, consumption=False)
    entry = await add_hub(hass)
    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=washer.device.id, device_type="washing_machine"
        ),
        {"name": "Washer"},
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
    assert shown == ["status", "mapping", "program"]
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


@pytest.mark.parametrize(
    ("device_type", "integrations"),
    [
        ("3d_printer", "Anycubic 3D Printer - Local Control, Anycubic Cloud & LAN"),
        ("washing_machine", "WashData, Miele, Home Connect"),
    ],
)
async def test_the_ha_device_step_names_the_integrations_known_for_the_device_type(
    hass: HomeAssistant, device_type: str, integrations: str
) -> None:
    entry = await add_hub(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )

    result = await configure(hass, result, {"device_type": device_type})

    assert result["step_id"] == "device"
    assert result["description_placeholders"] == {"integrations": integrations}


async def test_a_device_type_no_integration_serves_names_none_and_pre_fills_nothing(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(CAPABILITIES, "kiln", frozenset())
    washer = add_miele(hass)
    entry = await add_hub(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    result = await configure(hass, result, {"device": "manual"})

    result = await configure(hass, result, {"device_type": "kiln"})

    assert result["step_id"] == "device"
    assert result["description_placeholders"] == {"integrations": ""}
    result = await configure(hass, result, {"device": washer.device.id})
    result = await configure(hass, result, {"name": "Kiln"})
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
