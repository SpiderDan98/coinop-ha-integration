"""Records what the panel receives, as canned responses for the panel's own tests."""

from collections.abc import Callable
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockUser

from .clock import CLOCK_START, Clock
from .contract import assert_recorded, stable_ids
from .devices import STATUS, add_device, add_hub
from .http import HttpClient
from .images import picture
from .stored import electricity, line_item, place_runs, place_tags, stored_run
from .websocket import PanelClient

DAY = timedelta(days=1)
WEAR = {
    "label": "Wear Kobra",
    "unit": "h",
    "unit_price": 0.15,
    "basis": "running_hours",
}
TEMPLATES = [
    WEAR,
    {
        "label": "Threaded inserts",
        "unit": "pcs",
        "unit_price": 0.08,
        "default_quantity": 8,
        "basis": "entered",
    },
    {"label": "Packaging", "unit_price": 0.5, "basis": "entered"},
]


def image(image_id: str, kind: str, created: datetime) -> dict[str, Any]:
    return {"id": image_id, "kind": kind, "created": created.isoformat()}


def history() -> list[dict[str, Any]]:
    benchy_start = CLOCK_START - 3 * DAY
    helmet_start = CLOCK_START - 2 * DAY
    return [
        stored_run(
            "benchy",
            name="Benchy",
            started=benchy_start,
            hours=1.25,
            part_count=4,
            note="Four on one plate",
            tags=["Gift"],
            images=[
                image("benchy-thumbnail", "thumbnail", benchy_start),
                image("benchy-snapshot", "snapshot", benchy_start + DAY / 19.2),
            ],
            line_items=[
                electricity(0.15, 0.30, benchy_start, benchy_start + DAY / 19.2),
                line_item(
                    "material",
                    0.3125,
                    id="benchy-pla",
                    label="PLA Basic Black",
                    quantity=12.5,
                    unit="g",
                    unit_price=0.025,
                ),
                line_item("other", 0.5, id="benchy-wear", label="Nozzle wear"),
            ],
        ),
        stored_run(
            "helmet",
            name="Helmet",
            started=helmet_start,
            hours=9,
            outcome="failed",
            flags=["fault"],
            tags=["Cosplay helmet", "Gift"],
            images=[image("helmet-snapshot", "snapshot", helmet_start + DAY * 9 / 24)],
            line_items=[
                electricity(0.6, 0.30, helmet_start, helmet_start + DAY / 4)
                | {
                    "quantity": 1.08,
                    "unit_price": 0.3 / 1.08,
                    "amount": 0.3,
                    "segments": [
                        {
                            "start": helmet_start.isoformat(),
                            "end": (helmet_start + DAY / 4).isoformat(),
                            "kwh": 0.6,
                            "unit_price": 0.3,
                        },
                        {
                            "start": (helmet_start + DAY / 4).isoformat(),
                            "end": (helmet_start + DAY * 9 / 24).isoformat(),
                            "kwh": 0.48,
                            "unit_price": 0.25,
                        },
                    ],
                },
            ],
        ),
        stored_run(
            "cancelled",
            name=None,
            device_id="device-mini",
            device_name="Mini",
            started=CLOCK_START - DAY,
            hours=0.5,
            outcome="cancelled",
        ),
    ]


async def test_record_the_runs_the_panel_shows(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    place_tags(hass_storage, "Cosplay helmet", "Gift", "Spare parts")
    entry = await add_hub(hass)
    hass.states.async_set(STATUS, "idle")
    await panel.subscribe("wattbill/runs/subscribe")
    events = [await panel.event()]
    subentry = await add_device(
        hass,
        entry,
        job="sensor.kobra_job",
        running_power=120,
        paused_power=8,
        price=0.30,
    )
    wear = await panel.call("wattbill/templates/create", template=WEAR)
    await panel.call(
        "wattbill/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "tags_for_new_runs": ["Batch 7"],
            "automatic_templates": [wear["template"]["id"]],
        },
    )
    hass.states.async_set(STATUS, "printing")
    await hass.async_block_till_done()
    events.append(await panel.event())
    await clock.advance(minutes=45)
    events.append(await panel.event())
    live_id = events[-1]["run"]["id"]
    ids = {
        live_id: "print-live",
        subentry.subentry_id: "device-kobra",
        wear["template"]["id"]: "template-wear",
    }
    runs = [run["id"] for run in events[0]["runs"]] + [live_id]
    details = [await panel.call("wattbill/runs/get", run_id=run) for run in runs]
    [live_item, live_wear] = details[-1]["run"]["line_items"]
    ids[live_item["id"]] = "print-live-electricity"
    ids[live_wear["id"]] = "print-live-wear"
    hass.states.async_set(STATUS, "finished")
    await hass.async_block_till_done()
    events.append(await panel.event())

    assert [event.get("change") for event in events] == [
        None,
        "started",
        "updated",
        "ended",
    ]
    assert_recorded("runs-subscribe", stable_ids(events, ids))
    assert_recorded("runs-get", stable_ids(details, ids))
    # Mini's Runs stay in the history after it was removed.
    devices = await panel.call("wattbill/devices/list")
    assert_recorded("devices-list", stable_ids(devices, ids))


async def test_record_line_item_corrections(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    await add_hub(hass)

    overridden = await panel.call(
        "wattbill/line_items/update",
        run_id="benchy",
        line_item_id="electricity",
        amount=0.1,
    )
    added = await panel.call(
        "wattbill/line_items/add",
        run_id="helmet",
        kind="other",
        label="Refund for the failed print",
        quantity=1,
        unit_price=-2,
    )

    template = await panel.call(
        "wattbill/line_items/save_as_template",
        run_id="benchy",
        line_item_id="benchy-wear",
    )
    from_template = await panel.call(
        "wattbill/line_items/add_template",
        run_id="benchy",
        template_id=template["template"]["id"],
        quantity=2,
    )

    assert_recorded("line-items-update", overridden)
    refund = added["run"]["line_items"][-1]["id"]
    assert_recorded("line-items-add", stable_ids(added, {refund: "helmet-refund"}))
    copied = from_template["run"]["line_items"][-1]["id"]
    ids = {template["template"]["id"]: "template-nozzle", copied: "benchy-nozzle"}
    assert_recorded("line-items-save-as-template", stable_ids(template, ids))
    assert_recorded("line-items-add-template", stable_ids(from_template, ids))


async def test_record_what_deleting_a_run_drops(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    await add_hub(hass)

    preview = await panel.call("wattbill/runs/delete_preview", run_ids=["helmet"])

    assert_recorded("runs-delete-preview", preview)


async def test_record_what_the_image_commands_answer(
    hass: HomeAssistant,
    clock: Clock,
    files: Path,
    panel: PanelClient,
    http: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    place_runs(hass_storage, *history())
    await add_hub(hass)
    path = "/api/wattbill/runs/benchy/images"

    status, uploaded = await http.upload(path, picture("green"))
    refused = await http.upload(path, *[picture()] * 10)
    [upload] = uploaded["images"]
    cover = await panel.call(
        "wattbill/images/set_cover", run_id="benchy", image_id=upload["id"]
    )
    deleted = await panel.call(
        "wattbill/images/delete", run_id="benchy", image_id=upload["id"]
    )

    assert (status, refused[0]) == (HTTPStatus.OK, HTTPStatus.CONFLICT)
    ids = {upload["id"]: "benchy-upload"}
    assert_recorded("images-upload", stable_ids(uploaded, ids))
    assert_recorded("images-upload-too-many", refused[1])
    assert_recorded("images-set-cover", stable_ids(cover, ids))
    assert_recorded("images-delete", deleted)


async def test_record_the_catalogue_the_panel_shows(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_admin_user: MockUser,
    hass_storage: dict[str, Any],
) -> None:
    place_runs(hass_storage, stored_run("vase"))
    await add_hub(hass)
    types = await panel.call("wattbill/materials/types")
    await panel.subscribe("wattbill/catalog/subscribe")
    events = [await panel.event()]
    fixed = {"source": "fixed", "pack_price": 19.99, "pack_size": 1000}
    created = []
    for material in (
        {
            "name": "eSun PLA+ black",
            "form": "filament",
            "type": "PLA",
            "density": 1.24,
            "vendor": "eSun",
            "colour": "#1a1a1a",
            "default_for_type": True,
            "price": fixed,
        },
        {
            "name": "Standard Resin grey",
            "form": "resin",
            "type": "Standard resin",
            "density": 1.1,
            "colour": "#8a8a8a",
            "price": fixed | {"pack_price": 29.99},
        },
        {
            "name": "PLA red (old brand)",
            "form": "filament",
            "type": "PLA",
            "density": 1.24,
            "price": fixed | {"pack_price": 15.99},
        },
    ):
        result = await panel.call("wattbill/materials/create", material=material)
        created.append(result["material"]["id"])
        await panel.event()
    await panel.call("wattbill/materials/archive", material_id=created[-1])
    tags = ["Cosplay helmet", "Gift", "Spare"]
    await panel.call("wattbill/runs/update", run_id="vase", tags=tags)
    rename = await panel.call("wattbill/tags/rename", tag="Spare", name="Spare parts")
    templates = []
    for fields in TEMPLATES:
        result = await panel.call("wattbill/templates/create", template=fields)
        templates.append(result["template"])
        await panel.event()
    updated = await panel.call(
        "wattbill/templates/update",
        template_id=templates[2]["id"],
        template={"unit_price": 0.6},
    )
    # A panel opened now gets the whole catalogue at once.
    later = connect_panel(hass_admin_user)
    await later.subscribe("wattbill/catalog/subscribe")
    events.append(await later.event())
    ids = {material: f"material-{n}" for n, material in enumerate(created, 1)}
    ids |= {
        template["id"]: f"template-{name}"
        for template, name in zip(
            templates, ("wear", "inserts", "packaging"), strict=True
        )
    }

    assert_recorded("materials-types", types)
    assert_recorded("catalog-subscribe", stable_ids(events, ids))
    assert_recorded("tags-rename", rename)
    assert_recorded("templates-update", stable_ids(updated, ids))
