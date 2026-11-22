"""Water: a measured Water Line Item on washing machine Runs, like electricity."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_WATER,
    WATER_PRICE,
    add_device,
    add_hub,
    add_washing_machine,
    answer_progress,
    configure,
    start_reconfigure,
    walk_to_mapping,
)
from .http import HttpClient
from .test_cost_statement import export
from .test_device_flow import fields
from .test_measured import electricity
from .test_persistence import live_runs
from .test_run_event import record_events
from .test_runs import set_status, stored_runs, value
from .washing import set_energy, set_washer, washed
from .websocket import PanelClient


@pytest.fixture(autouse=True)
async def settle_reload(hass: HomeAssistant) -> Any:
    """A Device added last reloads the hub; its tracker must not start during teardown."""
    yield
    await hass.async_block_till_done()


async def set_water(
    hass: HomeAssistant,
    value: float | str,
    *,
    entity: str = WASHER_WATER,
    unit: str = "L",
) -> None:
    hass.states.async_set(entity, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def set_water_price(
    hass: HomeAssistant, value: float, unit: str = "EUR/m³"
) -> None:
    hass.states.async_set(WATER_PRICE, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


def water(run: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = next(i for i in run["line_items"] if i["kind"] == "water")
    return item


async def add_water_washer(hass: HomeAssistant, **water: Any) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    await add_washing_machine(hass, await add_hub(hass), **({"water": "meter"} | water))


async def test_meter_readings_give_litres_priced_across_a_water_price_change(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 1000)
    await set_water_price(hass, 4.0)
    await add_water_washer(hass, water_price={"entity_id": WATER_PRICE})

    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_water(hass, 1020)
    await set_water_price(hass, 5.0)
    await clock.advance(minutes=30)
    await set_water(hass, 1050)
    await set_washer(hass, "finished")
    await set_water(hass, 1050)
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    item = water(run)
    assert (item["unit"], item["method"]) == ("L", "measured")
    assert item["quantity"] == pytest.approx(50)
    assert [(s["kwh"], s["unit_price"]) for s in item["segments"]] == [
        (pytest.approx(20), pytest.approx(0.004)),
        (pytest.approx(30), pytest.approx(0.005)),
    ]
    assert item["amount"] == pytest.approx(20 * 0.004 + 30 * 0.005)
    assert run["flags"] == []


async def walk_to_water(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Walk Add Device for a washing machine to the water source menu."""
    result = await walk_to_mapping(
        hass, entry, status="sensor.washer_status", device_type="washing_machine"
    )
    result = await configure(hass, result, WASHER_MAPPING)
    result = await configure(hass, result, {})
    result = await answer_progress(hass, result)
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": WASHER_ENERGY})
    result = await configure(hass, result, {"next_step_id": "fixed_price"})
    result = await configure(hass, result, {"price": 0.3})
    assert result["step_id"] == "water", result.get("errors")
    return result


async def test_water_comes_from_a_meter_a_flow_sensor_or_nowhere(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    result = await walk_to_water(hass, await add_hub(hass))

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [
        "water_meter",
        "water_flow",
        "water_per_program",
        "water_none",
    ]

    result = await configure(hass, result, {"next_step_id": "water_none"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["water"] == {"source": "none"}
    assert "water_price" not in result["data"]


@pytest.mark.parametrize(
    ("step", "unit"),
    [
        ("water_meter", "L"),
        ("water_meter", "m³"),
        ("water_meter", "gal"),
        ("water_meter", "ft³"),
        ("water_meter", "CCF"),
        ("water_flow", "L/min"),
        ("water_flow", "m³/h"),
    ],
)
async def test_volume_and_flow_units_are_recognised(
    hass: HomeAssistant, step: str, unit: str
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 3, unit=unit)
    result = await walk_to_water(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": step})
    assert fields(result) == ["entity_id", "attribute"]

    result = await configure(hass, result, {"entity_id": WASHER_WATER})

    assert result["step_id"] == "water_price", result.get("errors")
    result = await configure(hass, result, {"next_step_id": "water_fixed_price"})
    result = await configure(hass, result, {"price": 4.2})
    assert result["data"]["water"] == {
        "source": step.removeprefix("water_"),
        "entity_id": WASHER_WATER,
        "attribute": None,
        "unit": unit,
        "factor": None,
    }
    assert result["data"]["water_price"] == {"source": "fixed", "value": 4.2}


async def test_an_unknown_water_unit_asks_for_a_conversion_factor(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 3, unit="buckets")
    result = await walk_to_water(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "water_meter"})

    result = await configure(hass, result, {"entity_id": WASHER_WATER})
    assert result["errors"] == {"entity_id": "unknown_unit"}
    assert "factor" in fields(result)
    result = await configure(hass, result, {"entity_id": WASHER_WATER, "factor": 10})

    assert result["step_id"] == "water_price"


async def test_a_water_attribute_asks_for_its_unit(hass: HomeAssistant) -> None:
    await set_energy(hass, 100)
    result = await walk_to_water(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "water_meter"})

    result = await configure(
        hass, result, {"entity_id": "sensor.washer", "attribute": "water"}
    )
    assert result["step_id"] == "water_meter_unit"
    result = await configure(hass, result, {"unit": "m³"})

    assert result["step_id"] == "water_price"


@pytest.mark.parametrize("unit", ["EUR/m³", "€/L", "ct/L"])
async def test_a_water_price_entity_in_m3_or_litres_is_accepted(
    hass: HomeAssistant, unit: str
) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, 100)
    await set_water(hass, 3)
    await set_water_price(hass, 4, unit)
    result = await walk_to_water(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": WASHER_WATER})
    result = await configure(hass, result, {"next_step_id": "water_price_entity"})

    result = await configure(hass, result, {"entity_id": WATER_PRICE})

    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    assert result["data"]["water_price"]["unit"] == unit


async def test_a_water_price_per_kwh_is_not_understood(hass: HomeAssistant) -> None:
    hass.config.currency = "EUR"
    await set_energy(hass, 100)
    await set_water(hass, 3)
    await set_water_price(hass, 4, "EUR/kWh")
    result = await walk_to_water(hass, await add_hub(hass))
    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": WASHER_WATER})
    result = await configure(hass, result, {"next_step_id": "water_price_entity"})

    result = await configure(hass, result, {"entity_id": WATER_PRICE})

    assert result["errors"] == {"entity_id": "unknown_unit"}


async def test_reconfigure_offers_water_and_asks_a_price_for_a_new_meter(
    hass: HomeAssistant,
) -> None:
    await set_energy(hass, 100)
    await set_water(hass, 3)
    entry = await add_hub(hass)
    subentry = await add_washing_machine(hass, entry)
    result = await start_reconfigure(hass, entry, subentry)
    assert result["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "water",
        "save",
    ]

    result = await configure(hass, result, {"next_step_id": "water"})
    result = await configure(hass, result, {"next_step_id": "water_meter"})
    result = await configure(hass, result, {"entity_id": WASHER_WATER})
    assert result["step_id"] == "water_price"
    result = await configure(hass, result, {"next_step_id": "water_fixed_price"})
    result = await configure(hass, result, {"price": 5})

    assert result["menu_options"] == [
        "status",
        "program",
        "progress",
        "consumption",
        "price",
        "water",
        "water_price",
        "save",
    ]
    result = await configure(hass, result, {"next_step_id": "save"})
    assert result["type"] is FlowResultType.ABORT
    assert subentry.data["water"]["source"] == "meter"
    assert subentry.data["water_price"] == {"source": "fixed", "value": 5}


async def test_a_flow_sensor_is_integrated_like_a_power_sensor(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 0, unit="L/min")
    await add_water_washer(hass, water="flow")

    await set_washer(hass, "running")
    await clock.advance(minutes=10)
    await set_water(hass, 6, unit="L/min")
    await clock.advance(minutes=5)
    await set_water(hass, 0, unit="L/min")
    await clock.advance(minutes=30)
    await set_water(hass, 0.3, unit="m³/h")
    await clock.advance(minutes=4)
    await set_water(hass, 0, unit="L/min")
    await clock.advance(minutes=1)
    await set_washer(hass, "finished")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    item = water(run)
    assert item["method"] == "measured"
    assert item["quantity"] == pytest.approx(6 * 5 + 5 * 4)
    assert item["amount"] == pytest.approx(50 * 0.004)


async def test_the_open_run_shows_the_water_used_so_far(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_washer(hass, "running")
    await clock.advance(minutes=20)
    await set_water(hass, 1012)
    await clock.advance(minutes=2)

    [run] = live_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(12)
    assert value(hass, "sensor.washer_current_run_cost") == pytest.approx(
        12 * 0.004, abs=0.01
    )


async def test_a_water_meter_gap_and_reset_are_flagged_as_for_electricity(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_washer(hass, "running")
    await clock.advance(minutes=10)
    await set_water(hass, STATE_UNAVAILABLE)
    await clock.advance(minutes=10)
    await set_water(hass, 1020)
    await clock.advance(minutes=10)
    await set_water(hass, 5)
    await clock.advance(minutes=10)
    await set_water(hass, 15)
    await set_washer(hass, "finished")
    await set_water(hass, 15)
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(20 + 5 + 10)
    assert run["flags"] == ["consumption_gap", "meter_reset"]


async def test_without_a_final_water_report_the_last_reading_applies_after_five_minutes(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_water(hass, 1040)
    await clock.advance(minutes=10)
    await set_energy(hass, 101)
    await set_washer(hass, "finished")
    await set_energy(hass, 101)

    await clock.advance(minutes=4, seconds=59)
    assert stored_runs(hass_storage) == []
    await clock.advance(seconds=1)

    [run] = stored_runs(hass_storage)
    assert water(run)["quantity"] == pytest.approx(40)


async def test_a_per_cycle_meter_dropping_to_zero_after_the_end_counts_once(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    """Miele's per-cycle counters keep the cycle's total for a while, then reset."""
    await set_water(hass, 0)
    await set_energy(hass, 0)
    await add_water_washer(hass)
    await set_energy(hass, 0)
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_water(hass, 30)
    await set_energy(hass, 0.4)
    await clock.advance(minutes=30)
    await set_water(hass, 48)
    await set_energy(hass, 0.9)
    await clock.advance(minutes=1)
    await set_washer(hass, "finished")
    await clock.advance(minutes=2)
    await set_water(hass, 0)
    await set_energy(hass, 0)
    await clock.advance(minutes=5)

    # The next load starts from 0, reported as it starts.
    await set_water(hass, 0)
    await set_energy(hass, 0)
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_water(hass, 40)
    await set_energy(hass, 0.7)
    await clock.advance(minutes=1)
    await set_washer(hass, "finished")
    await clock.advance(minutes=2)
    await set_water(hass, 0)
    await set_energy(hass, 0)
    await clock.advance(minutes=5)

    first, second = stored_runs(hass_storage)
    assert water(first)["quantity"] == pytest.approx(48)
    assert water(second)["quantity"] == pytest.approx(40)
    assert electricity(first)["quantity"] == pytest.approx(0.9)
    assert electricity(second)["quantity"] == pytest.approx(0.7)
    assert first["flags"] == second["flags"] == []


async def test_water_in_runs_and_water_cost_add_up_and_the_ended_event_has_litres(
    hass: HomeAssistant, clock: Clock
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    fired = record_events(hass, "event.washer_run")

    for start, litres in ((1000, 1045), (1045, 1100)):
        await set_water(hass, start)
        await set_washer(hass, "running")
        await clock.advance(minutes=60)
        await set_water(hass, litres)
        await set_washer(hass, "finished")
        await set_water(hass, litres)
        await clock.advance(minutes=5)

    water_in_runs = hass.states.get("sensor.washer_water_in_runs")
    assert water_in_runs is not None
    assert float(water_in_runs.state) == pytest.approx(100)
    assert water_in_runs.attributes["unit_of_measurement"] == "L"
    assert water_in_runs.attributes["device_class"] == "water"
    assert water_in_runs.attributes["state_class"] == "total"
    assert value(hass, "sensor.washer_water_cost") == pytest.approx(0.4)
    assert value(hass, "sensor.washer_total_cost") == pytest.approx(0.4)
    ended = [event for event in fired if event["event_type"] == "ended"]
    assert [event["water_litres"] for event in ended] == [
        pytest.approx(45),
        pytest.approx(55),
    ]


async def test_without_a_water_source_water_is_added_by_hand(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_water_washer(hass, water="none")
    await washed(hass, clock, kwh=1.2)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert [i["kind"] for i in run["line_items"]] == ["electricity"]

    run = (
        await panel.call(
            "coinop/line_items/add",
            run_id=summary["id"],
            kind="water",
            quantity=60,
            unit_price=0.0045,
        )
    )["run"]

    item = water(run)
    assert (item["quantity"], item["unit"], item["method"]) == (60, "L", "entered")
    assert item["amount"] == pytest.approx(0.27)
    assert item["deletable"] is True
    assert run["subtotals"]["water"] == 0.27
    assert value(hass, "sensor.washer_water_in_runs") == 60
    error = await panel.error(
        "coinop/line_items/add", run_id=summary["id"], kind="water", quantity=1
    )
    assert error["code"] == "not_allowed"
    error = await panel.error(
        "coinop/line_items/update",
        run_id=summary["id"],
        line_item_id=item["id"],
        unit="m³",
    )
    assert error["code"] == "not_allowed"
    run = (
        await panel.call(
            "coinop/line_items/delete", run_id=summary["id"], line_item_id=item["id"]
        )
    )["run"]
    assert [i["kind"] for i in run["line_items"]] == ["electricity"]


async def test_measured_water_is_kept_but_can_be_corrected(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_water(hass, 1000)
    await set_washer(hass, "running")
    await clock.advance(minutes=60)
    await set_water(hass, 1050)
    await set_washer(hass, "finished")
    await set_water(hass, 1050)
    await clock.advance(minutes=5)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    item = water(run)
    assert item["deletable"] is False

    run = (
        await panel.call(
            "coinop/line_items/update",
            run_id=summary["id"],
            line_item_id=item["id"],
            quantity=40,
        )
    )["run"]

    assert water(run)["amount"] == pytest.approx(0.16)
    assert water(run)["computed"]["quantity"] == pytest.approx(50)
    error = await panel.error(
        "coinop/line_items/delete", run_id=summary["id"], line_item_id=item["id"]
    )
    assert error["code"] == "not_allowed"


async def test_water_is_a_cost_kind_of_the_aggregates_and_the_deletion_preview(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_water(hass, 1000)
    await set_washer(hass, "running")
    await clock.advance(minutes=60)
    await set_water(hass, 1050)
    await set_energy(hass, 101)
    await set_washer(hass, "finished")
    await set_water(hass, 1050)
    await set_energy(hass, 101)

    groups = (await panel.call("coinop/aggregates/get", group_by=["kind"]))["groups"]
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    preview = await panel.call("coinop/runs/delete_preview", run_ids=[summary["id"]])

    assert [(g["kind"], g["cost"], g["water_litres"]) for g in groups] == [
        ("electricity", 0.3, 0),
        ("water", 0.2, pytest.approx(50)),
    ]
    assert (groups[1]["water_cost"], groups[1]["runs"]) == (0.2, 1)
    assert preview["drop"]["water_cost"] == 0.2
    assert preview["drop"]["water_litres"] == pytest.approx(50)


async def test_a_cost_statement_lists_water_in_litres_priced_per_m3(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    await set_water(hass, 1000)
    await add_water_washer(hass)
    await set_water(hass, 1000)
    await set_washer(hass, "running")
    await clock.advance(minutes=60)
    await set_water(hass, 1052.5)
    await set_energy(hass, 101)
    await set_washer(hass, "finished")
    await set_water(hass, 1052.5)
    await set_energy(hass, 101)
    [run] = (await panel.call("coinop/runs/list"))["runs"]

    english = await export(panel, browser, run_ids=[run["id"]])
    german = await export(panel, browser, run_ids=[run["id"]], language="de")

    assert "Water 52.5 L × €4.00/m³ €0.21" in english.lines  # noqa: RUF001
    assert "Wasser 52,5 L × 4,00 €/m³ 0,21 €" in german.lines  # noqa: RUF001


async def test_printers_have_no_water_entities_or_litres(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)
    fired = record_events(hass)

    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_status(hass, "finished")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.kobra_water_in_runs") is None
    assert hass.states.get("sensor.kobra_water_cost") is None
    assert "water_litres" not in fired[-1]
