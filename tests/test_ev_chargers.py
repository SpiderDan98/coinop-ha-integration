"""EV chargers: a charging session is a Run, and per-Run meters its only Capability."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
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
from .http import HttpClient
from .test_cost_statement import export
from .test_dynamic_price import PRICE_ENTITY, segments, set_price
from .test_measured import electricity
from .test_run_event import record_events
from .test_runs import stored_runs
from .websocket import PanelClient

CHARGER_STATUS = "sensor.wallbox_status"
# Starts each charging session from 0.
SESSION_ENERGY = "sensor.wallbox_session_energy"
CHARGER_MAPPING = {
    "running": ["charging"],
    "paused": ["connected"],
    "finished": ["disconnected"],
}


async def set_charger(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(CHARGER_STATUS, status)
    await hass.async_block_till_done()


async def set_session(hass: HomeAssistant, kwh: float) -> None:
    hass.states.async_set(SESSION_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()


async def add_charger(hass: HomeAssistant, **options: Any) -> ConfigSubentry:
    """An EV charger without a car, in EUR at 0.30 per kWh, on its session energy
    sensor at 0."""
    hass.config.currency = "EUR"
    await set_session(hass, 0)
    await set_charger(hass, "disconnected")
    return await add_basic_device(
        hass,
        await add_hub(hass),
        device_type="ev_charger",
        name="Wallbox",
        status=CHARGER_STATUS,
        mapping=CHARGER_MAPPING,
        meter={"entity_id": SESSION_ENERGY},
        **options,
    )


async def charge(hass: HomeAssistant, clock: Clock, kwh: float) -> None:
    """A two-hour charging session of `kwh`, counted from 0; five minutes after the
    car is unplugged, the session energy sensor drops back to 0."""
    await set_session(hass, 0)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, kwh / 2)
    await clock.advance(hours=1)
    await set_session(hass, kwh)
    await set_charger(hass, "disconnected")
    await set_session(hass, kwh)
    await clock.advance(minutes=5)
    await set_session(hass, 0)


async def test_an_ev_charger_asks_only_for_what_every_device_has(
    hass: HomeAssistant,
) -> None:
    await set_session(hass, 0)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, name="Wallbox", status=CHARGER_STATUS, device_type="ev_charger"
    )
    result = await configure(hass, result, CHARGER_MAPPING)
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power"],
    )
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": SESSION_ENERGY})
    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.30})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [charger] = entry.subentries.values()
    assert charger.data["device_type"] == "ev_charger"
    assert sorted(charger.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "status",
    ]


async def test_reconfiguring_an_ev_charger_offers_only_what_every_device_has(
    hass: HomeAssistant,
) -> None:
    charger = await add_charger(hass)
    [entry] = hass.config_entries.async_entries("coinop")

    result = await start_reconfigure(hass, entry, charger)

    assert result["menu_options"] == ["status", "consumption", "price", "save"]


async def test_a_session_energy_sensor_back_at_zero_between_sessions_is_no_reset(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await add_charger(hass)

    await charge(hass, clock, 11.5)
    await clock.advance(hours=20)
    await charge(hass, clock, 7.2)

    first, second = stored_runs(hass_storage)
    assert electricity(first)["quantity"] == pytest.approx(11.5)
    assert electricity(second)["quantity"] == pytest.approx(7.2)
    assert electricity(second)["amount"] == pytest.approx(2.16)
    assert first["flags"] == second["flags"] == []
    assert (first["outcome"], first["part_count"]) == ("completed", None)


async def test_a_session_sensor_dropping_before_it_reported_the_end_is_no_reset(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await add_charger(hass)
    await set_session(hass, 0)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, 9.0)
    await clock.advance(minutes=1)

    await set_charger(hass, "disconnected")
    await clock.advance(seconds=10)
    await set_session(hass, 0)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(9.0)
    assert run["flags"] == []


async def test_a_car_that_stops_charging_while_plugged_in_stays_in_its_session(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], panel: PanelClient
) -> None:
    await add_charger(hass)
    await set_session(hass, 0)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, 7.0)
    await set_charger(hass, "connected")
    await clock.advance(hours=3)
    await set_session(hass, 7.0)
    await set_charger(hass, "charging")
    await clock.advance(minutes=30)
    await set_session(hass, 10.5)
    await set_charger(hass, "disconnected")
    await set_session(hass, 10.5)

    [run] = stored_runs(hass_storage)
    assert electricity(run)["quantity"] == pytest.approx(10.5)
    [listed] = (await panel.call("coinop/runs/list"))["runs"]
    assert listed["running_seconds"] == 90 * 60


async def test_a_charging_session_is_priced_with_the_price_of_each_hour(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_price(hass, 0.20)
    await add_charger(hass, price=PRICE_ENTITY)
    await set_session(hass, 0)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, 6.0)
    await set_price(hass, 0.40)
    await clock.advance(hours=1)
    await set_session(hass, 10.0)
    await set_charger(hass, "disconnected")
    await set_session(hass, 10.0)

    [run] = stored_runs(hass_storage)
    assert [segment[2:] for segment in segments(run)] == [(6.0, 0.20), (4.0, 0.40)]
    assert electricity(run)["amount"] == pytest.approx(2.80)


async def test_the_devices_command_sends_an_ev_chargers_one_capability(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    charger = await add_charger(hass)

    [device] = (await panel.call("coinop/devices/list"))["devices"]

    assert (device["type"], device["capabilities"]) == (
        "ev_charger",
        ["per_run_meters"],
    )
    assert sorted(device["ha_settings"]) == [
        "consumption",
        "mapping",
        "price",
        "printer_device_id",
        "status",
    ]
    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=charger.subentry_id,
        settings={"doses": [{"id": "dose-cable", "material_id": "cable"}]},
    )
    assert error["code"] == "not_allowed"


async def test_an_ev_charger_has_no_water_sensors_and_its_ended_event_no_program(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await add_charger(hass)
    fired = record_events(hass, "event.wallbox_run")

    await charge(hass, clock, 11.5)

    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.wallbox_run",
        "sensor.wallbox_current_run_cost",
        "sensor.wallbox_electricity_cost",
        "sensor.wallbox_energy_in_runs",
        "sensor.wallbox_flagged_runs",
        "sensor.wallbox_last_run_cost",
        "sensor.wallbox_material_cost",
        "sensor.wallbox_other_cost",
        "sensor.wallbox_running_time",
        "sensor.wallbox_runs",
        "sensor.wallbox_total_cost",
    ]
    [_, ended] = fired
    assert (ended["event_type"], ended["outcome"]) == ("ended", "completed")
    assert ended["energy_kwh"] == pytest.approx(11.5)
    assert ended["total_cost"] == pytest.approx(3.45)
    assert {
        "program",
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)


async def test_charging_sessions_take_the_tags_and_templates_for_new_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    charger = await add_charger(hass)
    template = await panel.call(
        "coinop/templates/create",
        template={"label": "Charger wear", "unit_price": 0.5, "basis": "entered"},
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=charger.subentry_id,
        settings={
            "tags_for_new_runs": ["Company car"],
            "automatic_templates": [template["template"]["id"]],
        },
    )

    await charge(hass, clock, 11.5)

    [run] = stored_runs(hass_storage)
    assert run["tags"] == ["Company car"]
    assert [(i["kind"], i["label"]) for i in run["line_items"]] == [
        ("electricity", None),
        ("other", "Charger wear"),
    ]
    retagged = await panel.call(
        "coinop/runs/update", run_id=run["id"], tags=["Guest car"]
    )
    assert retagged["run"]["tags"] == ["Guest car"]


async def test_a_cost_statement_lists_a_charging_session_without_part_count(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    await add_charger(hass)
    await charge(hass, clock, 11.5)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], name="Company car")

    detailed = await export(panel, browser, run_ids=[run["id"]])
    compact = await export(panel, browser, run_ids=[run["id"]], detail="compact")

    assert "Wallbox · Jan 15, 2026 · Running time 2 h 0 min" in detailed.lines
    assert "Electricity 11.5 kWh × €0.30 €3.45" in detailed.lines  # noqa: RUF001
    assert compact.lines[4:6] == [
        "Run Device Start Total",
        "Company car Wallbox Jan 15, 2026 €3.45",
    ]
    for pages in (detailed.pages, compact.pages):
        text = "".join(pages).lower()
        assert not any(word in text for word in ("part", "program", "water"))
