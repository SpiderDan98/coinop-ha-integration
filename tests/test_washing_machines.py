"""Washing machines: the second Device Type, with the Run lifecycle of a printer."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_STATUS,
    add_device,
    add_hub,
    add_washing_machine,
    configure,
    open_device_types,
    start_add_device,
    start_reconfigure,
    walk_to_mapping,
)
from .http import HttpClient
from .test_cost_statement import export
from .test_device_flow import fields, offered
from .test_run_event import record_events
from .test_runs import stored_runs, value
from .washing import add_washer, set_energy, set_washer, washed
from .websocket import PanelClient


def washer_entry(hass: HomeAssistant) -> ConfigEntry:
    [entry] = hass.config_entries.async_entries("coinop")
    return entry


async def test_manual_setup_starts_with_the_device_type(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await open_device_types(hass, entry)

    assert result["step_id"] == "user"
    assert fields(result) == ["device_type"]
    assert offered(result, "device_type") == [
        "3d_printer",
        "washing_machine",
        "dishwasher",
        "tumble_dryer",
        "coffee_machine",
        "oven",
        "ev_charger",
        "robotic_mower",
        "other",
        "quick_start",
    ]


async def test_a_washing_machine_asks_status_mapping_electricity_and_price(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)

    result = await walk_to_mapping(
        hass, entry, status=WASHER_STATUS, device_type="washing_machine"
    )
    result = await configure(hass, result, WASHER_MAPPING)
    assert result["step_id"] == "program"
    result = await configure(hass, result, {})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["energy", "power", "per_program", "none"]
    result = await configure(hass, result, {"next_step_id": "power"})
    assert fields(result) == ["entity_id", "attribute"]

    subentry = await add_washing_machine(hass, entry, status="sensor.other_washer")

    assert subentry.data["device_type"] == "washing_machine"
    assert sorted(subentry.data) == [
        "consumption",
        "device_type",
        "mapping",
        "price",
        "printer_device_id",
        "program",
        "status",
        "water",
    ]


async def test_the_washing_machine_flow_validates_like_a_printers(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    await add_washing_machine(hass, entry)
    result = await walk_to_mapping(
        hass, entry, name="Second", status="sensor.dryer", device_type="washing_machine"
    )

    result = await configure(hass, result, {"running": ["running"]})
    assert result["errors"] == {"base": "no_ending_value"}
    result = await start_add_device(hass, entry, device_type="washing_machine")
    result = await configure(hass, result, {"name": "Second"})
    result = await configure(hass, result, {"entity_id": WASHER_STATUS})
    assert result["errors"] == {"entity_id": "status_already_used"}


async def test_reconfiguring_a_washing_machine_offers_its_sections(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    subentry = await add_washing_machine(hass, entry)

    result = await start_reconfigure(hass, entry, subentry)

    assert result["menu_options"] == [
        "status",
        "program",
        "consumption",
        "price",
        "water",
        "save",
    ]


async def test_a_load_is_a_run_with_measured_electricity(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    entry = await add_hub(hass)
    await add_washing_machine(hass, entry, price=0.40)

    await set_washer(hass, "running")
    await clock.advance(minutes=50)
    await set_energy(hass, 100.8)
    await set_washer(hass, "paused")
    await clock.advance(minutes=5)
    await set_washer(hass, "running")
    await clock.advance(minutes=40)
    await set_energy(hass, 101.2)
    await set_washer(hass, "finished")
    await set_energy(hass, 101.2)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["flags"], run["part_count"]) == ("completed", [], None)
    [electricity] = run["line_items"]
    assert electricity["kind"] == "electricity"
    assert electricity["method"] == "measured"
    assert electricity["quantity"] == pytest.approx(1.2)
    assert electricity["amount"] == pytest.approx(0.48)
    assert value(hass, "sensor.washer_total_cost") == pytest.approx(0.48)


@pytest.fixture
async def washer(hass: HomeAssistant, clock: Clock) -> ConfigSubentry:
    """A washing machine on a plug's energy meter at 0.50 per kWh."""
    return await add_washer(hass, program=False, price=0.50)


@pytest.mark.usefixtures("washer")
async def test_a_washing_machine_has_the_printer_entities_with_water_for_material_used(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    assert sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    ) == [
        "event.washer_run",
        "sensor.washer_current_run_cost",
        "sensor.washer_electricity_cost",
        "sensor.washer_energy_in_runs",
        "sensor.washer_flagged_runs",
        "sensor.washer_last_run_cost",
        "sensor.washer_material_cost",
        "sensor.washer_other_cost",
        "sensor.washer_running_time",
        "sensor.washer_runs",
        "sensor.washer_total_cost",
        "sensor.washer_water_cost",
        "sensor.washer_water_in_runs",
    ]


@pytest.mark.usefixtures("washer")
async def test_a_washing_machine_run_has_no_part_count_in_its_sensor_and_event(
    hass: HomeAssistant, clock: Clock
) -> None:
    fired = record_events(hass, "event.washer_run")

    await washed(hass, clock, kwh=1.2)

    last = hass.states.get("sensor.washer_last_run_cost")
    assert last is not None
    assert float(last.state) == pytest.approx(0.6)
    assert last.attributes["outcome"] == "completed"
    assert {"part_count", "cost_per_part"}.isdisjoint(last.attributes)
    [_, ended] = fired
    assert ended["event_type"] == "ended"
    assert ended["total_cost"] == pytest.approx(0.6)
    assert ended["energy_kwh"] == pytest.approx(1.2)
    assert {"part_count", "cost_per_part", "material_grams"}.isdisjoint(ended)


@pytest.mark.usefixtures("washer")
async def test_the_panel_gets_no_part_count_for_a_washing_machine_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await washed(hass, clock, kwh=1.2)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["total"], run["part_count"], run["cost_per_part"]) == (0.6, None, None)
    error = await panel.error("coinop/runs/update", run_id=run["id"], part_count=2)
    assert error["code"] == "not_allowed"


@pytest.mark.usefixtures("washer")
async def test_the_devices_tab_learns_what_each_device_type_has(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    await add_device(hass, washer_entry(hass))

    devices = (await panel.call("coinop/devices/list"))["devices"]

    assert [(d["type"], d["capabilities"]) for d in devices] == [
        (
            "washing_machine",
            ["doses", "per_run_meters", "program", "program_consumption", "water"],
        ),
        ("3d_printer", ["average_power", "images", "job", "material", "part_count"]),
    ]
    assert devices[0]["ha_settings"] == {
        "printer_device_id": None,
        "status": {"entity_id": WASHER_STATUS, "attribute": None},
        "mapping": WASHER_MAPPING | {"ended": [], "fault": []},
        "program": {"entity_id": None, "attribute": None},
        "consumption": {
            "source": "energy",
            "entity_id": WASHER_ENERGY,
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.5},
        "water": {"source": "none"},
    }


async def test_tags_and_automatic_templates_apply_to_washing_machine_runs(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    template = await panel.call(
        "coinop/templates/create",
        template={"label": "Depreciation", "unit_price": 0.3, "basis": "entered"},
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "tags_for_new_runs": ["Flat 2"],
            "automatic_templates": [template["template"]["id"]],
        },
    )

    await washed(hass, clock, kwh=1.2)

    [run] = stored_runs(hass_storage)
    assert run["tags"] == ["Flat 2"]
    assert [(i["kind"], i["label"]) for i in run["line_items"]] == [
        ("electricity", None),
        ("other", "Depreciation"),
    ]


@pytest.mark.usefixtures("washer")
async def test_a_cost_statement_shows_a_washing_machine_run_without_part_count(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    await washed(hass, clock, kwh=1.2)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], name="Cotton 60")

    detailed = await export(panel, browser, run_ids=[run["id"]])
    compact = await export(panel, browser, run_ids=[run["id"]], detail="compact")

    assert "Washer · Jan 15, 2026 · Running time 1 h 30 min" in detailed.lines
    assert "Electricity 1.2 kWh × €0.50 €0.60" in detailed.lines  # noqa: RUF001
    assert compact.lines[4:6] == [
        "Run Device Start Total",
        "Cotton 60 Washer Jan 15, 2026 €0.60",
    ]
    for pages in (detailed.pages, compact.pages):
        assert "part" not in "".join(pages).lower()
