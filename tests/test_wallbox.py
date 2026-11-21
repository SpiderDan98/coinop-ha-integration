"""The Wallbox profile: an EV charger added from Home Assistant's `wallbox` integration."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .chargers import add_wallbox
from .clock import Clock
from .devices import ENERGY, add_hub, configure, start_reconfigure
from .registry import HaDevice
from .test_device_flow import fields, suggested
from .test_integration_profiles import accepted
from .test_measured import electricity
from .test_quick_start import offered, open_add_device, pick, quick_start, register
from .test_runs import stored_runs

MAPPING = {
    "running": ["Charging"],
    "paused": [
        "Discharging",
        "Paused",
        "Scheduled",
        "Waiting for car demand",
        "Waiting",
        "Waiting in queue by Power Sharing",
        "Waiting in queue by Power Boost",
        "Waiting in queue by Eco-Smart",
        "Waiting MID failed",
        "Waiting MID safety margin exceeded",
        "Locked, car connected",
    ],
    "finished": ["Ready", "Locked"],
    "cancelled": [],
    "ended": [],
    "fault": ["Error"],
    "ignored": ["Disconnected", "Updating", "Unknown"],
}


async def test_quick_start_adds_a_wallbox_with_its_session_counter(
    hass: HomeAssistant,
) -> None:
    wallbox = add_wallbox(hass)
    entry = await add_hub(hass)

    assert offered(await open_add_device(hass, entry)) == [
        {"value": wallbox.device.id, "label": "Wallbox Garage · Wallbox"},
        {"value": "manual", "label": "manual"},
    ]
    result = await pick(hass, entry, wallbox.device.id)
    assert fields(result) == ["price", "price_entity"]
    await configure(hass, result, {"price": 0.3})

    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["device_type"] == "ev_charger"
    assert data["status"] == {
        "entity_id": wallbox["status_description"],
        "attribute": None,
    }
    assert data["mapping"] == MAPPING
    assert data["consumption"] == {
        "source": "energy",
        "entity_id": wallbox["added_energy"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert data["price"] == {"source": "fixed", "value": 0.3}


@pytest.mark.parametrize(
    "counter", [{"disabled": ("added_energy",)}, {"missing": ("added_energy",)}]
)
async def test_a_wallbox_without_its_session_counter_asks_for_a_meter(
    hass: HomeAssistant, counter: dict[str, Any]
) -> None:
    wallbox = add_wallbox(hass, **counter)
    register(hass, ENERGY, "kWh")
    entry = await add_hub(hass)

    result = await pick(hass, entry, wallbox.device.id)
    assert fields(result) == ["meter", "price", "price_entity"]
    data = await quick_start(hass, entry, wallbox.device.id, meter=ENERGY, price=0.3)

    assert data["consumption"]["entity_id"] == ENERGY
    assert data["status"]["entity_id"] == wallbox["status_description"]


async def add_wallbox_device(hass: HomeAssistant) -> HaDevice:
    """A Wallbox without a car, its session counter at 0, added by Quick Start."""
    wallbox = add_wallbox(hass)
    await set_energy(hass, wallbox, 0)
    await set_status(hass, wallbox, "Ready")
    await quick_start(hass, await add_hub(hass), wallbox.device.id, price=0.3)
    return wallbox


async def set_energy(hass: HomeAssistant, wallbox: HaDevice, kwh: float) -> None:
    hass.states.async_set(
        wallbox["added_energy"], str(kwh), {"unit_of_measurement": "kWh"}
    )
    await hass.async_block_till_done()


async def set_status(hass: HomeAssistant, wallbox: HaDevice, state: str) -> None:
    hass.states.async_set(wallbox["status_description"], state)
    await hass.async_block_till_done()


async def charge(
    hass: HomeAssistant, clock: Clock, wallbox: HaDevice, *, kwh: float
) -> None:
    """A session that charges, is paused, loses the cloud for a poll and charges again
    until the car is full and unplugged. Its counter starts from 0 when the car is
    plugged in and ends at `kwh`, which it holds until the next session."""
    await set_status(hass, wallbox, "Waiting for car demand")
    await set_energy(hass, wallbox, 0)
    await set_status(hass, wallbox, "Charging")
    await clock.advance(hours=1)
    await set_energy(hass, wallbox, kwh / 2)
    await set_status(hass, wallbox, "Paused")
    await clock.advance(hours=2)
    await set_status(hass, wallbox, "Disconnected")
    await clock.advance(minutes=2)
    await set_status(hass, wallbox, "Charging")
    await clock.advance(hours=1)
    await set_energy(hass, wallbox, kwh)
    await set_status(hass, wallbox, "Waiting for car demand")
    await clock.advance(hours=1)
    await set_status(hass, wallbox, "Ready")
    await clock.advance(minutes=10)


async def test_a_wallbox_session_that_pauses_and_charges_again_is_one_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    wallbox = await add_wallbox_device(hass)

    await charge(hass, clock, wallbox, kwh=10.5)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["flags"] == []
    assert electricity(run)["quantity"] == pytest.approx(10.5)
    assert electricity(run)["amount"] == pytest.approx(3.15)


async def test_the_next_session_counting_from_zero_raises_no_meter_reset_flag(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    wallbox = await add_wallbox_device(hass)
    await charge(hass, clock, wallbox, kwh=10.5)
    await clock.advance(hours=20)
    await charge(hass, clock, wallbox, kwh=4.2)

    first, second = stored_runs(hass_storage)
    assert first["flags"] == second["flags"] == []
    assert electricity(first)["quantity"] == pytest.approx(10.5)
    assert electricity(second)["quantity"] == pytest.approx(4.2)


async def test_a_wallbox_error_flags_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    wallbox = await add_wallbox_device(hass)

    await set_status(hass, wallbox, "Charging")
    await clock.advance(hours=1)
    await set_energy(hass, wallbox, 6)
    await set_status(hass, wallbox, "Error")
    await clock.advance(minutes=5)
    await set_status(hass, wallbox, "Ready")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["fault"]
    assert electricity(run)["quantity"] == pytest.approx(6)


async def test_manual_setup_of_a_wallbox_comes_pre_filled(
    hass: HomeAssistant,
) -> None:
    wallbox = add_wallbox(hass)
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    result = await configure(hass, result, {"device": "manual"})
    result = await configure(hass, result, {"device_type": "ev_charger"})
    assert "Wallbox" in result["description_placeholders"]["integrations"]
    result = await configure(hass, result, {"device": wallbox.device.id})
    result = await configure(hass, result, {"name": "Charger"})

    shown = []
    while result["type"] is FlowResultType.FORM and result["step_id"] != "consumption":
        shown.append(result["step_id"])
        result = await configure(hass, result, accepted(result))
        assert not result.get("errors"), result["errors"]
    assert shown == ["status", "mapping"]
    result = await configure(hass, result, {"next_step_id": "energy"})
    assert suggested(result, "entity_id") == wallbox["added_energy"]
    result = await configure(hass, result, accepted(result))
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    data = subentry.data
    assert data["status"] == {
        "entity_id": wallbox["status_description"],
        "attribute": None,
    }
    assert data["mapping"] == MAPPING
    assert data["consumption"]["entity_id"] == wallbox["added_energy"]


async def test_detect_again_on_a_wallbox_leaves_electricity_and_price_alone(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    wallbox = add_wallbox(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, wallbox.device.id, price=0.3)
    [subentry] = entry.subentries.values()
    before = dict(subentry.data)
    # The user renamed the Status and swapped in a plug's meter of their own.
    renamed = entity_registry.async_update_entity(
        wallbox["status_description"], new_entity_id="sensor.wallbox_state"
    ).entity_id
    entity_registry.async_update_entity(
        wallbox["added_energy"], disabled_by=er.RegistryEntryDisabler.USER
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
    assert data["mapping"] == MAPPING
    assert data["consumption"] == before["consumption"]
    assert data["price"] == before["price"]
