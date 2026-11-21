"""Integration Profiles for EV chargers: Easee, Zaptec, go-e Charger MQTT and API v2."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .chargers import add_easee, add_goe_api2, add_goe_mqtt, add_zaptec
from .clock import Clock
from .devices import ENERGY, add_hub, configure, start_reconfigure
from .registry import HaDevice
from .test_device_flow import fields, suggested
from .test_integration_profiles import accepted
from .test_measured import electricity
from .test_quick_start import offered, open_add_device, pick, quick_start, register
from .test_runs import stored_runs


def full(**values: list[str]) -> dict[str, list[str]]:
    targets = ("running", "paused", "finished", "cancelled", "ended", "fault")
    return {target: values.get(target, []) for target in (*targets, "ignored")}


@dataclass(frozen=True)
class Charger:
    """A charger fixture, what its profile pre-fills and the Status of a session."""

    add: Callable[..., HaDevice]
    label: str
    status: str
    mapping: dict[str, list[str]]
    # The counter Quick Start takes, and the one it takes without it.
    counter: str
    fallback: str
    # By unplugged, plugged, charging, paused, done and fault.
    states: dict[str, str]
    unit: str = "kWh"
    # The counter's reading in kWh before the session.
    start: float = 1200


EASEE = Charger(
    add_easee,
    "Garage · Easee",
    "status",
    full(
        running=["charging"],
        paused=[
            "awaiting_start",
            "completed",
            "ready_to_charge",
            "awaiting_authorization",
            "de_authorizing",
            "start_charging",
            "stop_charging",
            "awaiting_load_balancing",
            "awaiting_smart_start",
            "awaiting_scheduled_start",
            "authenticating",
            "paused_due_to_equalizer",
        ],
        finished=["disconnected"],
        fault=[
            "error",
            "erratic_ev",
            "error_temperature_too_high",
            "error_dead_powerboard",
            "error_overcurrent",
            "error_pen_fault",
        ],
        ignored=["offline", "searching_for_master"],
    ),
    "lifetime_energy",
    "session_energy",
    {
        "unplugged": "disconnected",
        "plugged": "awaiting_start",
        "charging": "charging",
        "paused": "awaiting_smart_start",
        "done": "completed",
        "fault": "error_overcurrent",
    },
)
# Its lifetime counter lags up to an hour, so the session counter comes first.
ZAPTEC = Charger(
    add_zaptec,
    "Driveway · Zaptec",
    "charger_operation_mode",
    full(
        running=["connected_charging"],
        paused=["connected_requesting", "connected_finished"],
        finished=["disconnected"],
        ignored=["unknown"],
    ),
    "total_charge_power_session",
    "signed_meter_value_kwh",
    {
        "unplugged": "disconnected",
        "plugged": "connected_requesting",
        "charging": "connected_charging",
        "paused": "connected_requesting",
        "done": "connected_finished",
    },
    start=0,
)
GOE_MQTT = Charger(
    add_goe_mqtt,
    "go-eCharger · go-e Charger MQTT",
    "car",
    full(
        running=["charging"],
        paused=["wait_for_car", "complete"],
        finished=["idle"],
        fault=["error", "unknown_error"],
    ),
    "eto",
    "wh",
    {
        "unplugged": "idle",
        "plugged": "wait_for_car",
        "charging": "charging",
        "paused": "wait_for_car",
        "done": "complete",
        "fault": "error",
    },
    unit="Wh",
)
# Its car state is a display text in HA's language: German, else English.
GOE_API2 = Charger(
    add_goe_api2,
    "go-e Charger · go-e Charger API v2",
    "car_value",
    full(
        running=["Charging", "Laden"],
        paused=["Wait for car", "Warte auf Fahrzeug", "Complete", "Abgeschlossen"],
        finished=["Idle", "Inaktiv/Frei"],
        fault=["Error", "Fehler", "Unknown/Error", "Unbekannt/Fehler"],
    ),
    "eto",
    "wh",
    {
        "unplugged": "Idle",
        "plugged": "Wait for car",
        "charging": "Charging",
        "paused": "Wait for car",
        "done": "Complete",
        "fault": "Error",
    },
)
GOE_API2_GERMAN = replace(
    GOE_API2,
    states={
        "unplugged": "Inaktiv/Frei",
        "plugged": "Warte auf Fahrzeug",
        "charging": "Laden",
        "paused": "Warte auf Fahrzeug",
        "done": "Abgeschlossen",
        "fault": "Fehler",
    },
)

CHARGERS = {
    "easee": EASEE,
    "zaptec": ZAPTEC,
    "goecharger_mqtt": GOE_MQTT,
    "goecharger_api2": GOE_API2,
}
SESSIONS = CHARGERS | {"goecharger_api2-de": GOE_API2_GERMAN}
# Zaptec reports no fault.
FAULTS = {
    key: charger for key, charger in SESSIONS.items() if "fault" in charger.states
}


def each(chargers: dict[str, Charger]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize("charger", chargers.values(), ids=chargers)


@each(CHARGERS)
async def test_quick_start_adds_the_charger_with_its_energy_counter(
    hass: HomeAssistant, charger: Charger
) -> None:
    device = charger.add(hass)
    entry = await add_hub(hass)

    # Not a Zaptec installation, which finds its chargers' Status through them.
    assert offered(await open_add_device(hass, entry))[:-1] == [
        {"value": device.device.id, "label": charger.label}
    ]
    result = await pick(hass, entry, device.device.id)
    assert fields(result) == ["price", "price_entity"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["device_type"] == "ev_charger"
    assert data["status"] == {"entity_id": device[charger.status], "attribute": None}
    assert data["mapping"] == charger.mapping
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": device[charger.counter],
        "attribute": None,
        "unit": charger.unit,
        "factor": None,
    }
    assert data["price"] == {"source": "fixed", "value": 0.3}


@each(CHARGERS)
@pytest.mark.parametrize("gone", ["disabled", "missing"])
async def test_without_its_first_counter_the_charger_takes_the_other(
    hass: HomeAssistant, charger: Charger, gone: str
) -> None:
    device = charger.add(hass, **{gone: (charger.counter,)})
    entry = await add_hub(hass)

    result = await pick(hass, entry, device.device.id)
    assert fields(result) == ["price", "price_entity"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"]["entity_id"] == device[charger.fallback]


@each(CHARGERS)
async def test_a_charger_without_energy_counters_asks_for_a_meter(
    hass: HomeAssistant, charger: Charger
) -> None:
    device = charger.add(hass, disabled=(charger.counter,), missing=(charger.fallback,))
    register(hass, ENERGY, "kWh")
    entry = await add_hub(hass)

    result = await pick(hass, entry, device.device.id)
    assert fields(result) == ["meter", "price", "price_entity"]
    result = await configure(hass, result, {"meter": ENERGY, "price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"]["entity_id"] == ENERGY


async def add_charger_device(hass: HomeAssistant, charger: Charger) -> HaDevice:
    """The charger without a car, added by Quick Start."""
    device = charger.add(hass)
    await set_counter(hass, charger, device, 0)
    await set_status(hass, charger, device, "unplugged")
    await quick_start(hass, await add_hub(hass), device.device.id, price=0.3)
    return device


async def set_counter(
    hass: HomeAssistant, charger: Charger, device: HaDevice, kwh: float
) -> None:
    """The counter `kwh` past its reading before the session."""
    scale = 1000 if charger.unit == "Wh" else 1
    hass.states.async_set(
        device[charger.counter],
        str((charger.start + kwh) * scale),
        {"unit_of_measurement": charger.unit},
    )
    await hass.async_block_till_done()


async def set_status(
    hass: HomeAssistant, charger: Charger, device: HaDevice, state: str
) -> None:
    hass.states.async_set(device[charger.status], charger.states[state])
    await hass.async_block_till_done()


@each(SESSIONS)
async def test_a_session_that_waits_and_charges_again_is_one_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], charger: Charger
) -> None:
    device = await add_charger_device(hass, charger)

    await set_status(hass, charger, device, "plugged")
    await set_status(hass, charger, device, "charging")
    await clock.advance(hours=1)
    await set_counter(hass, charger, device, 7)
    await set_status(hass, charger, device, "paused")
    await clock.advance(hours=3)
    await set_status(hass, charger, device, "charging")
    await clock.advance(hours=1)
    await set_counter(hass, charger, device, 10.5)
    await set_status(hass, charger, device, "done")
    await clock.advance(hours=2)
    await set_status(hass, charger, device, "unplugged")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == []
    assert electricity(run)["quantity"] == pytest.approx(10.5)
    assert electricity(run)["amount"] == pytest.approx(3.15)


@each(FAULTS)
async def test_a_charger_fault_flags_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], charger: Charger
) -> None:
    device = await add_charger_device(hass, charger)

    await set_status(hass, charger, device, "charging")
    await clock.advance(hours=1)
    await set_status(hass, charger, device, "fault")
    await clock.advance(minutes=5)
    await set_status(hass, charger, device, "unplugged")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["fault"]


@each(CHARGERS)
async def test_manual_setup_of_the_charger_comes_pre_filled(
    hass: HomeAssistant, charger: Charger
) -> None:
    device = charger.add(hass)
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    result = await configure(hass, result, {"device": "manual"})
    result = await configure(hass, result, {"device_type": "ev_charger"})
    assert result["step_id"] == "device"
    integration = charger.label.split(" · ")[1]
    assert integration in result["description_placeholders"]["integrations"]
    result = await configure(hass, result, {"device": device.device.id})
    result = await configure(hass, result, {"name": "Charger"})

    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
        assert not result.get("errors"), result["errors"]
    assert shown == ["status", "mapping"]
    assert result["step_id"] == "consumption"
    result = await configure(hass, result, {"next_step_id": "energy"})
    assert suggested(result, "entity_id") == device[charger.counter]
    result = await configure(hass, result, accepted(result))
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["status"] == {"entity_id": device[charger.status], "attribute": None}
    assert data["mapping"] == charger.mapping
    assert data["consumption"]["entity_id"] == device[charger.counter]


@each(CHARGERS)
async def test_detect_again_on_the_charger_leaves_electricity_and_price_alone(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, charger: Charger
) -> None:
    device = charger.add(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, device.device.id, price=0.3)
    [subentry] = entry.subentries.values()
    before = dict(subentry.data)
    # An update renamed the Status; the user disabled the counter, which a Detect
    # again that pre-filled the meter would swap for the other one.
    renamed = entity_registry.async_update_entity(
        device[charger.status], new_entity_id="sensor.charger_state"
    ).entity_id
    entity_registry.async_update_entity(
        device[charger.counter], disabled_by=er.RegistryEntryDisabler.USER
    )
    menu = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, menu, {"next_step_id": "detect"})
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    assert shown == ["status", "mapping"]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"] == {"entity_id": renamed, "attribute": None}
    assert data["mapping"] == charger.mapping
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
