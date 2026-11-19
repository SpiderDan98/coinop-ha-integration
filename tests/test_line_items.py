"""The user corrects computed Line Items and records Other costs on a Run."""

from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_run_event import record_events
from .test_runs import TOTAL_COST, set_status, stored_runs, value
from .test_sensors import CURRENT, print_runs
from .websocket import PanelClient

ELECTRICITY_COST = "sensor.kobra_electricity_cost"
OTHER_COST = "sensor.kobra_other_cost"


async def printed(hass: HomeAssistant, clock: Clock, panel: PanelClient) -> Any:
    """One final 2 h Run at 100 W and 1 EUR/kWh: 0.2 kWh for 0.20 EUR, followed by
    the Material Line Item to fill in."""
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await print_runs(hass, clock, [2])
    [run] = (await panel.call("wattbill/runs/list"))["runs"]
    return (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]


async def test_overriding_the_amount_back_computes_the_unit_price(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await printed(hass, clock, panel)
    [item, _material] = run["line_items"]

    result = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=item["id"],
        amount=0.5,
    )

    [corrected, _material] = result["run"]["line_items"]
    assert corrected["quantity"] == pytest.approx(0.2)
    assert corrected["unit_price"] == pytest.approx(2.5)
    assert corrected["amount"] == 0.5
    assert corrected["computed"] == {
        "quantity": pytest.approx(0.2),
        "unit_price": 1,
        "amount": 0.2,
    }
    assert result["run"]["total"] == 0.5
    assert value(hass, TOTAL_COST) == pytest.approx(0.5)
    assert value(hass, ELECTRICITY_COST) == pytest.approx(0.5)
    [stored] = stored_runs(hass_storage)
    assert stored["line_items"][0]["amount"] == 0.5
    assert stored["line_items"][0]["computed"]["amount"] == pytest.approx(0.2)


async def update(panel: PanelClient, run: Any, **values: Any) -> Any:
    """Override the Run's first Line Item; the Line Items as the Run now has them."""
    result = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=run["line_items"][0]["id"],
        **values,
    )
    return result["run"]["line_items"]


async def test_reset_restores_the_computed_values(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await printed(hass, clock, panel)
    [computed, _material] = run["line_items"]
    await update(panel, run, quantity=0.5)

    result = await panel.call(
        "wattbill/line_items/reset", run_id=run["id"], line_item_id=computed["id"]
    )

    assert result["run"]["line_items"][0] == computed
    assert computed["computed"] is None
    assert value(hass, TOTAL_COST) == pytest.approx(0.2)
    [stored] = stored_runs(hass_storage)
    assert stored["line_items"][0]["computed"] is None


@pytest.mark.parametrize(
    ("values", "quantity", "unit_price", "amount"),
    [
        ({"quantity": 0.5}, 0.5, 1, 0.5),
        ({"unit_price": 0.3}, 0.2, 0.3, 0.06),
        ({"amount": 0}, 0.2, 0, 0),
        ({"quantity": None, "amount": 0.4}, None, 1, 0.4),
        ({"quantity": 0, "amount": 0.4}, 0, 1, 0.4),
        ({"quantity": 0}, 0, 1, 0),
        ({"quantity": None}, None, 1, 0),
    ],
)
async def test_overrides_keep_amount_quantity_times_unit_price(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    values: dict[str, Any],
    quantity: float | None,
    unit_price: float,
    amount: float,
) -> None:
    """Electricity goes down to 0; without a quantity the amount stands."""
    run = await printed(hass, clock, panel)

    [item, _material] = await update(panel, run, **values)

    assert (item["quantity"], item["unit_price"], item["amount"]) == (
        pytest.approx(quantity),
        pytest.approx(unit_price),
        amount,
    )
    assert value(hass, TOTAL_COST) == pytest.approx(amount)


@pytest.mark.parametrize(
    "values", [{"unit_price": -1}, {"amount": -0.1}, {"quantity": -1}]
)
async def test_electricity_has_no_negative_values(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, values: dict[str, Any]
) -> None:
    run = await printed(hass, clock, panel)
    [item, _material] = run["line_items"]

    error = await panel.error(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=item["id"],
        **values,
    )

    assert error["code"] == "invalid_format"
    assert value(hass, TOTAL_COST) == pytest.approx(0.2)


async def open_run(hass: HomeAssistant, panel: PanelClient) -> Any:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    [run] = (await panel.call("wattbill/runs/list"))["runs"]
    return (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]


async def test_live_values_are_locked_while_the_run_is_open(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await open_run(hass, panel)
    [item] = run["line_items"]
    assert item["locked"] is True

    for command, values in [
        ("wattbill/line_items/update", {"amount": 0}),
        ("wattbill/line_items/reset", {}),
    ]:
        error = await panel.error(
            command, run_id=run["id"], line_item_id=item["id"], **values
        )
        assert error["code"] == "not_allowed", command

    await set_status(hass, "finished")
    final = await panel.call("wattbill/runs/get", run_id=run["id"])
    assert final["run"]["line_items"][0]["locked"] is False


async def add_other(panel: PanelClient, run: Any, **fields: Any) -> Any:
    """Add an Other Line Item; the one added, as the Run now lists it."""
    result = await panel.call(
        "wattbill/line_items/add", run_id=run["id"], kind="other", **fields
    )
    return result["run"]["line_items"][-1]


async def test_other_line_items_are_added_and_edited_while_the_run_is_open(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await open_run(hass, panel)

    inserts = await add_other(
        panel, run, label="Threaded inserts", quantity=8, unit="pcs", unit_price=0.15
    )

    assert {
        key: inserts[key]
        for key in ("kind", "label", "quantity", "unit", "unit_price", "amount")
    } == {
        "kind": "other",
        "label": "Threaded inserts",
        "quantity": 8,
        "unit": "pcs",
        "unit_price": 0.15,
        "amount": 1.2,
    }
    assert (inserts["computed"], inserts["locked"]) == (None, False)
    assert value(hass, OTHER_COST) == pytest.approx(1.2)
    assert value(hass, CURRENT) == pytest.approx(1.2)

    result = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=inserts["id"],
        quantity=10,
    )
    await clock.advance(minutes=30)

    detail = (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]
    assert detail["line_items"][1] == result["run"]["line_items"][1]
    assert detail["subtotals"]["other"] == 1.5
    assert detail["subtotals"]["electricity"] == 0.05
    assert value(hass, OTHER_COST) == pytest.approx(1.5)
    [live] = hass_storage["wattbill.live"]["data"]["runs"]
    assert live["line_items"][1]["label"] == "Threaded inserts"


async def test_other_line_items_record_a_refund(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)

    refund = await add_other(
        panel, run, label="Refund for the failed print", quantity=1, unit_price=-5
    )

    assert (refund["unit"], refund["amount"]) == ("", -5)
    assert value(hass, TOTAL_COST) == pytest.approx(-4.8)
    assert value(hass, OTHER_COST) == pytest.approx(-5)


async def test_other_line_items_are_deleted_electricity_is_not(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await open_run(hass, panel)
    [electricity] = run["line_items"]
    wear = await add_other(panel, run, label="Nozzle wear", unit_price=0.5)
    assert (wear["deletable"], electricity["deletable"]) == (True, False)

    result = await panel.call(
        "wattbill/line_items/delete", run_id=run["id"], line_item_id=wear["id"]
    )

    assert [item["id"] for item in result["run"]["line_items"]] == [electricity["id"]]
    assert value(hass, OTHER_COST) == 0
    await set_status(hass, "finished")
    error = await panel.error(
        "wattbill/line_items/delete", run_id=run["id"], line_item_id=electricity["id"]
    )
    assert error["code"] == "not_allowed"
    final = (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]
    assert final["line_items"][0]["deletable"] is False


async def test_labels_and_units_entered_by_hand_are_kept_verbatim(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)
    wear = await add_other(panel, run, label=" Nozzle wear ", unit="h", unit_price=0.5)
    assert (wear["label"], wear["unit"]) == ("Nozzle wear", "h")

    result = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=wear["id"],
        label="Hotend wear",
        unit="Std.",
    )
    [electricity, _material, renamed] = result["run"]["line_items"]
    assert (renamed["label"], renamed["unit"]) == ("Hotend wear", "Std.")
    assert electricity["label"] is None

    result = await panel.call(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=wear["id"],
        label="",
    )
    assert result["run"]["line_items"][2]["label"] is None
    error = await panel.error(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=electricity["id"],
        unit="Wh",
    )
    assert error["code"] == "not_allowed"


async def test_overrides_survive_a_restart_and_tell_open_panels(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    watcher: PanelClient,
) -> None:
    run = await printed(hass, clock, panel)
    fired = record_events(hass)
    await watcher.subscribe("wattbill/runs/subscribe")
    await watcher.event()

    [overridden, _material] = await update(panel, run, amount=0.5)

    event = await watcher.event()
    assert (event["change"], event["run"]["total"]) == ("updated", 0.5)
    assert fired == []
    [entry] = hass.config_entries.async_entries("wattbill")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restarted = await panel.call("wattbill/runs/get", run_id=run["id"])
    assert restarted["run"]["line_items"][0] == overridden
    assert value(hass, TOTAL_COST) == pytest.approx(0.5)


async def test_an_overridden_value_keeps_the_first_computed_one(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)

    await update(panel, run, quantity=0.5)
    [item, _material] = await update(panel, run, unit_price=2)

    assert (item["quantity"], item["unit_price"], item["amount"]) == (0.5, 2, 1)
    assert item["computed"] == {
        "quantity": pytest.approx(0.2),
        "unit_price": 1,
        "amount": 0.2,
    }


async def test_line_items_that_dont_exist_are_not_found(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)

    for command in ("update", "reset", "delete"):
        for run_id, item_id in [("nope", "x"), (run["id"], "nope")]:
            error = await panel.error(
                f"wattbill/line_items/{command}", run_id=run_id, line_item_id=item_id
            )
            assert error["code"] == "not_found", (command, run_id)
    error = await panel.error("wattbill/line_items/add", run_id="nope", kind="other")
    assert error["code"] == "not_found"
    error = await panel.error(
        "wattbill/line_items/add", run_id=run["id"], kind="electricity"
    )
    assert error["code"] == "invalid_format"
