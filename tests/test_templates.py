"""Line Item Templates: recurring costs one click away, copied into Runs."""

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_hub
from .stored import place_runs, stored_run
from .test_line_items import OTHER_COST, open_run, printed
from .test_persistence import restart
from .test_runs import set_status, value
from .websocket import PanelClient

WEAR = {
    "label": "Wear Kobra",
    "unit": "h",
    "unit_price": 0.15,
    "default_quantity": 1,
    "basis": "running_hours",
}
INSERTS = {
    "label": "Threaded inserts",
    "unit": "pcs",
    "unit_price": 0.08,
    "default_quantity": 8,
    "basis": "entered",
}


def catalogue(hass_storage: dict[str, Any]) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = hass_storage["wattbill.catalog"]["data"][
        "templates"
    ]
    return templates


async def create(panel: PanelClient, **fields: Any) -> dict[str, Any]:
    template: dict[str, Any] = (
        await panel.call("wattbill/templates/create", template=fields)
    )["template"]
    return template


async def test_templates_are_created_edited_and_deleted_in_the_catalogue(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await panel.subscribe("wattbill/catalog/subscribe")
    assert (await panel.event())["templates"] == []

    inserts = await create(panel, **INSERTS | {"label": " Threaded inserts "})
    wear = await create(panel, **WEAR)

    assert inserts == {"id": inserts["id"], **INSERTS}
    assert (await panel.event()) == {"templates": [inserts]}
    assert (await panel.event()) == {"templates": [inserts, wear]}
    updated = await panel.call(
        "wattbill/templates/update",
        template_id=inserts["id"],
        template={"unit_price": 0.1, "default_quantity": 4},
    )
    assert updated["template"] == inserts | {"unit_price": 0.1, "default_quantity": 4}
    await panel.event()
    await panel.call("wattbill/templates/delete", template_id=wear["id"])
    assert (await panel.event()) == {"templates": [updated["template"]]}

    await restart(hass, entry)
    assert catalogue(hass_storage) == [updated["template"]]


async def test_a_template_needs_a_label_and_a_known_basis(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    errors = [
        await panel.error("wattbill/templates/create", template=INSERTS | fields)
        for fields in ({"label": "  "}, {"basis": "per_part"}, {"default_quantity": -1})
    ]
    missing = [
        await panel.error("wattbill/templates/update", template_id="nope", template={}),
        await panel.error("wattbill/templates/delete", template_id="nope"),
    ]

    assert [error["code"] for error in errors] == ["invalid_format"] * 3
    assert [error["code"] for error in missing] == ["not_found"] * 2


async def add_template(
    panel: PanelClient, run_id: str, template: dict[str, Any], **fields: Any
) -> dict[str, Any]:
    """Add the template to the Run; the Line Item added, as the Run now lists it."""
    result = await panel.call(
        "wattbill/line_items/add_template",
        run_id=run_id,
        template_id=template["id"],
        **fields,
    )
    item: dict[str, Any] = result["run"]["line_items"][-1]
    return item


def values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("kind", "label", "quantity", "unit", "unit_price", "amount")
    }


async def test_adding_a_template_copies_its_values_into_an_other_line_item(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)
    inserts = await create(panel, **INSERTS)

    default = await add_template(panel, run["id"], inserts)
    entered = await add_template(panel, run["id"], inserts, quantity=3)

    assert values(default) == {
        "kind": "other",
        "label": "Threaded inserts",
        "quantity": 8,
        "unit": "pcs",
        "unit_price": 0.08,
        "amount": 0.64,
    }
    assert (default["template_id"], default["computed"]) == (inserts["id"], None)
    assert (entered["quantity"], entered["amount"]) == (3, 0.24)
    assert value(hass, OTHER_COST) == pytest.approx(0.88)

    await panel.call(
        "wattbill/templates/update",
        template_id=inserts["id"],
        template={"label": "M4 inserts", "unit_price": 1},
    )
    await panel.call("wattbill/templates/delete", template_id=inserts["id"])
    after = (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]
    assert after["line_items"][1:] == [default, entered]
    assert value(hass, OTHER_COST) == pytest.approx(0.88)


async def test_running_hours_are_the_runs_running_time_without_pauses(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    started = clock.now() - timedelta(hours=5)
    pause = {
        "start": (started + timedelta(hours=1)).isoformat(),
        "end": (started + timedelta(hours=1, minutes=30)).isoformat(),
    }
    place_runs(
        hass_storage, stored_run("vase", started=started, hours=3, pauses=[pause])
    )
    await add_hub(hass)
    wear = await create(panel, **WEAR)

    item = await add_template(panel, "vase", wear, quantity=7)

    assert values(item) | {"basis": item["basis"]} == {
        "kind": "other",
        "label": "Wear Kobra",
        "quantity": 2.5,
        "unit": "h",
        "unit_price": 0.15,
        "amount": 0.38,
        "basis": "running_hours",
    }
    assert (item["locked"], item["deletable"]) == (False, True)
    result = await panel.call(
        "wattbill/line_items/update", run_id="vase", line_item_id=item["id"], quantity=3
    )
    assert result["run"]["line_items"][-1]["computed"]["quantity"] == 2.5
    result = await panel.call(
        "wattbill/line_items/reset", run_id="vase", line_item_id=item["id"]
    )
    assert result["run"]["line_items"][-1] == item


async def wear_of(panel: PanelClient, run_id: str) -> Any:
    run = (await panel.call("wattbill/runs/get", run_id=run_id))["run"]
    [item] = [i for i in run["line_items"] if i["basis"] == "running_hours"]
    return item


async def test_running_hours_update_live_and_freeze_at_run_end(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await open_run(hass, panel)
    wear = await create(panel, **WEAR)
    added = await add_template(panel, run["id"], wear)
    assert (added["quantity"], added["locked"], added["deletable"]) == (0, True, False)

    await clock.advance(minutes=30)
    await set_status(hass, "paused")
    await clock.advance(minutes=30)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    assert (await wear_of(panel, run["id"]))["quantity"] == pytest.approx(1)
    error = await panel.error(
        "wattbill/line_items/update",
        run_id=run["id"],
        line_item_id=added["id"],
        quantity=3,
    )
    assert error["code"] == "not_allowed"

    await set_status(hass, "finished")
    await clock.advance(hours=2)
    frozen = await wear_of(panel, run["id"])
    assert (frozen["quantity"], frozen["amount"], frozen["locked"]) == (
        pytest.approx(1),
        0.15,
        False,
    )
    assert value(hass, OTHER_COST) == pytest.approx(0.15)


async def test_a_template_is_added_only_to_runs_and_from_templates_that_exist(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("vase"))
    await add_hub(hass)
    inserts = await create(panel, **INSERTS)

    errors = [
        await panel.error(
            "wattbill/line_items/add_template", run_id=run_id, template_id=template_id
        )
        for run_id, template_id in (("nope", inserts["id"]), ("vase", "nope"))
    ]

    assert [error["code"] for error in errors] == ["not_found"] * 2
