"""Line Item Templates: recurring costs one click away, copied into Runs."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import Clock
from .devices import add_device, add_hub
from .stored import place_runs, stored_run
from .test_line_items import OTHER_COST, add_other, open_run, printed
from .test_persistence import restart
from .test_runs import set_status, stored_runs, value
from .test_sensors import CURRENT, print_runs
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
    templates: list[dict[str, Any]] = hass_storage["coinop.catalog"]["data"][
        "templates"
    ]
    return templates


async def create(panel: PanelClient, **fields: Any) -> dict[str, Any]:
    template: dict[str, Any] = (
        await panel.call("coinop/templates/create", template=fields)
    )["template"]
    return template


async def test_templates_are_created_edited_and_deleted_in_the_catalogue(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await panel.subscribe("coinop/catalog/subscribe")
    assert (await panel.event())["templates"] == []

    inserts = await create(panel, **INSERTS | {"label": " Threaded inserts "})
    wear = await create(panel, **WEAR)

    assert inserts == {"id": inserts["id"], **INSERTS}
    assert (await panel.event()) == {"templates": [inserts]}
    assert (await panel.event()) == {"templates": [inserts, wear]}
    updated = await panel.call(
        "coinop/templates/update",
        template_id=inserts["id"],
        template={"unit_price": 0.1, "default_quantity": 4},
    )
    assert updated["template"] == inserts | {"unit_price": 0.1, "default_quantity": 4}
    await panel.event()
    await panel.call("coinop/templates/delete", template_id=wear["id"])
    assert (await panel.event()) == {"templates": [updated["template"]]}

    await restart(hass, entry)
    assert catalogue(hass_storage) == [updated["template"]]


async def test_a_template_needs_a_label_and_a_known_basis(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    errors = [
        await panel.error("coinop/templates/create", template=INSERTS | fields)
        for fields in ({"label": "  "}, {"basis": "per_part"}, {"default_quantity": -1})
    ]
    missing = [
        await panel.error("coinop/templates/update", template_id="nope", template={}),
        await panel.error("coinop/templates/delete", template_id="nope"),
    ]

    assert [error["code"] for error in errors] == ["invalid_format"] * 3
    assert [error["code"] for error in missing] == ["not_found"] * 2


async def add_template(
    panel: PanelClient, run_id: str, template: dict[str, Any], **fields: Any
) -> dict[str, Any]:
    """Add the template to the Run; the Line Item added, as the Run now lists it."""
    result = await panel.call(
        "coinop/line_items/add_template",
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
        "coinop/templates/update",
        template_id=inserts["id"],
        template={"label": "M4 inserts", "unit_price": 1},
    )
    await panel.call("coinop/templates/delete", template_id=inserts["id"])
    after = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert after["line_items"][2:] == [default, entered]
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
        "coinop/line_items/update", run_id="vase", line_item_id=item["id"], quantity=3
    )
    assert result["run"]["line_items"][-1]["computed"]["quantity"] == 2.5
    result = await panel.call(
        "coinop/line_items/reset", run_id="vase", line_item_id=item["id"]
    )
    assert result["run"]["line_items"][-1] == item


async def wear_of(panel: PanelClient, run_id: str) -> Any:
    run = (await panel.call("coinop/runs/get", run_id=run_id))["run"]
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
        "coinop/line_items/update",
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


async def save(panel: PanelClient, run: Any, item: Any, **fields: Any) -> Any:
    result = await panel.call(
        "coinop/line_items/save_as_template",
        run_id=run["id"],
        line_item_id=item["id"],
        **fields,
    )
    return {key: value for key, value in result["template"].items() if key != "id"}


async def test_any_line_item_is_saved_as_a_template_with_its_current_values(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    run = await printed(hass, clock, panel)
    [electricity, _material] = run["line_items"]
    labour = await add_other(
        panel, run, label="Labour", quantity=0.5, unit="h", unit_price=15
    )
    await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=labour["id"],
        quantity=0.75,
    )
    flat = await add_other(panel, run, label="Packaging", quantity=None, amount=0.5)
    wear = await add_template(panel, run["id"], await create(panel, **WEAR))

    saved = [
        await save(panel, run, labour),
        await save(panel, run, flat),
        await save(panel, run, wear),
        await save(panel, run, electricity, label="Electricity"),
    ]

    assert saved == [
        {
            "label": "Labour",
            "unit": "h",
            "unit_price": 15,
            "default_quantity": 0.75,
            "basis": "entered",
        },
        {
            "label": "Packaging",
            "unit": "",
            "unit_price": 0.5,
            "default_quantity": 1,
            "basis": "entered",
        },
        WEAR | {"default_quantity": pytest.approx(2)},
        {
            "label": "Electricity",
            "unit": "kWh",
            "unit_price": 1,
            "default_quantity": pytest.approx(0.2),
            "basis": "entered",
        },
    ]
    assert len(catalogue(hass_storage)) == 5


async def test_a_line_item_without_a_label_needs_one_to_be_saved(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    run = await printed(hass, clock, panel)
    [electricity, _material] = run["line_items"]

    errors = [
        await panel.error(
            "coinop/line_items/save_as_template",
            run_id=run["id"],
            line_item_id=electricity["id"],
            **fields,
        )
        for fields in ({}, {"label": " "})
    ]
    missing = await panel.error(
        "coinop/line_items/save_as_template", run_id=run["id"], line_item_id="nope"
    )

    assert [error["code"] for error in errors] == ["invalid_format"] * 2
    assert missing["code"] == "not_found"


async def set_automatic(
    panel: PanelClient, device: ConfigSubentry, *templates: dict[str, Any]
) -> Any:
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=device.subentry_id,
        settings={"automatic_templates": [t["id"] for t in templates]},
    )
    return result["settings"]["automatic_templates"]


def other_items(hass_storage: dict[str, Any]) -> list[list[tuple[Any, ...]]]:
    """Per stored Run: (label, quantity, amount) of its Other Line Items."""
    return [
        [
            (i["label"], round(i["quantity"], 6), round(i["amount"], 6))
            for i in run["line_items"]
            if i["kind"] == "other"
        ]
        for run in stored_runs(hass_storage)
    ]


async def test_automatic_templates_are_added_at_run_start_and_count_live(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, running_power=100, price=1)
    wear = await create(panel, **WEAR)
    inserts = await create(panel, **INSERTS)
    assert await set_automatic(panel, kobra, wear, inserts) == [
        wear["id"],
        inserts["id"],
    ]

    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    started = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert [
        (i["label"], i["quantity"], i["locked"], i["template_id"])
        for i in started["line_items"][1:]
    ] == [
        ("Wear Kobra", 0, True, wear["id"]),
        ("Threaded inserts", 8, False, inserts["id"]),
    ]
    await clock.advance(hours=1)
    assert (await wear_of(panel, run["id"]))["quantity"] == pytest.approx(1)
    assert value(hass, CURRENT) == pytest.approx(0.1 + 0.15 + 0.64)

    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await clock.advance(hours=1)

    assert other_items(hass_storage) == [
        [("Wear Kobra", 2, 0.3), ("Threaded inserts", 8, 0.64)]
    ]


async def test_running_hours_keep_counting_after_a_restart(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, running_power=100, price=1)
    await set_automatic(panel, kobra, await create(panel, **WEAR))
    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await clock.advance(minutes=30)

    await restart(hass, entry)
    await clock.advance(minutes=30)

    wear = await wear_of(panel, run["id"])
    assert (wear["quantity"], wear["locked"]) == (pytest.approx(1), True)


async def test_changing_automatic_templates_affects_only_future_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, running_power=100, price=1)
    wear = await create(panel, **WEAR)
    inserts = await create(panel, **INSERTS)
    await set_automatic(panel, kobra, wear)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await set_automatic(panel, kobra, inserts)
    await panel.call(
        "coinop/templates/update",
        template_id=wear["id"],
        template={"label": "Nozzle", "unit_price": 1},
    )
    await set_status(hass, "finished")
    await print_runs(hass, clock, [1])

    assert other_items(hass_storage) == [
        [("Wear Kobra", 1, 0.15)],
        [("Threaded inserts", 8, 0.64)],
    ]


async def test_a_deleted_template_leaves_every_devices_automatic_templates(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    mini = await add_device(hass, entry, name="Mini", status="sensor.mini_status")
    wear = await create(panel, **WEAR)
    inserts = await create(panel, **INSERTS)
    await set_automatic(panel, kobra, wear, inserts)
    await set_automatic(panel, mini, wear)

    await panel.call("coinop/templates/delete", template_id=wear["id"])

    devices = (await panel.call("coinop/devices/list"))["devices"]
    assert [d["settings"]["automatic_templates"] for d in devices] == [
        [inserts["id"]],
        [],
    ]


async def test_automatic_templates_must_exist(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    wear = await create(panel, **WEAR)

    errors = [
        await panel.error(
            "coinop/devices/update_settings",
            device_id=kobra.subentry_id,
            settings={"automatic_templates": ids},
        )
        for ids in (["nope"], [wear["id"], wear["id"]], wear["id"])
    ]

    assert [error["code"] for error in errors] == [
        "not_found",
        "invalid_format",
        "invalid_format",
    ]


async def test_a_template_is_added_only_to_runs_and_from_templates_that_exist(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("vase"))
    await add_hub(hass)
    inserts = await create(panel, **INSERTS)

    errors = [
        await panel.error(
            "coinop/line_items/add_template", run_id=run_id, template_id=template_id
        )
        for run_id, template_id in (("nope", inserts["id"]), ("vase", "nope"))
    ]

    assert [error["code"] for error in errors] == ["not_found"] * 2


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("coinop/templates/create", {"template": INSERTS}),
        ("coinop/templates/update", {"template_id": "t", "template": {}}),
        ("coinop/templates/delete", {"template_id": "t"}),
        ("coinop/line_items/add_template", {"run_id": "vase", "template_id": "t"}),
        (
            "coinop/line_items/save_as_template",
            {"run_id": "vase", "line_item_id": "electricity", "label": "Power"},
        ),
    ],
)
async def test_only_admins_use_templates(
    hass: HomeAssistant,
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    hass_storage: dict[str, Any],
    command: str,
    data: dict[str, Any],
) -> None:
    place_runs(hass_storage, stored_run("vase"))
    await add_hub(hass)
    user = connect_panel(hass_read_only_user)

    error = await user.error(command, **data)

    assert error["code"] == "unauthorized"
    assert catalogue(hass_storage) == []
