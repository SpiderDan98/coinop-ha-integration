"""Integration Profiles for EV chargers: evcc and OCPP."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .chargers import add_charge_point, add_evcc_site
from .clock import Clock
from .devices import add_hub, configure
from .registry import HaDevice
from .test_device_flow import fields
from .test_integration_profiles import accepted
from .test_measured import electricity
from .test_quick_start import offered, open_add_device, pick, quick_start
from .test_runs import stored_runs

EVCC_MAPPING = {
    "running": ["on"],
    "paused": [],
    "finished": ["off"],
    "cancelled": [],
    "ended": [],
    "fault": [],
    "ignored": [],
}
OCPP_MAPPING = {
    "running": ["Charging"],
    "paused": ["Preparing", "SuspendedEV", "SuspendedEVSE", "Finishing"],
    "finished": ["Available"],
    "cancelled": [],
    "ended": [],
    "fault": ["Faulted"],
    "ignored": ["Unavailable", "Reserved"],
}


async def chargers_offered(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """The labels of the HA devices Quick Start offers, by device id."""
    return {
        option["value"]: option["label"]
        for option in offered(await open_add_device(hass, entry))
        if option["value"] != "manual"
    }


async def test_quick_start_adds_an_evcc_site_with_one_loadpoint(
    hass: HomeAssistant,
) -> None:
    [site] = add_evcc_site(hass)
    entry = await add_hub(hass)

    assert await chargers_offered(hass, entry) == {
        site.device.id: "evcc ☀️🚘 Solar Charging [evcc] · evcc"
    }
    result = await pick(hass, entry, site.device.id)
    assert fields(result) == ["price", "price_entity"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["device_type"] == "ev_charger"
    assert data["status"] == {"entity_id": site["charging"], "attribute": None}
    assert data["mapping"] == EVCC_MAPPING
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": site["charged_energy"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert data["price"] == {"source": "fixed", "value": 0.3}


async def test_quick_start_offers_each_loadpoint_of_an_evcc_site_with_several(
    hass: HomeAssistant,
) -> None:
    garage, carport = add_evcc_site(hass, ("garage", "carport"))
    entry = await add_hub(hass)

    assert await chargers_offered(hass, entry) == {
        garage.device.id: "evcc - Loadpoint Garage [evcc] · evcc",
        carport.device.id: "evcc - Loadpoint Carport [evcc] · evcc",
    }
    data = await quick_start(hass, entry, carport.device.id, price=0.3)
    assert data["status"] == {"entity_id": carport["charging"], "attribute": None}
    assert data["consumption"]["entity_id"] == carport["charged_energy"]


@pytest.mark.parametrize(
    "session", [{"disabled": ("charged_energy",)}, {"missing": ("charged_energy",)}]
)
async def test_without_its_session_counter_an_evcc_loadpoint_takes_the_chargers_meter(
    hass: HomeAssistant, session: dict[str, Any]
) -> None:
    [site] = add_evcc_site(hass, **session)
    entry = await add_hub(hass)

    result = await pick(hass, entry, site.device.id)
    assert fields(result) == ["price", "price_entity"]
    data = await quick_start(hass, entry, site.device.id, price=0.3)
    assert data["consumption"]["entity_id"] == site["charge_total_import"]


async def add_evcc_loadpoint(hass: HomeAssistant) -> HaDevice:
    """An evcc loadpoint without a car, added by Quick Start, its session counter at
    the last session's 12 kWh."""
    [site] = add_evcc_site(hass)
    await set_state(hass, site["charged_energy"], "12", unit="kWh")
    await set_state(hass, site["charging"], "off")
    await quick_start(hass, await add_hub(hass), site.device.id, price=0.3)
    return site


async def set_state(
    hass: HomeAssistant, entity_id: str, state: str, *, unit: str | None = None
) -> None:
    hass.states.async_set(
        entity_id, state, {"unit_of_measurement": unit} if unit else {}
    )
    await hass.async_block_till_done()


async def test_an_evcc_charge_is_a_run_from_on_to_off(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    site = await add_evcc_loadpoint(hass)

    # evcc resets its session counter when the car is plugged in.
    await set_state(hass, site["charged_energy"], "0", unit="kWh")
    await set_state(hass, site["charging"], "on")
    await clock.advance(hours=2)
    await set_state(hass, site["charged_energy"], "14.5", unit="kWh")
    await set_state(hass, site["charging"], "off")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == []
    assert electricity(run)["quantity"] == pytest.approx(14.5)
    assert electricity(run)["amount"] == pytest.approx(4.35)


async def test_charging_that_evcc_stops_and_starts_again_is_two_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    site = await add_evcc_loadpoint(hass)

    await set_state(hass, site["charged_energy"], "0", unit="kWh")
    await set_state(hass, site["charging"], "on")
    await clock.advance(hours=1)
    await set_state(hass, site["charged_energy"], "5", unit="kWh")
    # The solar surplus is gone for an hour; the car stays plugged in.
    await set_state(hass, site["charging"], "off")
    await clock.advance(hours=1)
    # evcc reports its counter at every poll, unchanged or not.
    await set_state(hass, site["charged_energy"], "5", unit="kWh")
    await set_state(hass, site["charging"], "on")
    await clock.advance(hours=1)
    await set_state(hass, site["charged_energy"], "8", unit="kWh")
    await set_state(hass, site["charging"], "off")
    await clock.advance(minutes=10)

    runs = stored_runs(hass_storage)
    assert [run["outcome"] for run in runs] == ["completed", "completed"]
    assert [electricity(run)["quantity"] for run in runs] == pytest.approx([5, 3])


async def test_manual_setup_of_an_evcc_loadpoint_comes_pre_filled(
    hass: HomeAssistant,
) -> None:
    [site] = add_evcc_site(hass)
    entry = await add_hub(hass)

    data = await walk_manual_setup(hass, entry, site)

    assert data["status"] == {"entity_id": site["charging"], "attribute": None}
    assert data["mapping"] == EVCC_MAPPING
    assert data["consumption"]["entity_id"] == site["charged_energy"]


async def walk_manual_setup(
    hass: HomeAssistant, entry: ConfigEntry, charger: HaDevice
) -> dict[str, Any]:
    """Add the HA device by hand as an EV charger, accepting every pre-filled step;
    returns the new Device's data."""
    result = await open_add_device(hass, entry)
    result = await configure(hass, result, {"device": "manual"})
    result = await configure(hass, result, {"device_type": "ev_charger"})
    result = await configure(hass, result, {"device": charger.device.id})
    result = await configure(hass, result, {"name": "Charger"})
    shown = []
    while result["type"] is FlowResultType.FORM and result["step_id"] != "consumption":
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
        assert not result.get("errors"), result["errors"]
    assert shown == ["status", "mapping"]
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, accepted(result))
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return dict(list(entry.subentries.values())[-1].data)


async def test_quick_start_adds_an_ocpp_charge_point_with_its_meter(
    hass: HomeAssistant,
) -> None:
    [charger] = add_charge_point(hass)
    entry = await add_hub(hass)

    assert await chargers_offered(hass, entry) == {charger.device.id: "charger · OCPP"}
    result = await pick(hass, entry, charger.device.id)
    assert fields(result) == ["price", "price_entity"]
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["device_type"] == "ev_charger"
    assert data["status"] == {
        "entity_id": charger["status_connector"],
        "attribute": None,
    }
    assert data["mapping"] == OCPP_MAPPING
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": charger["energy_active_import_register"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert data["price"] == {"source": "fixed", "value": 0.3}


async def test_quick_start_offers_each_connector_of_an_ocpp_charge_point_with_several(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    _, first, second = add_charge_point(hass, connectors=2)
    # A lookup across both connectors would pair the second one's Status with the
    # first one's meter.
    entity_registry.async_update_entity(
        second["energy_active_import_register"],
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    entry = await add_hub(hass)

    assert await chargers_offered(hass, entry) == {
        first.device.id: "charger Connector 1 · OCPP",
        second.device.id: "charger Connector 2 · OCPP",
    }
    data = await quick_start(hass, entry, second.device.id, price=0.3)
    assert data["status"] == {
        "entity_id": second["status_connector"],
        "attribute": None,
    }
    assert data["consumption"]["entity_id"] == second["energy_session"]


@pytest.mark.parametrize(
    "meter",
    [
        {"disabled": ("energy_active_import_register",)},
        {"missing": ("energy_active_import_register",)},
    ],
)
async def test_without_its_meter_an_ocpp_charge_point_takes_its_session_counter(
    hass: HomeAssistant, meter: dict[str, Any]
) -> None:
    [charger] = add_charge_point(hass, **meter)
    entry = await add_hub(hass)

    result = await pick(hass, entry, charger.device.id)
    assert fields(result) == ["price", "price_entity"]
    data = await quick_start(hass, entry, charger.device.id, price=0.3)
    assert data["consumption"]["entity_id"] == charger["energy_session"]


async def add_ocpp_charger(hass: HomeAssistant) -> HaDevice:
    """An OCPP charge point without a car, added by Quick Start, its meter at
    3000 kWh."""
    [charger] = add_charge_point(hass)
    await set_state(hass, charger["energy_active_import_register"], "3000", unit="kWh")
    await set_state(hass, charger["status_connector"], "Available")
    await quick_start(hass, await add_hub(hass), charger.device.id, price=0.3)
    return charger


async def test_an_ocpp_session_that_is_suspended_and_charges_again_is_one_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    charger = await add_ocpp_charger(hass)
    meter = charger["energy_active_import_register"]
    status = charger["status_connector"]

    await set_state(hass, status, "Preparing")
    await set_state(hass, status, "Charging")
    await clock.advance(hours=1)
    await set_state(hass, meter, "3006", unit="kWh")
    # The charger waits for the cheap hours, then the car stops at its limit.
    await set_state(hass, status, "SuspendedEVSE")
    await clock.advance(hours=3)
    await set_state(hass, status, "Charging")
    await clock.advance(hours=1)
    await set_state(hass, meter, "3010", unit="kWh")
    await set_state(hass, status, "SuspendedEV")
    await clock.advance(hours=1)
    await set_state(hass, status, "Finishing")
    await set_state(hass, status, "Available")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == []
    assert electricity(run)["quantity"] == pytest.approx(10)
    assert electricity(run)["amount"] == pytest.approx(3)


async def test_a_faulted_connector_flags_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    charger = await add_ocpp_charger(hass)
    status = charger["status_connector"]

    await set_state(hass, status, "Charging")
    await clock.advance(hours=1)
    await set_state(hass, status, "Faulted")
    await clock.advance(minutes=5)
    await set_state(hass, status, "Available")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["fault"]


async def test_manual_setup_of_an_ocpp_connector_comes_pre_filled(
    hass: HomeAssistant,
) -> None:
    _, first, _ = add_charge_point(hass, connectors=2)
    entry = await add_hub(hass)

    data = await walk_manual_setup(hass, entry, first)

    assert data["status"] == {
        "entity_id": first["status_connector"],
        "attribute": None,
    }
    assert data["mapping"] == OCPP_MAPPING
    assert data["consumption"]["entity_id"] == first["energy_active_import_register"]
