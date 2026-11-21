"""Robotic mowers: the Device Type without any Capability."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    add_basic_device,
    add_hub,
    configure,
    start_reconfigure,
    walk_to_mapping,
)
from .test_device_flow import fields
from .test_lifecycle import at
from .test_manual_runs import create
from .test_measured import electricity
from .test_run_event import record_events
from .test_runs import stored_runs
from .websocket import PanelClient

MOWER_STATUS = "sensor.mower_status"
# The plug of the mower's charging station.
STATION_ENERGY = "sensor.mower_station_energy"
STATION_POWER = "sensor.mower_station_power"
# Charging is Paused, so what the station draws after mowing lands in the Run.
MOWER_MAPPING = {
    "running": ["mowing", "returning"],
    "paused": ["charging"],
    "ended": ["parked"],
}


async def set_mower(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(MOWER_STATUS, status)
    await hass.async_block_till_done()


async def set_station(hass: HomeAssistant, kwh: float) -> None:
    hass.states.async_set(STATION_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()


async def add_mower(
    hass: HomeAssistant, *, meter: dict[str, Any] | None = None, **options: Any
) -> ConfigSubentry:
    """A robotic mower, parked, in EUR at 0.30 per kWh, on its charging station's
    energy meter at 50 kWh unless `options` pick another `source` with its `meter`."""
    hass.config.currency = "EUR"
    await set_station(hass, 50)
    await set_mower(hass, "parked")
    return await add_basic_device(
        hass,
        await add_hub(hass),
        device_type="robotic_mower",
        name="Mower",
        status=MOWER_STATUS,
        mapping=MOWER_MAPPING,
        meter=meter or {"entity_id": STATION_ENERGY},
        **options,
    )


async def test_a_robotic_mower_asks_only_for_what_every_device_has(
    hass: HomeAssistant,
) -> None:
    await set_station(hass, 50)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, name="Mower", status=MOWER_STATUS, device_type="robotic_mower"
    )
    result = await configure(hass, result, MOWER_MAPPING)
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power"],
    )
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": STATION_ENERGY})
    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.30})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [mower] = entry.subentries.values()
    assert mower.data["device_type"] == "robotic_mower"
    assert sorted(mower.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "status",
    ]


async def test_a_robotic_mowers_power_sensor_has_no_average_power_for_gaps(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass, entry, name="Mower", status=MOWER_STATUS, device_type="robotic_mower"
    )
    result = await configure(hass, result, MOWER_MAPPING)

    result = await configure(hass, result, {"next_step_id": "power"})

    assert fields(result) == ["entity_id", "attribute"]


async def test_reconfiguring_a_robotic_mower_offers_only_what_every_device_has(
    hass: HomeAssistant,
) -> None:
    mower = await add_mower(hass)
    [entry] = hass.config_entries.async_entries("coinop")

    result = await start_reconfigure(hass, entry, mower)

    assert result["menu_options"] == ["status", "consumption", "price", "save"]


async def mow(hass: HomeAssistant, clock: Clock, *, kwh: float = 0.25) -> None:
    """An hour of mowing, five minutes back to the station and 55 minutes of
    charging, which the station's meter counts as `kwh`; then the mower is parked."""
    station = hass.states.get(STATION_ENERGY)
    assert station is not None
    start = float(station.state)
    await set_station(hass, start)
    await set_mower(hass, "mowing")
    await clock.advance(minutes=60)
    await set_mower(hass, "returning")
    await clock.advance(minutes=5)
    await set_station(hass, start)
    await set_mower(hass, "charging")
    await clock.advance(minutes=55)
    await set_station(hass, start + kwh)
    await set_mower(hass, "parked")
    await set_station(hass, start + kwh)


async def test_charging_as_paused_puts_its_electricity_in_the_run_but_not_its_time(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await add_mower(hass)

    await mow(hass, clock)

    [run] = stored_runs(hass_storage)
    assert run["pauses"] == [{"start": at(minutes=65), "end": at(minutes=120)}]
    assert (run.get("program"), run["part_count"], run["flags"]) == (None, None, [])
    [item] = run["line_items"]
    assert (item["kind"], item["method"]) == ("electricity", "measured")
    assert item["quantity"] == pytest.approx(0.25)
    assert item["amount"] == pytest.approx(0.075)
    [listed] = (await panel.call("coinop/runs/list"))["runs"]
    assert listed["running_seconds"] == 65 * 60


async def test_a_mower_leaving_again_after_charging_continues_its_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await add_mower(hass)
    await set_mower(hass, "mowing")
    await clock.advance(minutes=60)
    await set_mower(hass, "charging")
    await clock.advance(minutes=50)
    await set_station(hass, 50.2)

    # While it charges, the open Run is paused: its running time stands still.
    [charging] = (await panel.call("coinop/runs/list"))["runs"]
    assert (charging["ended"], charging["running_seconds"]) == (None, 60 * 60)
    await set_mower(hass, "mowing")
    await clock.advance(minutes=30)
    await set_mower(hass, "charging")
    await clock.advance(minutes=40)
    await set_station(hass, 50.3)
    await set_mower(hass, "parked")
    await set_station(hass, 50.3)

    [run] = stored_runs(hass_storage)
    assert len(run["pauses"]) == 2
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    [listed] = (await panel.call("coinop/runs/list"))["runs"]
    assert listed["running_seconds"] == 90 * 60


async def test_a_gap_in_a_mowers_power_sensor_holds_the_last_power(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    async def set_power(watts: float | str) -> None:
        hass.states.async_set(STATION_POWER, str(watts), {"unit_of_measurement": "W"})
        await hass.async_block_till_done()

    await set_power(0)
    await add_mower(hass, source="power", meter={"entity_id": STATION_POWER})
    await set_mower(hass, "mowing")
    await clock.advance(minutes=60)
    await set_power(100)
    await set_mower(hass, "charging")
    await clock.advance(minutes=10)
    await set_power(STATE_UNAVAILABLE)
    await clock.advance(minutes=20)
    await set_power(40)
    await clock.advance(minutes=30)
    await set_mower(hass, "parked")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(
        (100 * 10 + 100 * 20 + 40 * 30) / 60_000
    )
    assert run["flags"] == ["consumption_gap"]


async def test_the_devices_command_sends_no_capability_for_a_robotic_mower(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    mower = await add_mower(hass)

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["capabilities"]) == ("robotic_mower", [])
    assert device["ha_settings"] == {
        "printer_device_id": None,
        "status": {"entity_id": MOWER_STATUS, "attribute": None},
        "mapping": MOWER_MAPPING
        | {"finished": [], "cancelled": [], "fault": [], "ignored": []},
        "consumption": {
            "source": "energy",
            "entity_id": STATION_ENERGY,
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.3},
    }
    assert device["known_programs"] == []
    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=mower.subentry_id,
        settings={"doses": [{"id": "dose-oil", "material_id": "oil"}]},
    )
    assert error["code"] == "not_allowed"


async def test_a_robotic_mower_has_no_water_sensors_and_its_ended_event_no_program(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await add_mower(hass)
    fired = record_events(hass, "event.mower_run")

    await mow(hass, clock)

    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.mower_run",
        "sensor.mower_current_run_cost",
        "sensor.mower_electricity_cost",
        "sensor.mower_energy_in_runs",
        "sensor.mower_flagged_runs",
        "sensor.mower_last_run_cost",
        "sensor.mower_material_cost",
        "sensor.mower_other_cost",
        "sensor.mower_running_time",
        "sensor.mower_runs",
        "sensor.mower_total_cost",
    ]
    [_, ended] = fired
    assert (ended["event_type"], ended["outcome"]) == ("ended", "unknown")
    assert ended["energy_kwh"] == pytest.approx(0.25)
    assert ended["running_hours"] == pytest.approx(65 / 60)
    assert {
        "program",
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)
    last = hass.states.get("sensor.mower_last_run_cost")
    assert last is not None
    assert {"program", "part_count", "cost_per_part"}.isdisjoint(last.attributes)


async def test_tags_and_automatic_templates_apply_to_mowing_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    mower = await add_mower(hass)
    template = await panel.call(
        "coinop/templates/create",
        template={"label": "Blade wear", "unit_price": 0.1, "basis": "running_hours"},
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=mower.subentry_id,
        settings={
            "tags_for_new_runs": ["Garden"],
            "automatic_templates": [template["template"]["id"]],
        },
    )

    await mow(hass, clock)

    [run] = stored_runs(hass_storage)
    assert run["tags"] == ["Garden"]
    assert [(i["kind"], i["label"], i["quantity"]) for i in run["line_items"]] == [
        ("electricity", None, pytest.approx(0.25)),
        ("other", "Blade wear", pytest.approx(65 / 60)),
    ]


async def test_a_manual_mowing_run_has_no_program_and_its_electricity_is_entered(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    mower = await add_mower(hass)
    await clock.advance(hours=5)

    run = await create(panel, mower.subentry_id, name="Front lawn")

    assert (run["program"], run["part_count"]) == (None, None)
    [item] = run["line_items"]
    assert (item["kind"], item["method"], item["quantity"]) == (
        "electricity",
        "entered",
        None,
    )
    error = await panel.error(
        "coinop/runs/create",
        device_id=mower.subentry_id,
        started=at(hours=0),
        ended=at(hours=2),
        outcome="completed",
        program="Edge cut",
    )
    assert error["code"] == "not_allowed"
