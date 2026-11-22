"""Integration Profiles for EV chargers: Tesla Wall Connector, and Detect again on
every EV charger integration."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import ENERGY, add_hub, configure, report_status, start_reconfigure
from .registry import (
    HaDevice,
    add_charge_point,
    add_evcc_site,
    add_wall_connector,
    add_wallbox,
)
from .test_device_flow import fields, suggested
from .test_easee_zaptec_go_e import CHARGERS
from .test_integration_profiles import accepted
from .test_measured import electricity
from .test_quick_start import offered, open_add_device, pick, quick_start, register
from .test_runs import stored_runs

WALL_CONNECTOR_MAPPING = {
    "running": ["charging", "charging_reduced"],
    "paused": [
        "connected",
        "ready",
        "negotiating",
        "waiting_car",
        "charging_finished",
    ],
    "finished": ["not_connected"],
    "cancelled": [],
    "ended": [],
    "fault": ["error"],
    "ignored": ["booting"],
}


async def test_quick_start_adds_a_wall_connector_with_its_lifetime_counter(
    hass: HomeAssistant,
) -> None:
    charger = add_wall_connector(hass)
    entry = await add_hub(hass)

    assert offered(await open_add_device(hass, entry))[0] == {
        "value": charger.device.id,
        "label": "Tesla Wall Connector · Tesla Wall Connector",
    }
    result = await pick(hass, entry, charger.device.id)
    assert fields(result) == ["price", "price_entity", "pick_another_device"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["device_type"] == "ev_charger"
    assert data["status"] == {"entity_id": charger["status"], "attribute": None}
    assert data["mapping"] == WALL_CONNECTOR_MAPPING
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": charger["energy_kWh"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert data["price"] == {"source": "fixed", "value": 0.3}


# Each EV charger integration's fixture and its Status's key.
DETECT_AGAIN = {
    "tesla_wall_connector": (add_wall_connector, "status"),
    "evcc_intg": (lambda hass: add_evcc_site(hass)[0], "charging"),
    "ocpp": (lambda hass: add_charge_point(hass)[0], "status_connector"),
    **{key: (charger.add, charger.status) for key, charger in CHARGERS.items()},
    "wallbox": (add_wallbox, "status_description"),
}


@pytest.mark.parametrize(("add", "status"), DETECT_AGAIN.values(), ids=DETECT_AGAIN)
async def test_detect_again_on_an_ev_charger_leaves_electricity_and_price_alone(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    add: Callable[[HomeAssistant], HaDevice],
    status: str,
) -> None:
    charger = add(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, charger.device.id, price=0.3)
    [subentry] = entry.subentries.values()
    before = dict(subentry.data)
    # An update renamed the Status; the user disabled the pre-filled counter, which a
    # Detect again that pre-filled the meter would swap for another one.
    renamed = entity_registry.async_update_entity(
        charger[status], new_entity_id=f"{charger[status]}_renamed"
    ).entity_id
    entity_registry.async_update_entity(
        before["consumption"]["entity_id"], disabled_by=er.RegistryEntryDisabler.USER
    )
    menu = await start_reconfigure(hass, entry, subentry)
    assert menu["menu_options"] == [
        "status",
        "progress",
        "consumption",
        "price",
        "detect",
        "save",
    ]

    result = await configure(hass, menu, {"next_step_id": "detect"})
    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
    # Only a charger with a target has a progress section to detect.
    targeted = before["progress"]["expected_energy"] is not None
    assert shown == ["status", "mapping", *(["progress"] if targeted else [])]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["status"] == {"entity_id": renamed, "attribute": None}
    assert data["mapping"] == before["mapping"]
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]


@pytest.mark.parametrize(
    "lifetime", [{"disabled": ("energy_kWh",)}, {"missing": ("energy_kWh",)}]
)
async def test_without_its_lifetime_counter_a_wall_connector_takes_its_session_counter(
    hass: HomeAssistant, lifetime: dict[str, Any]
) -> None:
    charger = add_wall_connector(hass, **lifetime)
    entry = await add_hub(hass)

    result = await pick(hass, entry, charger.device.id)
    assert fields(result) == ["price", "price_entity", "pick_another_device"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"]["entity_id"] == charger["session_energy_wh"]


async def test_a_wall_connector_without_energy_counters_asks_for_a_meter(
    hass: HomeAssistant,
) -> None:
    charger = add_wall_connector(
        hass, disabled=("energy_kWh",), missing=("session_energy_wh",)
    )
    register(hass, ENERGY, "kWh")
    entry = await add_hub(hass)

    result = await pick(hass, entry, charger.device.id)
    assert fields(result) == ["meter", "price", "price_entity", "pick_another_device"]
    result = await configure(hass, result, {"meter": ENERGY, "price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"]["entity_id"] == ENERGY


async def add_wall_connector_device(hass: HomeAssistant) -> HaDevice:
    """A Wall Connector without a car, added by Quick Start, its lifetime counter at
    1200 kWh."""
    charger = add_wall_connector(hass)
    await set_counter(hass, charger, 1200)
    hass.states.async_set(charger["status"], "not_connected")
    await quick_start(hass, await add_hub(hass), charger.device.id, price=0.3)
    return charger


async def set_counter(hass: HomeAssistant, charger: HaDevice, kwh: float) -> None:
    hass.states.async_set(
        charger["energy_kWh"], str(kwh), {"unit_of_measurement": "kWh"}
    )
    await hass.async_block_till_done()


async def test_a_session_that_waits_and_charges_again_is_one_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    charger = await add_wall_connector_device(hass)

    await report_status(hass, charger["status"], "connected")
    await report_status(hass, charger["status"], "charging")
    await clock.advance(hours=1)
    await set_counter(hass, charger, 1207)
    # Load management waits for the cheap hours, then charges at reduced current.
    await report_status(hass, charger["status"], "waiting_car")
    await clock.advance(hours=3)
    await report_status(hass, charger["status"], "charging_reduced")
    await clock.advance(hours=1)
    await set_counter(hass, charger, 1210.5)
    await report_status(hass, charger["status"], "charging_finished")
    await clock.advance(hours=2)
    await report_status(hass, charger["status"], "not_connected")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == []
    assert electricity(run)["quantity"] == pytest.approx(10.5)
    assert electricity(run)["amount"] == pytest.approx(3.15)


async def test_a_wall_connector_error_flags_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    charger = await add_wall_connector_device(hass)

    await report_status(hass, charger["status"], "charging")
    await clock.advance(hours=1)
    await report_status(hass, charger["status"], "error")
    await clock.advance(minutes=5)
    await report_status(hass, charger["status"], "not_connected")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["fault"]


async def test_manual_setup_of_a_wall_connector_comes_pre_filled(
    hass: HomeAssistant,
) -> None:
    charger = add_wall_connector(hass)
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    result = await configure(hass, result, {"device": "manual"})
    result = await configure(hass, result, {"device_type": "ev_charger"})
    assert result["step_id"] == "device"
    integrations = result["description_placeholders"]["integrations"]
    assert "Tesla Wall Connector" in integrations.split(", ")
    result = await configure(hass, result, {"device": charger.device.id})
    result = await configure(hass, result, {"name": "Wall Connector"})

    shown = []
    while result["type"] is FlowResultType.FORM:
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
        assert not result.get("errors"), result["errors"]
    assert shown == ["status", "mapping", "progress"]
    assert result["step_id"] == "consumption"
    result = await configure(hass, result, {"next_step_id": "energy"})
    assert suggested(result, "entity_id") == charger["energy_kWh"]
    result = await configure(hass, result, accepted(result))
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["status"] == {"entity_id": charger["status"], "attribute": None}
    assert data["mapping"] == WALL_CONNECTOR_MAPPING
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": charger["energy_kWh"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
