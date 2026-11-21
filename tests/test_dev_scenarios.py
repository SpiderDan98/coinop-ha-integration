"""The dev container's Scenarios load through today's websocket API."""

import asyncio
from pathlib import Path
from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict
import pytest
from pytest_homeassistant_custom_component.common import MockUser

import custom_components
from dev.coinop_dev import async_setup
from dev.coinop_dev.scenarios import async_load

from .clock import Clock
from .devices import configure
from .test_quick_start import offered
from .websocket import PanelClient

DEV = Path(__file__).parents[1] / "dev"
CONFIG = DEV / "configuration.yaml"
PLUG_ENERGY = "sensor.washing_machine_plug_energy"
DISHWASHER_PLUG_ENERGY = "sensor.dishwasher_plug_energy"
PLUG_POWER = "sensor.kobra_s1_plug_power"


@pytest.fixture
async def helpers(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Devices' helpers from the dev configuration.yaml, and the dev container's
    integrations where Home Assistant finds them."""
    monkeypatch.setattr(
        custom_components, "__path__", [*custom_components.__path__, str(DEV)]
    )
    hass.data.pop(DATA_CUSTOM_COMPONENTS, None)
    config = await hass.async_add_executor_job(load_yaml_dict, CONFIG)
    for domain in ("input_select", "input_text", "input_number", "template"):
        assert await async_setup_component(hass, domain, {domain: config[domain]})


async def counts(panel: PanelClient) -> tuple[int, int, int, int]:
    """Devices, Materials, Runs and open Runs."""
    runs = (await panel.call("coinop/runs/list"))["runs"]
    return (
        len((await panel.call("coinop/devices/list"))["devices"]),
        len((await panel.call("coinop/materials/list"))["materials"]),
        len(runs),
        sum(run["ended"] is None for run in runs),
    )


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("empty", (0, 0, 0, 0)),
        ("quick-start", (0, 0, 0, 0)),
        ("few-runs", (1, 3, 7, 0)),
        ("printing-now", (1, 3, 8, 1)),
        ("two-printers", (2, 5, 60, 0)),
        ("washing-machine", (1, 4, 10, 0)),
    ],
)
async def test_a_scenario_fills_coinop_from_scratch(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    name: str,
    expected: tuple[int, int, int, int],
) -> None:
    await async_load(hass, name, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == expected
    assert len(hass.config_entries.async_entries("coinop")) == 1


@pytest.mark.usefixtures("helpers")
async def test_the_long_history_spans_two_years_and_goes_with_the_next_scenario(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, "long-history", hass_admin_user)
    runs = (await panel.call("coinop/runs/list"))["runs"]
    devices, materials, _, _ = await counts(panel)
    thumbnails = await hass.async_add_executor_job(
        lambda: list(files.glob("images/*/*"))
    )

    await async_load(hass, "empty", hass_admin_user)

    assert (devices, materials) == (2, 8)
    assert len(runs) > 250
    assert any(run["flags"] for run in runs)
    assert thumbnails
    assert await counts(panel) == (0, 0, 0, 0)
    assert not await hass.async_add_executor_job(files.exists)


@pytest.mark.usefixtures("helpers")
async def test_the_washing_machine_mixes_measured_values_and_program_defaults(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, "washing-machine", hass_admin_user)
    await hass.async_block_till_done()

    runs = [
        (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
        for run in (await panel.call("coinop/runs/list"))["runs"]
    ]
    methods = {
        (item["kind"], item.get("method") or item.get("dose_source"))
        for run in runs
        for item in run["line_items"]
    }
    assert methods == {
        ("electricity", "measured"),
        ("water", "measured"),
        ("material", "stock_input"),
        ("material", "program_default"),
        ("material", "default_row"),
    }
    assert {run["program"] for run in runs} == {
        "Cotton 60°",
        "Eco 40-60",
        "Wool",
        "Quick 30",
        None,
    }
    assert any("ended_early_defaults" in run["flags"] for run in runs)


@pytest.mark.usefixtures("helpers")
async def test_the_load_service_fills_coinop_when_a_task_awaits_its_call(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    """As over REST (`make dev`), whose view awaits the service call in a task."""
    assert await async_setup(hass, {})
    call = hass.services.async_call(
        "coinop_dev",
        "load",
        {"scenario": "washing-machine"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )

    async with asyncio.timeout(10):
        await hass.async_create_task(call)

    assert await counts(panel) == (1, 4, 10, 0)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_washing_machine_washdata_follows(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass, "Washing machine · WashData", optional_meter=PLUG_ENERGY, price=0.32
    )

    await set_helper(hass, "input_number.washer_energy", 100)
    await set_helper(hass, "input_select.washer_program", "Eco 40-60")
    await set_helper(hass, "input_select.washer_status", "running")
    await clock.advance(hours=1)
    await set_helper(hass, "input_number.washer_energy", 100.7)
    await set_helper(hass, "input_select.washer_status", "cancelled")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["outcome"]) == ("Eco 40-60", "cancelled")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.7)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_dishwasher_washdata_follows_as_a_dishwasher(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass,
        "Dishwasher · WashData",
        optional_meter=DISHWASHER_PLUG_ENERGY,
        price=0.32,
        water_price=4.2,
    )

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert (device["name"], device["type"]) == ("Dishwasher", "dishwasher")
    await set_helper(hass, "input_number.dishwasher_energy", 50)
    await set_helper(hass, "input_select.dishwasher_program", "Eco 50°")
    await set_helper(hass, "input_select.dishwasher_status", "running")
    await clock.advance(hours=2)
    await set_helper(hass, "input_number.dishwasher_energy", 50.9)
    await set_helper(hass, "input_select.dishwasher_status", "finished")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["outcome"]) == ("Eco 50°", "completed")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.9)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_printer_of_the_anycubic_stand_in(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass, "Kobra S1 · Anycubic Cloud & LAN", meter=PLUG_POWER, price=0.32
    )

    await set_helper(hass, "input_number.kobra_power", 120)
    await set_helper(hass, "input_text.kobra_job", "Benchy.gcode")
    await set_helper(hass, "input_select.kobra_status", "printing")
    await clock.advance(hours=1)
    await set_helper(hass, "input_select.kobra_status", "finished")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["name"], run["outcome"]) == ("Benchy", "completed")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.12)


async def test_the_next_scenario_takes_the_stand_ins_devices_away(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    helpers: None,
    files: Path,
) -> None:
    stand_ins = ("anycubic_cloud", "ha_washdata")
    await async_load(hass, "quick-start", hass_admin_user)
    assert [len(hass.config_entries.async_entries(d)) for d in stand_ins] == [1, 2]

    await async_load(hass, "empty", hass_admin_user)

    assert not any(hass.config_entries.async_entries(d) for d in stand_ins)


async def quick_start(hass: HomeAssistant, label: str, **answers: Any) -> None:
    """Add the HA device Quick Start offers as `label`."""
    [entry] = hass.config_entries.async_entries("coinop")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "quick_start"
    devices = {option["label"]: option["value"] for option in offered(result)}
    assert list(devices) == [
        "Kobra S1 · Anycubic Cloud & LAN",
        "Washing machine · WashData",
        "Dishwasher · WashData",
        "manual",
    ]
    result = await configure(hass, result, {"device": devices[label]})
    result = await configure(hass, result, answers)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")


async def set_helper(hass: HomeAssistant, entity_id: str, value: str | float) -> None:
    domain = entity_id.split(".")[0]
    service, field = (
        ("select_option", "option")
        if domain == "input_select"
        else ("set_value", "value")
    )
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, field: value}, blocking=True
    )
    await hass.async_block_till_done()
