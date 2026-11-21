"""Water on an Other Device: the choice "Water" brings the water source and price, a
Water Line Item, the water sensors and the litres in the `ended` event."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    OTHER_MAPPING,
    add_hub,
    add_other_device,
    basic_entities,
    coinop_entities,
    configure,
    other_input,
    start_reconfigure,
    walk_to_mapping,
)
from .test_device_flow import fields
from .test_other_devices import choose_other
from .test_run_event import record_events
from .test_runs import stored_runs, value
from .test_water import water
from .websocket import PanelClient

VALVE_STATUS = "sensor.garden_valve_status"
VALVE_WATER = "sensor.garden_valve_water"


async def set_valve(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(VALVE_STATUS, status)
    await hass.async_block_till_done()


async def set_valve_water(hass: HomeAssistant, litres: float | str) -> None:
    hass.states.async_set(VALVE_WATER, str(litres), {"unit_of_measurement": "L"})
    await hass.async_block_till_done()


async def add_irrigation(
    hass: HomeAssistant, entry: ConfigEntry | None = None, **options: Any
) -> ConfigSubentry:
    """A battery-driven garden valve, off, in EUR: an Other Device with the Type Name
    "Irrigation" that has water, on its water meter `VALVE_WATER` at 4.00 per m³ and
    with the electricity source none, unless `options` say otherwise. Set the meter
    first."""
    hass.config.currency = "EUR"
    await set_valve(hass, "off")
    valve: dict[str, Any] = {
        "type_name": "Irrigation",
        "name": "Garden valve",
        "status": VALVE_STATUS,
        "has": ["water"],
        "source": "none",
        "water": "meter",
        "water_meter": {"entity_id": VALVE_WATER},
    }
    return await add_other_device(hass, entry or await add_hub(hass), **valve | options)


async def test_water_adds_the_water_source_and_its_price_to_add_device_and_reconfigure(
    hass: HomeAssistant,
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)
    assert "water" in fields(result)
    steps = []
    for user_input in (
        other_input("Irrigation", ["water"]),
        {},
        {"name": "Garden valve"},
        {"entity_id": VALVE_STATUS},
        OTHER_MAPPING,
        {"next_step_id": "none"},
        {"next_step_id": "water_meter"},
        {"entity_id": VALVE_WATER},
        {"next_step_id": "water_fixed_price"},
        {"price": 4.0},
    ):
        result = await configure(hass, result, user_input)
        steps.append(result.get("step_id"))

    assert steps == [
        "device_without_profile",
        "name",
        "status",
        "mapping",
        "consumption",
        "water",
        "water_meter",
        "water_price",
        "water_fixed_price",
        None,
    ]
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [valve] = entry.subentries.values()
    result = await start_reconfigure(hass, entry, valve)
    assert result["menu_options"] == [
        "other",
        "status",
        "consumption",
        "water",
        "water_price",
        "save",
    ]


async def test_water_comes_from_a_meter_a_flow_sensor_or_nowhere_never_per_program(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass,
        entry,
        name="Garden valve",
        status=VALVE_STATUS,
        device_type="other",
        other=other_input("Irrigation", ["water"]),
    )
    result = await configure(hass, result, OTHER_MAPPING)
    assert result["menu_options"] == ["energy", "power", "estimate", "none"]

    result = await configure(hass, result, {"next_step_id": "none"})

    assert (result["step_id"], result["menu_options"]) == (
        "water",
        ["water_meter", "water_flow", "water_none"],
    )


async def test_the_water_source_none_skips_the_water_price(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    valve = await add_irrigation(hass, entry, water="none")

    assert valve.data["water"] == {"source": "none"}
    assert "water_price" not in valve.data
    result = await start_reconfigure(hass, entry, valve)
    assert result["menu_options"] == ["other", "status", "consumption", "water", "save"]


async def test_a_water_source_picked_in_reconfigure_walks_on_to_the_water_price(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    await set_valve_water(hass, 1000)
    entry = await add_hub(hass)
    valve = await add_irrigation(hass, entry, water="none")
    result = await start_reconfigure(hass, entry, valve)
    result = await configure(hass, result, {"next_step_id": "water"})
    assert result["menu_options"] == ["water_meter", "water_flow", "water_none"]

    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": VALVE_WATER})
    assert result["step_id"] == "water_price"
    result = await configure(hass, result, {"next_step_id": "water_fixed_price"})
    result = await configure(hass, result, {"price": 2.5})

    assert result["menu_options"] == [
        "other",
        "status",
        "consumption",
        "water",
        "water_price",
        "save",
    ]
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()
    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["ha_settings"]["water"]["source"] == "meter"
    assert device["ha_settings"]["water_price"] == {"source": "fixed", "value": 2.5}


async def irrigate(
    hass: HomeAssistant, clock: Clock, *, start: float, litres: float
) -> None:
    """A watering of half an hour that takes `litres` from the water meter at `start`,
    which reports once more after the valve closed."""
    await set_valve_water(hass, start)
    await set_valve(hass, "on")
    await clock.advance(minutes=30)
    await set_valve_water(hass, start + litres)
    await set_valve(hass, "off")
    await set_valve_water(hass, start + litres)
    # Older Home Assistant needs a second pass for the Run event's listeners.
    await hass.async_block_till_done()


async def test_a_run_with_the_electricity_source_none_costs_only_its_water(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    await add_irrigation(hass)

    await irrigate(hass, clock, start=1000, litres=120)

    [run] = stored_runs(hass_storage)
    assert (run["device_name"], run["finalised"], run["flags"]) == (
        "Garden valve",
        True,
        [],
    )
    [item] = run["line_items"]
    assert (item["kind"], item["unit"], item["method"]) == ("water", "L", "measured")
    assert item["quantity"] == pytest.approx(120)
    assert item["amount"] == pytest.approx(0.48)


async def test_water_gaps_and_resets_are_flagged_as_on_any_device_with_water(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_valve_water(hass, 1000)
    await add_irrigation(hass)

    await set_valve(hass, "on")
    await clock.advance(minutes=10)
    await set_valve_water(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=10)
    await set_valve_water(hass, 1020)
    await clock.advance(minutes=10)
    await set_valve_water(hass, 5)
    await clock.advance(minutes=10)
    await set_valve_water(hass, 15)
    await set_valve(hass, "off")
    await set_valve_water(hass, 15)

    [run] = stored_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(20 + 5 + 10)
    assert run["flags"] == ["consumption_gap", "meter_reset"]


@pytest.mark.parametrize(
    ("has", "kinds", "flags"),
    [
        (["water"], ["electricity", "water"], ["consumption_gap"]),
        ([], ["electricity"], []),
    ],
    ids=["water", "nothing picked"],
)
async def test_only_a_device_with_water_gets_a_water_line_item_and_water_flags(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    has: list[str],
    kinds: list[str],
    flags: list[str],
) -> None:
    """Fed the same states, the water meter falling silent among them."""
    await set_valve_water(hass, 1000)
    await add_irrigation(hass, has=has, source="estimate", running_power=10)

    await set_valve(hass, "on")
    await clock.advance(minutes=10)
    await set_valve_water(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=20)
    await set_valve_water(hass, 1090)
    await set_valve(hass, "off")
    await set_valve_water(hass, 1090)

    [run] = stored_runs(hass_storage)
    assert [item["kind"] for item in run["line_items"]] == kinds
    assert run["flags"] == flags


async def test_a_device_with_water_has_the_water_sensors_and_litres_in_its_ended_event(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    await add_irrigation(hass)
    fired = record_events(hass, "event.garden_valve_run")

    await irrigate(hass, clock, start=1000, litres=120)
    await irrigate(hass, clock, start=1120, litres=80)

    assert coinop_entities(entity_registry) == sorted(
        [
            *basic_entities("garden_valve"),
            "sensor.garden_valve_water_cost",
            "sensor.garden_valve_water_in_runs",
        ]
    )
    assert value(hass, "sensor.garden_valve_water_in_runs") == pytest.approx(200)
    assert value(hass, "sensor.garden_valve_water_cost") == pytest.approx(0.80)
    assert value(hass, "sensor.garden_valve_total_cost") == pytest.approx(0.80)
    ended = [event for event in fired if event["event_type"] == "ended"]
    assert [event["water_litres"] for event in ended] == [
        pytest.approx(120),
        pytest.approx(80),
    ]
    assert [event["energy_kwh"] for event in ended] == [0, 0]
    assert {"program", "part_count", "material_grams"}.isdisjoint(ended[0])


async def test_a_device_without_water_has_no_water_sensors_and_no_litres(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await set_valve_water(hass, 1000)
    await add_irrigation(hass, has=[])
    fired = record_events(hass, "event.garden_valve_run")

    await irrigate(hass, clock, start=1000, litres=120)

    assert coinop_entities(entity_registry) == basic_entities("garden_valve")
    [_, ended] = fired
    assert ended["event_type"] == "ended"
    assert "water_litres" not in ended


async def test_the_devices_command_sends_the_water_source_and_price(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    await set_valve_water(hass, 1000)
    await add_irrigation(hass)

    [valve] = (await panel.call("coinop/devices/list"))["devices"]

    assert (valve["type"], valve["type_name"]) == ("other", "Irrigation")
    assert "water" in valve["capabilities"]
    settings = valve["ha_settings"]
    assert settings["consumption"] == {"source": "none"}
    assert "price" not in settings
    assert (settings["water"]["source"], settings["water"]["entity_id"]) == (
        "meter",
        VALVE_WATER,
    )
    assert settings["water_price"] == {"source": "fixed", "value": 4.0}
