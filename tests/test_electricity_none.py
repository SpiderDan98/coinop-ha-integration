"""Electricity source none: a Device whose Runs get no Electricity Line Item."""

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
import pytest

from custom_components.coinop.const import DOMAIN

from .clock import Clock
from .devices import (
    ENERGY,
    POWER,
    WASHER_WATER,
    add_device,
    add_hub,
    add_washing_machine,
    basic_entities,
    coinop_entities,
    configure,
    reconfigure,
    start_reconfigure,
    walk_to_consumption,
)
from .http import HttpClient
from .registry import add_miele
from .test_cost_statement import export
from .test_device_flow import suggested
from .test_doses import doses
from .test_integration_profiles import accepted
from .test_manual_runs import create
from .test_manual_washes import ROWS
from .test_measured import add_metered_device, electricity, set_meter
from .test_program_consumption import approx, consumed
from .test_robotic_mowers import add_mower, set_mower
from .test_run_event import record_events
from .test_runs import NO_MATERIAL, set_status, stored_runs, value
from .test_templates import create as create_template
from .test_washer_profiles import walk_pre_filled
from .test_water import set_water
from .washing import DOSES, add_washer, set_washer, washed
from .websocket import PanelClient


@pytest.fixture(autouse=True)
async def settle_reload(hass: HomeAssistant) -> Any:
    """A Device added last reloads the hub; its tracker must not start during teardown."""
    yield
    await hass.async_block_till_done()


async def mow_an_hour(hass: HomeAssistant, clock: Clock) -> None:
    await set_mower(hass, "mowing")
    await clock.advance(minutes=60)
    await set_mower(hass, "parked")


async def test_electricity_source_none_skips_the_electricity_price(
    hass: HomeAssistant,
) -> None:
    result = await walk_to_consumption(hass, await add_hub(hass))
    assert result["menu_options"] == ["energy", "power", "estimate", "none"]

    result = await configure(hass, result, {"next_step_id": "none"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["consumption"] == {"source": "none"}
    assert "price" not in result["data"]


@pytest.mark.parametrize("language", ["en", "de"])
async def test_the_electricity_source_menu_names_none_and_explains_it(
    hass: HomeAssistant, language: str
) -> None:
    translations = await async_get_translations(
        hass, language, "config_subentries", [DOMAIN]
    )

    step = f"component.{DOMAIN}.config_subentries.device.step.consumption"
    name = translations[f"{step}.menu_options.none"]
    assert f"**{name}**" in translations[f"{step}.description"]


async def test_a_device_type_with_water_goes_on_to_its_water_steps(
    hass: HomeAssistant,
) -> None:
    await set_water(hass, 1000)
    await set_washer(hass, "off")

    washer = await add_washing_machine(
        hass, await add_hub(hass), source="none", water="meter", water_price=4.0
    )

    assert washer.data["consumption"] == {"source": "none"}
    assert "price" not in washer.data
    assert washer.data["water"]["entity_id"] == WASHER_WATER
    assert washer.data["water_price"] == {"source": "fixed", "value": 4.0}


async def test_reconfigure_offers_the_electricity_source_but_not_its_price(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, source="none")

    result = await start_reconfigure(hass, entry, subentry)

    assert result["menu_options"] == [
        "status",
        "job",
        "images",
        "progress",
        "consumption",
        "save",
    ]


@pytest.mark.parametrize(
    ("source", "source_input"),
    [
        ("energy", {"entity_id": ENERGY}),
        ("power", {"entity_id": POWER}),
        ("estimate", {"running_power": 100}),
    ],
)
async def test_a_source_picked_in_reconfigure_walks_on_to_the_missing_price(
    hass: HomeAssistant, source: str, source_input: dict[str, Any]
) -> None:
    await set_meter(hass, 10)
    await set_meter(hass, 100, entity=POWER, unit="W")
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, source="none")
    result = await start_reconfigure(hass, entry, subentry)
    result = await configure(hass, result, {"next_step_id": "consumption"})
    result = await configure(hass, result, {"next_step_id": source})

    result = await configure(hass, result, source_input)

    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.32})
    assert result["menu_options"] == [
        "status",
        "job",
        "images",
        "progress",
        "consumption",
        "price",
        "save",
    ]
    await configure(hass, result, {"next_step_id": "save"})
    assert subentry.data["consumption"]["source"] == source
    assert subentry.data["price"] == {"source": "fixed", "value": 0.32}


async def test_per_program_picked_in_reconfigure_walks_on_to_the_missing_price(
    hass: HomeAssistant,
) -> None:
    """No step of the source's own lies between its menu and the price."""
    washer = await add_washer(hass, source="none")
    [entry] = hass.config_entries.async_entries(DOMAIN)
    result = await start_reconfigure(hass, entry, washer)
    result = await configure(hass, result, {"next_step_id": "consumption"})

    result = await configure(hass, result, {"next_step_id": "per_program"})

    assert result["step_id"] == "price"
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.32})
    assert "price" in result["menu_options"]
    await configure(hass, result, {"next_step_id": "save"})
    assert washer.data["consumption"] == {"source": "per_program"}
    assert washer.data["price"] == {"source": "fixed", "value": 0.32}


async def test_a_price_entered_before_is_kept_while_the_source_is_none(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=120, price=0.28)

    await reconfigure(
        hass, entry, subentry, {"next_step_id": "consumption"}, {"next_step_id": "none"}
    )

    assert subentry.data["consumption"] == {"source": "none"}
    result = await start_reconfigure(hass, entry, subentry)
    assert "price" not in result["menu_options"]
    result = await configure(hass, result, {"next_step_id": "consumption"})
    result = await configure(hass, result, {"next_step_id": "estimate"})
    assert suggested(result, "running_power") is None
    result = await configure(hass, result, {"running_power": 90})
    assert result["step_id"] == "reconfigure"
    assert "price" in result["menu_options"]
    await configure(hass, result, {"next_step_id": "save"})
    assert subentry.data["price"] == {"source": "fixed", "value": 0.28}


async def test_detect_again_leaves_an_electricity_source_none_alone(
    hass: HomeAssistant,
) -> None:
    """Miele's profile finds the appliance's own energy meter."""
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(
        hass, entry, add_miele(hass), consumption={"next_step_id": "none"}
    )
    assert subentry.data["consumption"] == {"source": "none"}
    result = await start_reconfigure(hass, entry, subentry)

    result = await configure(hass, result, {"next_step_id": "detect"})
    while result["type"] is FlowResultType.FORM:
        result = await configure(hass, result, accepted(result))
    await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()

    data = entry.subentries[subentry.subentry_id].data
    assert data["consumption"] == {"source": "none"}
    assert "price" not in data


async def test_a_run_has_no_electricity_line_item_and_is_final_at_its_end(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """A Device without any computed cost is a valid Device."""
    await add_mower(hass, source="none")

    await mow_an_hour(hass, clock)

    [run] = stored_runs(hass_storage)
    assert run["finalised"] is True
    assert run["line_items"] == []
    assert run["flags"] == []


def kinds(run: dict[str, Any]) -> list[str]:
    return [item["kind"] for item in run["line_items"]]


async def test_water_and_doses_are_as_before_and_only_water_is_waited_for(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """Its Device Type would take the kWh of the Program Defaults, which has none."""
    await set_water(hass, 1000)
    washer = await add_washer(hass, hass_storage, source="none", water="meter")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "doses": DOSES,
            "program_defaults": {"default": {"doses": {"dose-liquid": 75}}},
        },
    )

    await set_washer(hass, "running")
    await clock.advance(minutes=60)
    await set_water(hass, 1050)
    await clock.advance(minutes=30)
    await set_washer(hass, "finished")
    assert stored_runs(hass_storage) == []
    await set_water(hass, 1050)

    [run] = stored_runs(hass_storage)
    assert [(i["kind"], i["quantity"], i["unit"]) for i in run["line_items"]] == [
        ("water", pytest.approx(50), "L"),
        ("material", 75, "ml"),
    ]
    assert run["flags"] == []


async def test_the_kwh_of_the_program_defaults_are_not_charged(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    washer = await add_washer(hass, source="none", water="per_program")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "program_defaults": {"default": {"doses": {}, "kwh": 0.8, "litres": 40}}
        },
    )

    await washed(hass, clock)

    [run] = stored_runs(hass_storage)
    assert [(i["kind"], i["quantity"]) for i in run["line_items"]] == [("water", 40)]
    assert run["flags"] == []


async def test_a_device_that_would_estimate_gets_no_electricity_either(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await add_device(hass, await add_hub(hass), source="none")

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert kinds(run) == ["material"]
    assert run["flags"] == NO_MATERIAL


async def test_switching_to_none_applies_from_the_next_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=100)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    [ended] = deepcopy(stored_runs(hass_storage))
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await reconfigure(
        hass, entry, subentry, {"next_step_id": "consumption"}, {"next_step_id": "none"}
    )
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    first, was_open, following = stored_runs(hass_storage)
    assert first == ended
    assert electricity(was_open)["method"] == "estimated"
    assert electricity(was_open)["quantity"] == pytest.approx(0.2)
    assert kinds(following) == ["material"]


async def test_a_run_open_at_the_switch_to_none_still_ends_measured_by_its_meter(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    [subentry] = entry.subentries.values()
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, 10.2)

    await reconfigure(
        hass, entry, subentry, {"next_step_id": "consumption"}, {"next_step_id": "none"}
    )
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    assert stored_runs(hass_storage) == []
    await clock.advance(minutes=2)
    await set_meter(hass, 10.52)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    was_open, following = stored_runs(hass_storage)
    assert electricity(was_open)["method"] == "measured"
    assert electricity(was_open)["quantity"] == pytest.approx(0.5)
    assert was_open["flags"] == NO_MATERIAL
    assert kinds(following) == ["material"]


# Reconfigure's inputs from source none to an estimate of 100 W at 0.30 per kWh.
TO_ESTIMATE = (
    {"next_step_id": "consumption"},
    {"next_step_id": "estimate"},
    {"running_power": 100},
    {"next_step_id": "fixed_price"},
    {"price": 0.30},
)


async def test_switching_from_none_applies_from_the_next_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, source="none")
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await reconfigure(hass, entry, subentry, *TO_ESTIMATE)
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    was_open, following = stored_runs(hass_storage)
    assert kinds(was_open) == ["material"]
    assert electricity(following)["quantity"] == pytest.approx(0.1)
    assert electricity(following)["amount"] == pytest.approx(0.03)


async def test_a_manual_run_has_no_electricity_line_item(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    device = await add_device(hass, await add_hub(hass), source="none")
    await clock.advance(hours=5)

    run = await create(panel, device.subentry_id)

    assert kinds(run) == ["material"]
    assert run["flags"] == NO_MATERIAL


async def test_a_manual_run_keeps_its_water_and_doses(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    washer = await add_washer(hass, hass_storage, source="none", water="per_program")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES, "program_defaults": ROWS},
    )
    await clock.advance(hours=3)

    run = await create(panel, washer.subentry_id, program="Cotton 60°")

    assert consumed(run) == approx([("water", "program_default", 60, "L", 0.24)])
    assert doses(run) == [
        ("dose-liquid", "program_default", "liquid", 60, "ml", 0.006, 0.36),
        ("dose-whitener", "program_default", "whitener", 20, "g", 0.004, 0.08),
    ]
    assert run["flags"] == []


async def test_the_sensors_stay_and_the_ended_event_reports_no_electricity(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    """A flat cost per Run comes from an automatic Line Item Template."""
    mower = await add_mower(hass, source="none")
    flat = await create_template(
        panel, label="Flat cost", unit_price=1.5, basis="entered"
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=mower.subentry_id,
        settings={"tags_for_new_runs": ["Garden"], "automatic_templates": [flat["id"]]},
    )
    fired = record_events(hass, "event.mower_run")

    await mow_an_hour(hass, clock)
    await hass.async_block_till_done()

    assert coinop_entities(entity_registry) == basic_entities("mower")
    [_, ended] = fired
    assert (ended["event_type"], ended["tags"]) == ("ended", ["Garden"])
    assert (ended["energy_kwh"], ended["total_cost"]) == (0, 1.5)
    assert value(hass, "sensor.mower_energy_in_runs") == 0
    assert value(hass, "sensor.mower_electricity_cost") == 0
    assert value(hass, "sensor.mower_total_cost") == 1.5


async def test_the_totals_by_kind_and_a_cost_statement_have_no_electricity(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    washer = await add_washer(hass, source="none", water="per_program")
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"program_defaults": {"default": {"doses": {}, "litres": 40}}},
    )
    await washed(hass, clock)
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    groups = (await panel.call("coinop/aggregates/get", group_by=["kind"]))["groups"]
    statement = await export(panel, browser, run_ids=[run["id"]])

    assert [(g["kind"], g["cost"], g["energy_kwh"]) for g in groups] == [
        ("water", 0.16, 0)
    ]
    assert "Water 40 L × €4.00/m³ €0.16" in statement.lines  # noqa: RUF001
    assert [line for line in statement.lines if "Electricity" in line] == []


async def mowed(hass: HomeAssistant, clock: Clock, panel: PanelClient) -> str:
    """An hour's Run of a robotic mower with electricity source none; its id."""
    await add_mower(hass, source="none")
    await mow_an_hour(hass, clock)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run_id: str = summary["id"]
    return run_id


async def test_electricity_is_added_by_hand_once_in_kwh_and_marked_as_entered(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run_id = await mowed(hass, clock, panel)

    run = (
        await panel.call(
            "coinop/line_items/add",
            run_id=run_id,
            kind="electricity",
            quantity=1.5,
            unit_price=0.32,
        )
    )["run"]

    [item] = run["line_items"]
    assert (item["kind"], item["quantity"], item["unit"], item["method"]) == (
        "electricity",
        1.5,
        "kWh",
        "entered",
    )
    assert item["amount"] == pytest.approx(0.48)
    assert (item["locked"], item["deletable"], item["computed"]) == (False, True, None)
    assert run["subtotals"]["electricity"] == 0.48
    assert value(hass, "sensor.mower_energy_in_runs") == 1.5
    assert value(hass, "sensor.mower_electricity_cost") == pytest.approx(0.48)
    error = await panel.error(
        "coinop/line_items/add", run_id=run_id, kind="electricity", quantity=1
    )
    assert error["code"] == "not_allowed"


async def test_electricity_added_by_hand_starts_empty_and_is_edited_and_deleted(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run_id = await mowed(hass, clock, panel)
    item = {"run_id": run_id}

    run = (await panel.call("coinop/line_items/add", **item, kind="electricity"))["run"]
    [added] = run["line_items"]
    item["line_item_id"] = added["id"]
    assert (added["quantity"], added["unit_price"], added["amount"]) == (None, 0, 0)

    run = (
        await panel.call(
            "coinop/line_items/update", **item, quantity=2, unit_price=0.25
        )
    )["run"]
    [edited] = run["line_items"]
    assert (edited["amount"], edited["computed"]) == (0.5, None)
    error = await panel.error("coinop/line_items/update", **item, unit="Wh")
    assert error["code"] == "not_allowed"
    error = await panel.error("coinop/line_items/update", **item, unit_price=-1)
    assert error["code"] == "invalid_format"
    run = (await panel.call("coinop/line_items/reset", **item))["run"]
    assert run["line_items"] == [edited]

    run = (await panel.call("coinop/line_items/delete", **item))["run"]
    assert run["line_items"] == []
    assert value(hass, "sensor.mower_energy_in_runs") == 0


async def test_electricity_is_added_by_hand_to_an_open_run_and_stays(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_mower(hass, source="none")
    await set_mower(hass, "mowing")
    await clock.advance(minutes=30)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]

    await panel.call(
        "coinop/line_items/add",
        run_id=summary["id"],
        kind="electricity",
        quantity=0.2,
        unit_price=0.30,
    )
    await clock.advance(minutes=30)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    [item] = run["line_items"]
    assert (run["ended"], item["locked"], item["quantity"]) == (None, False, 0.2)
    await panel.call(
        "coinop/line_items/update",
        run_id=summary["id"],
        line_item_id=item["id"],
        quantity=0.25,
    )
    await set_mower(hass, "parked")

    [stored] = stored_runs(hass_storage)
    assert electricity(stored)["quantity"] == 0.25
    assert electricity(stored)["method"] == "entered"


def entered_electricity(run: dict[str, Any]) -> tuple[Any, ...]:
    """The method, kWh and amount of the Run's one Electricity Line Item."""
    [item] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    return item["method"], item["quantity"], item["amount"]


async def test_electricity_is_added_by_hand_whatever_the_devices_source_is_now(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A Run that started while the source was none has no Electricity Line Item."""
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, source="none")
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await reconfigure(hass, entry, subentry, *TO_ESTIMATE)
    runs = (await panel.call("coinop/runs/list"))["runs"]
    assert sorted(run["ended"] is None for run in runs) == [False, True]

    for run in runs:
        await panel.call(
            "coinop/line_items/add",
            run_id=run["id"],
            kind="electricity",
            quantity=0.2,
            unit_price=0.25,
        )
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    ended, was_open = stored_runs(hass_storage)
    by_hand = ("entered", 0.2, pytest.approx(0.05))
    assert (entered_electricity(ended), entered_electricity(was_open)) == (
        by_hand,
        by_hand,
    )


async def test_electricity_added_by_hand_survives_a_switch_to_another_source(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, source="none")
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call(
        "coinop/line_items/add",
        run_id=summary["id"],
        kind="electricity",
        quantity=0.2,
        unit_price=0.25,
    )

    await reconfigure(hass, entry, subentry, *TO_ESTIMATE)
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert entered_electricity(run) == ("entered", 0.2, pytest.approx(0.05))


async def test_a_run_that_has_its_electricity_takes_no_second_one(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_device(hass, await add_hub(hass), running_power=100)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]

    open_error = await panel.error(
        "coinop/line_items/add", run_id=summary["id"], kind="electricity", quantity=1
    )
    await set_status(hass, "finished")
    ended_error = await panel.error(
        "coinop/line_items/add", run_id=summary["id"], kind="electricity", quantity=1
    )

    assert (open_error["code"], ended_error["code"]) == ("not_allowed", "not_allowed")
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert electricity(run)["deletable"] is False


async def test_a_manual_runs_empty_electricity_is_one_entered_by_hand_too(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A Device with a source but nothing to compute a past Run from."""
    mower = await add_mower(hass)
    await clock.advance(hours=5)
    run = await create(panel, mower.subentry_id)
    [item] = run["line_items"]
    assert (item["kind"], item["method"], item["deletable"]) == (
        "electricity",
        "entered",
        True,
    )

    await panel.call(
        "coinop/line_items/delete", run_id=run["id"], line_item_id=item["id"]
    )
    run = (
        await panel.call("coinop/line_items/add", run_id=run["id"], kind="electricity")
    )["run"]

    assert kinds(run) == ["electricity"]
