"""Other: the Device Type for what Coin-op ships none for, under a Type Name the user
gives and with what the user picks for it."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    BASIC_DATA,
    OTHER_MAPPING,
    add_basic_device,
    add_hub,
    add_other_device,
    answer_progress,
    basic_entities,
    coinop_entities,
    configure,
    open_device_types,
    open_other,
    other_input,
    price_choice,
    price_input,
    reconfigure,
    report_status,
    run_once,
    start_reconfigure,
    walk_to_mapping,
)
from .registry import add_miele, add_washdata
from .test_device_flow import fields, offered, suggested
from .test_lifecycle import at
from .test_manual_runs import create
from .test_measured import electricity
from .test_quick_start import open_add_device
from .test_run_event import record_events
from .test_runs import stored_runs
from .websocket import PanelClient

KILN_STATUS = "sensor.kiln_status"
PUMP_STATUS = "sensor.pool_pump_status"
# Starts each pump cycle from 0.
CYCLE_ENERGY = "sensor.pool_pump_cycle_energy"


async def set_kiln(hass: HomeAssistant, status: str) -> None:
    await report_status(hass, KILN_STATUS, status)


async def add_kiln(
    hass: HomeAssistant, *, entry: ConfigEntry | None = None, **options: Any
) -> ConfigSubentry:
    """A kiln, off, in EUR at 0.30 per kWh: an Other Device with the Type Name "Kiln"
    that has nothing, estimating its electricity from 2 kW unless `options` say
    otherwise."""
    hass.config.currency = "EUR"
    await set_kiln(hass, "off")
    kiln: dict[str, Any] = {
        "type_name": "Kiln",
        "name": "Kiln",
        "status": KILN_STATUS,
        "running_power": 2000,
    }
    return await add_other_device(hass, entry or await add_hub(hass), **kiln | options)


async def fire(
    hass: HomeAssistant, clock: Clock, kiln: str = KILN_STATUS, *, minutes: float = 90
) -> None:
    """A firing of `minutes`, after which the kiln (by its Status entity) is off
    again."""
    await run_once(hass, clock, kiln, minutes=minutes)


async def set_pump(hass: HomeAssistant, status: str) -> None:
    await report_status(hass, PUMP_STATUS, status)


async def set_cycle(hass: HomeAssistant, kwh: float) -> None:
    hass.states.async_set(CYCLE_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()


async def add_pump(
    hass: HomeAssistant, *, entry: ConfigEntry | None = None, **options: Any
) -> ConfigSubentry:
    """A pool pump, off, in EUR at 0.30 per kWh: an Other Device with the Type Name
    "Pump" on its cycle energy sensor at 0, whose meters count each Run from 0 unless
    `options` say otherwise."""
    hass.config.currency = "EUR"
    await set_cycle(hass, 0)
    await set_pump(hass, "off")
    pool_pump: dict[str, Any] = {
        "type_name": "Pump",
        "name": "Pool pump",
        "status": PUMP_STATUS,
        "has": ["per_run_meters"],
        "source": "energy",
        "meter": {"entity_id": CYCLE_ENERGY},
    }
    return await add_other_device(
        hass, entry or await add_hub(hass), **pool_pump | options
    )


async def pump(hass: HomeAssistant, clock: Clock, kwh: float) -> None:
    """A two-hour pump cycle of `kwh`, counted from 0. The cycle energy sensor drops
    back to 0 ten seconds after the pump stopped, before it reported the end."""
    await set_cycle(hass, 0)
    await set_pump(hass, "on")
    await clock.advance(hours=2)
    await set_cycle(hass, kwh)
    await clock.advance(minutes=1)
    await set_pump(hass, "off")
    await clock.advance(seconds=10)
    await set_cycle(hass, 0)


async def choose_other(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Open Add Device and choose the Device Type Other."""
    result = await open_device_types(hass, entry)
    return await configure(hass, result, {"device_type": "other"})


async def test_other_asks_for_a_type_name_and_what_the_device_has_then_the_basics(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)
    assert result["step_id"] == "other"
    assert fields(result) == [
        "type_name",
        "program",
        "doses",
        "water",
        "job",
        "images",
        "part_count",
        "per_run_meters",
        "change_device_type",
    ]
    steps = []
    for user_input in (
        other_input("Kiln"),
        {},
        {"name": "Kiln"},
        {"entity_id": KILN_STATUS},
        OTHER_MAPPING,
        {},
        {"next_step_id": "estimate"},
        {"running_power": 2000},
        price_choice(0.30),
        price_input(0.30),
    ):
        result = await configure(hass, result, user_input)
        steps.append(result.get("step_id"))

    assert steps == [
        "device_without_profile",
        "name",
        "status",
        "mapping",
        "progress",
        "consumption",
        "estimate",
        "price",
        "fixed_price",
        None,
    ]
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_type_name_is_required_and_stored_trimmed(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await choose_other(hass, entry)

    result = await configure(hass, result, other_input("   "))

    assert (result["step_id"], result["errors"]) == (
        "other",
        {"type_name": "type_name_required"},
    )
    kiln = await add_kiln(hass, entry=entry, type_name="  Kiln ")
    assert kiln.data["type_name"] == "Kiln"


async def test_without_any_type_name_the_other_step_asks_for_one(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await configure(hass, await choose_other(hass, entry), {})

    assert result["errors"] == {"type_name": "type_name_required"}


async def test_the_other_step_leads_back_to_the_device_type_without_a_type_name(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await configure(
        hass, await choose_other(hass, entry), {"change_device_type": True}
    )

    assert result["step_id"] == "user"


async def test_reconfigure_offers_no_change_of_device_type(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)

    result = await open_other(hass, entry, kiln)

    assert result["step_id"] == "other"
    assert "change_device_type" not in fields(result)


async def test_the_type_names_of_other_devices_are_suggested_and_a_new_one_accepted(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await choose_other(hass, entry)
    # With nothing to suggest, the Type Name is a plain text field.
    assert "options" not in result["data_schema"].schema["type_name"].config
    await add_kiln(hass, entry=entry)
    await add_kiln(
        hass, entry=entry, name="Small kiln", status="sensor.small_kiln_status"
    )
    await add_kiln(
        hass, entry=entry, type_name="Pump", name="Pool pump", status=PUMP_STATUS
    )

    result = await choose_other(hass, entry)

    assert offered(result, "type_name") == ["Kiln", "Pump"]
    result = await configure(hass, result, other_input("Soda maker"))
    assert result["step_id"] == "device_without_profile"


async def test_a_device_that_has_nothing_can_estimate_its_electricity(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass,
        entry,
        name="Kiln",
        status=KILN_STATUS,
        device_type="other",
        other=other_input("Kiln"),
    )

    result = await configure(hass, result, OTHER_MAPPING)
    result = await answer_progress(hass, result)

    assert result["menu_options"] == ["energy", "power", "estimate", "none"]
    result = await configure(hass, result, {"next_step_id": "power"})
    assert fields(result) == ["entity_id", "attribute", "running_power"]


async def test_an_other_device_stores_its_type_name_next_to_what_every_device_stores(
    hass: HomeAssistant,
) -> None:
    kiln = await add_kiln(hass)

    assert (kiln.data["device_type"], kiln.data["type_name"]) == ("other", "Kiln")
    assert set(BASIC_DATA) <= set(kiln.data)
    assert {"job", "images", "program", "water", "water_price"}.isdisjoint(kiln.data)


async def test_no_integration_pre_fills_an_other_device(hass: HomeAssistant) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": "manual"}
    )
    assert "other" in offered(result, "device_type")
    result = await configure(hass, result, {"device_type": "other"})
    result = await configure(hass, result, other_input("Kiln"))
    assert result["step_id"] == "device_without_profile"

    result = await configure(hass, result, {"device": washer.device.id})
    assert suggested(result, "name") == "Washing machine"
    result = await configure(hass, result, {"name": "Kiln"})

    assert result["step_id"] == "status"
    assert suggested(result, "entity_id") is None


async def test_reconfiguring_an_other_device_offers_its_sections_and_no_detect_again(
    hass: HomeAssistant,
) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry, device=washer.device.id)

    result = await start_reconfigure(hass, entry, kiln)

    assert result["menu_options"] == [
        "other",
        "status",
        "progress",
        "consumption",
        "price",
        "save",
    ]


async def test_reconfiguring_a_section_leaves_the_type_name_and_what_it_has_alone(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    pump = await add_pump(hass, entry=entry)
    result = await start_reconfigure(hass, entry, pump)
    result = await configure(hass, result, {"next_step_id": "consumption"})
    assert result["menu_options"] == ["energy", "power", "estimate", "none"]

    await reconfigure(
        hass,
        entry,
        pump,
        {"next_step_id": "consumption"},
        {"next_step_id": "estimate"},
        {"running_power": 750},
    )

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert (device["type"], device["type_name"]) == ("other", "Pump")
    assert device["capabilities"] == ["average_power", "per_run_meters"]
    assert device["ha_settings"]["consumption"] == {
        "source": "estimate",
        "running_power": 750,
        "paused_power": None,
    }


async def test_quick_start_never_offers_a_device_as_other(hass: HomeAssistant) -> None:
    plug = add_washdata(hass, "generic", name="Plug")
    entry = await add_hub(hass)

    result = await configure(
        hass, await open_add_device(hass, entry), {"device": plug.device.id}
    )

    assert result["step_id"] == "quick_start_device_type"
    assert "other" not in offered(result, "device_type")


async def test_a_run_of_an_other_device_gets_an_electricity_line_item(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await add_kiln(hass)

    await fire(hass, clock)

    [run] = stored_runs(hass_storage)
    assert (run["device_name"], run["outcome"], run["flags"]) == ("Kiln", "unknown", [])
    assert (run.get("program"), run["part_count"]) == (None, None)
    [item] = run["line_items"]
    assert (item["kind"], item["method"]) == ("electricity", "estimated")
    assert item["quantity"] == pytest.approx(3.0)
    assert item["amount"] == pytest.approx(0.90)


async def test_tags_and_automatic_templates_apply_to_an_other_devices_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    kiln = await add_kiln(hass)
    template = await panel.call(
        "coinop/templates/create",
        template={"label": "Element wear", "unit_price": 0.4, "basis": "running_hours"},
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=kiln.subentry_id,
        settings={
            "tags_for_new_runs": ["Pottery"],
            "automatic_templates": [template["template"]["id"]],
        },
    )

    await fire(hass, clock)

    [run] = stored_runs(hass_storage)
    assert run["tags"] == ["Pottery"]
    assert [(i["kind"], i["label"], i["quantity"]) for i in run["line_items"]] == [
        ("electricity", None, pytest.approx(3.0)),
        ("other", "Element wear", pytest.approx(1.5)),
    ]


async def test_a_manual_run_of_an_other_device_is_estimated_and_has_no_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    kiln = await add_kiln(hass)
    await clock.advance(hours=5)

    run = await create(panel, kiln.subentry_id, name="Bisque firing")

    assert (run["device_name"], run["program"], run["part_count"]) == (
        "Kiln",
        None,
        None,
    )
    [item] = run["line_items"]
    assert (item["kind"], item["method"]) == ("electricity", "estimated")
    assert item["quantity"] == pytest.approx(4.0)
    error = await panel.error(
        "coinop/runs/create",
        device_id=kiln.subentry_id,
        started=at(hours=0),
        ended=at(hours=2),
        outcome="completed",
        program="Glaze",
    )
    assert error["code"] == "not_allowed"


@pytest.mark.parametrize(
    ("has", "flags"),
    [(["per_run_meters"], []), ([], ["meter_reset"])],
    ids=["meters count each Run from 0", "nothing picked"],
)
async def test_a_meter_back_at_zero_after_a_run_is_a_reset_unless_it_counts_each_run(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    has: list[str],
    flags: list[str],
) -> None:
    await add_pump(hass, has=has)

    await pump(hass, clock, 1.6)
    await clock.advance(hours=20)
    await pump(hass, clock, 2.4)

    first, second = stored_runs(hass_storage)
    assert electricity(first)["quantity"] == pytest.approx(1.6)
    assert electricity(second)["quantity"] == pytest.approx(2.4)
    assert electricity(second)["amount"] == pytest.approx(0.72)
    assert (first["flags"], second["flags"]) == (flags, flags)


async def test_the_devices_command_sends_an_other_devices_type_name_and_what_it_has(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_kiln(hass, entry=entry)
    await add_pump(hass, entry=entry)
    await add_basic_device(
        hass,
        entry,
        device_type="robotic_mower",
        name="Mower",
        status="sensor.mower_status",
        mapping={"running": ["mowing"], "ended": ["parked"]},
        meter={"entity_id": CYCLE_ENERGY},
    )

    kiln, pump, mower = (await panel.call("coinop/devices/list"))["devices"]

    assert (kiln["type"], kiln["type_name"], kiln["capabilities"]) == (
        "other",
        "Kiln",
        ["average_power"],
    )
    assert (pump["type"], pump["type_name"], pump["capabilities"]) == (
        "other",
        "Pump",
        ["average_power", "per_run_meters"],
    )
    assert kiln["ha_settings"] == {
        "printer_device_id": None,
        "status": {"entity_id": KILN_STATUS, "attribute": None},
        "mapping": OTHER_MAPPING
        | {"paused": [], "finished": [], "cancelled": [], "fault": [], "ignored": []},
        "progress": {"remaining_time": None, "progress": None, "expected_energy": None},
        "consumption": {
            "source": "estimate",
            "running_power": 2000,
            "paused_power": None,
        },
        "price": {"source": "fixed", "value": 0.3},
    }
    assert mower["type"] == "robotic_mower"
    assert "type_name" not in mower


async def test_an_other_device_has_the_entities_every_device_has(
    hass: HomeAssistant, clock: Clock, entity_registry: er.EntityRegistry
) -> None:
    await add_kiln(hass)
    fired = record_events(hass, "event.kiln_run")

    await fire(hass, clock)

    assert coinop_entities(entity_registry) == basic_entities("kiln")
    [_, ended] = fired
    assert (ended["event_type"], ended["outcome"]) == ("ended", "unknown")
    assert ended["energy_kwh"] == pytest.approx(3.0)
    assert ended["total_cost"] == pytest.approx(0.90)
    assert {
        "program",
        "water_litres",
        "part_count",
        "cost_per_part",
        "material_grams",
    }.isdisjoint(ended)
