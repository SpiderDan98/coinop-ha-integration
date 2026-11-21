"""Records what the panel receives, as canned responses for the panel's own tests."""

from collections.abc import Callable
from datetime import datetime, timedelta
from http import HTTPStatus
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockUser
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .clock import CLOCK_START, Clock
from .contract import assert_recorded, stable_ids
from .devices import (
    STATUS,
    WASHER_ENERGY,
    WASHER_STATUS,
    WASHER_WATER,
    WATER_PRICE,
    add_device,
    add_hub,
    add_washing_machine,
)
from .http import HttpClient
from .images import picture
from .stored import (
    electricity,
    line_item,
    place_materials,
    place_runs,
    place_tags,
    stored_material,
    stored_run,
)
from .test_ev_chargers import add_charger
from .test_other_devices import add_kiln, add_pump, fire
from .test_other_doses import add_brew_kettle, add_soda_maker, carbonate, dose
from .test_other_images_and_parts import (
    KILN_CAMERA,
    KILN_PREVIEW,
    add_kiln_camera,
    add_kiln_preview,
)
from .test_other_jobs import add_cnc_router, cut
from .test_other_programs import add_bread_maker, bake, set_bread_program
from .test_other_water import add_irrigation, irrigate, set_valve_water
from .test_robotic_mowers import add_mower, mow
from .test_spoolman import (
    add_spoolman_hub,
    filament,
    set_options,
    spool,
    spoolman_down,
)
from .test_washer_profiles import walk_pre_filled
from .washers import add_miele
from .websocket import PanelClient

DAY = timedelta(days=1)
FILAMENT = "sensor.kobra_filament_used"
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


def materials() -> list[dict[str, Any]]:
    fixed = {"source": "fixed", "pack_size": 1000.0, "pack_unit": "g"}
    return [
        stored_material(
            "pla-black", name="PLA Basic Black", price=fixed | {"pack_price": 25.0}
        ),
        stored_material(
            "petg-white",
            name="PETG White",
            type="PETG",
            density=1.27,
            price=fixed | {"pack_price": 30.0},
        ),
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
                    material_id="pla-black",
                    material={
                        "name": "PLA Basic Black",
                        "type": "PLA",
                        "density": 1.24,
                        "diameter": 1.75,
                        "price_per_gram": 0.025,
                    },
                    measured=True,
                    length=4191.0,
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
            flags=["fault", "material_missing"],
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
                line_item(
                    "material",
                    0,
                    id="helmet-filament",
                    measured=True,
                    length=30000.0,
                    quantity=None,
                    unit="g",
                    unit_price=0,
                ),
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
    place_materials(hass_storage, *materials())
    entry = await add_hub(hass)
    hass.states.async_set(STATUS, "idle")
    used = {"unit_of_measurement": "mm"}
    hass.states.async_set(FILAMENT, "0", used)
    await panel.subscribe("coinop/runs/subscribe")
    events = [await panel.event()]
    subentry = await add_device(
        hass,
        entry,
        job="sensor.kobra_job",
        material=FILAMENT,
        running_power=120,
        paused_power=8,
        price=0.30,
    )
    wear = await panel.call("coinop/templates/create", template=WEAR)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "tags_for_new_runs": ["Batch 7"],
            "automatic_templates": [wear["template"]["id"]],
            "default_material": "pla-black",
        },
    )
    hass.states.async_set(STATUS, "printing")
    await hass.async_block_till_done()
    events.append(await panel.event())
    hass.states.async_set(FILAMENT, "1500", used)
    await hass.async_block_till_done()
    await panel.event()
    await clock.advance(minutes=45)
    events.append(await panel.event())
    live_id = events[-1]["run"]["id"]
    ids = {
        live_id: "print-live",
        subentry.subentry_id: "device-kobra",
        wear["template"]["id"]: "template-wear",
    }
    runs = [run["id"] for run in events[0]["runs"]] + [live_id]
    details = [await panel.call("coinop/runs/get", run_id=run) for run in runs]
    [live_item, live_material, live_wear] = details[-1]["run"]["line_items"]
    ids[live_item["id"]] = "print-live-electricity"
    ids[live_material["id"]] = "print-live-material"
    ids[live_wear["id"]] = "print-live-wear"
    hass.states.async_set(STATUS, "finished")
    await hass.async_block_till_done()
    await panel.event()
    hass.states.async_set(FILAMENT, "1600", used)
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
    devices = await panel.call("coinop/devices/list")
    assert_recorded("devices-list", stable_ids(devices, ids))


async def test_record_line_item_corrections(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    place_materials(hass_storage, *materials())
    await add_hub(hass)

    overridden = await panel.call(
        "coinop/line_items/update",
        run_id="benchy",
        line_item_id="electricity",
        amount=0.1,
    )
    added = await panel.call(
        "coinop/line_items/add",
        run_id="helmet",
        kind="other",
        label="Refund for the failed print",
        quantity=1,
        unit_price=-2,
    )

    template = await panel.call(
        "coinop/line_items/save_as_template",
        run_id="benchy",
        line_item_id="benchy-wear",
    )
    from_template = await panel.call(
        "coinop/line_items/add_template",
        run_id="benchy",
        template_id=template["template"]["id"],
        quantity=2,
    )
    picked = await panel.call(
        "coinop/line_items/update",
        run_id="helmet",
        line_item_id="helmet-filament",
        material_id="petg-white",
    )
    added_material = await panel.call(
        "coinop/line_items/add",
        run_id="benchy",
        kind="material",
        material_id="petg-white",
        quantity=3,
        unit="g",
    )

    assert_recorded("line-items-update", overridden)
    refund = added["run"]["line_items"][-1]["id"]
    assert_recorded("line-items-add", stable_ids(added, {refund: "helmet-refund"}))
    copied = from_template["run"]["line_items"][-1]["id"]
    ids = {template["template"]["id"]: "template-nozzle", copied: "benchy-nozzle"}
    assert_recorded("line-items-save-as-template", stable_ids(template, ids))
    assert_recorded("line-items-add-template", stable_ids(from_template, ids))
    assert_recorded(
        "line-items-material", stable_ids(picked, {refund: "helmet-refund"})
    )
    petg = added_material["run"]["line_items"][-1]["id"]
    assert_recorded(
        "line-items-add-material",
        stable_ids(added_material, ids | {petg: "benchy-petg"}),
    )


async def test_record_a_manual_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, running_power=120, price=0.30)

    created = await panel.call(
        "coinop/runs/create",
        device_id=subentry.subentry_id,
        name="Bracket",
        started=(CLOCK_START - DAY / 4).isoformat(),
        ended=(CLOCK_START - DAY / 6).isoformat(),
        outcome="completed",
        tags=["Batch 7"],
    )

    [power, material] = created["run"]["line_items"]
    ids = {
        created["run"]["id"]: "manual",
        power["id"]: "manual-electricity",
        material["id"]: "manual-material",
        subentry.subentry_id: "device-kobra",
    }
    assert_recorded("runs-create", stable_ids(created, ids))


async def test_record_a_washing_machine_and_its_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    laundry = {"form": "detergent", "diameter": None}
    place_materials(
        hass_storage,
        stored_material(
            "material-detergent",
            name="Liquid detergent",
            type="Liquid detergent",
            density=1.04,
            price={
                "source": "fixed",
                "pack_price": 7.8,
                "pack_size": 1500.0,
                "pack_unit": "ml",
            },
            **laundry,
        ),
        stored_material(
            "material-pods",
            name="Colour pods",
            type="Detergent pods",
            density=None,
            price={
                "source": "fixed",
                "pack_price": 12.0,
                "pack_size": 40.0,
                "pack_unit": "pcs",
            },
            **laundry,
        ),
    )
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set(
        "sensor.washer_program",
        "Cotton 60°",
        {"options": ["Cotton 60°", "Wool", "Eco 40-60"]},
    )
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": "sensor.washer_program"},
        price=0.30,
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "doses": [
                {"id": "dose-detergent", "material_id": "material-detergent"},
                {"id": "dose-pods", "material_id": "material-pods"},
            ],
            "program_defaults": {
                "default": {"doses": {"dose-detergent": 75}},
                "programs": {"Wool": {"doses": {"dose-detergent": 40}}},
            },
        },
    )
    hass.states.async_set(WASHER_STATUS, "running")
    await clock.advance(minutes=90)
    hass.states.async_set(WASHER_ENERGY, "101.2", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_STATUS, "finished")
    await hass.async_block_till_done()
    # Weighed only from the next Run on, so the recorded one keeps its Default row.
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "doses": [
                {
                    "id": "dose-detergent",
                    "material_id": "material-detergent",
                    "stock": {"entity_id": "sensor.detergent_scale"},
                },
                {"id": "dose-pods", "material_id": "material-pods"},
            ]
        },
    )

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])
    suggestions = await panel.call(
        "coinop/devices/measured_suggestions", device_id=subentry.subentry_id
    )

    [electricity, detergent] = detail["run"]["line_items"]
    ids = {
        subentry.subentry_id: "device-washer",
        run["id"]: "wash",
        electricity["id"]: "wash-electricity",
        detergent["id"]: "wash-detergent",
    }
    assert_recorded("devices-list-washing-machine", stable_ids(devices, ids))
    assert_recorded("runs-get-washing-machine", stable_ids(detail, ids))
    assert_recorded("devices-measured-suggestions", suggestions)


async def test_record_water_on_washing_machine_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """Measured water across a price change, and water added by hand without a source."""
    hass.config.currency = "EUR"
    litres = {"unit_of_measurement": "L"}
    per_m3 = {"unit_of_measurement": "EUR/m³"}
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_WATER, "1000", litres)
    hass.states.async_set(WATER_PRICE, "4", per_m3)
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set("sensor.dryer_status", "off")
    entry = await add_hub(hass)
    metered = await add_washing_machine(
        hass, entry, water="meter", water_price={"entity_id": WATER_PRICE}
    )
    unmetered = await add_washing_machine(
        hass, entry, name="Basement", status="sensor.dryer_status"
    )
    hass.states.async_set(WASHER_WATER, "1000", litres, force_update=True)
    hass.states.async_set(WASHER_STATUS, "running")
    hass.states.async_set("sensor.dryer_status", "running")
    await clock.advance(minutes=30)
    hass.states.async_set(WASHER_WATER, "1020", litres)
    hass.states.async_set(WATER_PRICE, "5", per_m3)
    await clock.advance(minutes=30)
    hass.states.async_set(WASHER_WATER, "1050", litres)
    hass.states.async_set(WASHER_STATUS, "finished")
    hass.states.async_set("sensor.dryer_status", "finished")
    await clock.advance(minutes=5)

    runs = (await panel.call("coinop/runs/list"))["runs"]
    [wash] = [run for run in runs if run["device_id"] == metered.subentry_id]
    [other] = [run for run in runs if run["device_id"] == unmetered.subentry_id]
    detail = await panel.call("coinop/runs/get", run_id=wash["id"])
    added = await panel.call(
        "coinop/line_items/add",
        run_id=other["id"],
        kind="water",
        quantity=60,
        unit_price=0.0045,
    )

    ids = {
        metered.subentry_id: "device-washer",
        unmetered.subentry_id: "device-basement",
        wash["id"]: "water-wash",
        other["id"]: "basement-wash",
        **{
            item["id"]: f"water-wash-{item['kind']}"
            for item in detail["run"]["line_items"]
        },
        **{
            item["id"]: f"basement-wash-{item['kind']}"
            for item in added["run"]["line_items"]
        },
    }
    assert_recorded("runs-get-water", stable_ids(detail, ids))
    assert_recorded("line-items-add-water", stable_ids(added, ids))


async def test_record_electricity_and_water_per_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A washing machine without meters: a "Wool" Run priced from its Program's row."""
    hass.config.currency = "EUR"
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set("sensor.washer_program", "Wool", {"options": ["Wool"]})
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": "sensor.washer_program"},
        source="per_program",
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "program_defaults": {
                "default": {"doses": {}, "kwh": 0.9, "litres": 50},
                "programs": {"Wool": {"doses": {}, "kwh": 0.4, "litres": 45}},
            }
        },
    )
    hass.states.async_set(WASHER_STATUS, "running")
    await clock.advance(minutes=40)
    hass.states.async_set(WASHER_STATUS, "finished")
    await hass.async_block_till_done()

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    ids = {
        subentry.subentry_id: "device-washer",
        run["id"]: "wool",
        **{item["id"]: f"wool-{item['kind']}" for item in detail["run"]["line_items"]},
    }
    assert_recorded("devices-list-per-program", stable_ids(devices, ids))
    assert_recorded("runs-get-per-program", stable_ids(detail, ids))


async def test_record_a_device_with_electricity_source_none(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A washing machine whose electricity isn't followed, with the kWh it had in its
    Program Defaults before: a "Wool" Run with water alone, and electricity added to
    it by hand."""
    hass.config.currency = "EUR"
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set("sensor.washer_program", "Wool", {"options": ["Wool"]})
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": "sensor.washer_program"},
        source="none",
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "program_defaults": {
                "default": {"doses": {}, "kwh": 0.9, "litres": 50},
                "programs": {"Wool": {"doses": {}, "kwh": 0.4, "litres": 45}},
            }
        },
    )
    hass.states.async_set(WASHER_STATUS, "running")
    await clock.advance(minutes=40)
    hass.states.async_set(WASHER_STATUS, "finished")
    await hass.async_block_till_done()

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])
    added = await panel.call(
        "coinop/line_items/add",
        run_id=run["id"],
        kind="electricity",
        quantity=0.4,
        unit_price=0.3,
    )

    ids = {
        subentry.subentry_id: "device-washer",
        run["id"]: "unpowered",
        **{
            item["id"]: f"unpowered-{item['kind']}"
            for item in added["run"]["line_items"]
        },
    }
    assert_recorded("devices-list-electricity-none", stable_ids(devices, ids))
    assert_recorded("runs-get-electricity-none", stable_ids(detail, ids))
    assert_recorded("line-items-add-electricity", stable_ids(added, ids))


async def test_record_an_other_device_with_water_and_a_watering(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A garden valve under the Type Name "Irrigation": an Other Device that has water,
    on a water meter and with the electricity source none; and a watering of 120 L."""
    await set_valve_water(hass, 1000)
    valve = await add_irrigation(hass)
    await irrigate(hass, clock, start=1000, litres=120)

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    [water] = detail["run"]["line_items"]
    ids = {
        valve.subentry_id: "device-garden-valve",
        run["id"]: "watering",
        water["id"]: "watering-water",
    }
    assert_recorded("devices-list-other-water", stable_ids(devices, ids))
    assert_recorded("runs-get-other-water", stable_ids(detail, ids))


async def test_record_a_dishwasher(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A Dishwasher on an energy meter with water per Program and tabs as its Dose."""
    place_materials(
        hass_storage,
        stored_material(
            "material-tabs",
            name="All-in-one tabs",
            form="dishwasher_product",
            type="Dishwasher tabs",
            density=None,
            diameter=None,
            price={
                "source": "fixed",
                "pack_price": 9.0,
                "pack_size": 60.0,
                "pack_unit": "pcs",
            },
        ),
    )
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set(
        "sensor.washer_program", "Eco 50°", {"options": ["Eco 50°", "Intensive 70°"]}
    )
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        name="Dishwasher",
        device_type="dishwasher",
        program={"entity_id": "sensor.washer_program"},
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "doses": [{"id": "dose-tabs", "material_id": "material-tabs"}],
            "program_defaults": {
                "default": {"doses": {"dose-tabs": 1}, "litres": 14},
                "programs": {"Eco 50°": {"doses": {"dose-tabs": 1}, "litres": 9.5}},
            },
        },
    )

    devices = await panel.call("coinop/devices/list")

    assert_recorded(
        "devices-list-dishwasher",
        stable_ids(devices, {subentry.subentry_id: "device-dishwasher"}),
    )


async def test_record_a_tumble_dryer(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A Tumble dryer on an energy meter with dryer sheets as its Dose."""
    place_materials(
        hass_storage,
        stored_material(
            "material-sheets",
            name="Dryer sheets",
            form="laundry_additive",
            type="Dryer sheets",
            density=None,
            diameter=None,
            price={
                "source": "fixed",
                "pack_price": 4.0,
                "pack_size": 80.0,
                "pack_unit": "pcs",
            },
        ),
    )
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set(
        "sensor.washer_program",
        "Cupboard dry",
        {"options": ["Cupboard dry", "Iron dry"]},
    )
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        name="Tumble dryer",
        device_type="tumble_dryer",
        program={"entity_id": "sensor.washer_program"},
        water=None,
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "doses": [{"id": "dose-sheets", "material_id": "material-sheets"}],
            "program_defaults": {
                "default": {"doses": {"dose-sheets": 1}, "kwh": 2.0},
                "programs": {"Cupboard dry": {"doses": {"dose-sheets": 2}, "kwh": 2.4}},
            },
        },
    )

    devices = await panel.call("coinop/devices/list")

    assert_recorded(
        "devices-list-tumble-dryer",
        stable_ids(devices, {subentry.subentry_id: "device-dryer"}),
    )


async def test_record_a_tumble_dryer_added_from_a_miele_washing_machine(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    """A Tumble dryer set up manually from a Miele washing machine's HA device,
    whose profile finds a water meter too."""
    washer = add_miele(hass)
    entry = await add_hub(hass)
    _, subentry = await walk_pre_filled(
        hass, entry, washer, "tumble_dryer", name={"name": "Dryer"}
    )

    devices = await panel.call("coinop/devices/list")

    assert_recorded(
        "devices-list-tumble-dryer-from-miele",
        stable_ids(
            devices,
            {
                subentry.subentry_id: "device-dryer",
                washer.device.id: "ha-device-washer",
            },
        ),
    )


async def test_record_a_coffee_machine_and_its_espresso(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A Coffee machine with electricity and water per Program and beans as its Dose."""
    hass.config.currency = "EUR"
    place_materials(
        hass_storage,
        stored_material(
            "material-beans",
            name="Espresso beans",
            form="beverage_ingredient",
            type="Coffee beans",
            density=0.4,
            diameter=None,
            price={
                "source": "fixed",
                "pack_price": 16.0,
                "pack_size": 1000.0,
                "pack_unit": "g",
            },
        ),
    )
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set(
        "sensor.washer_program", "Espresso", {"options": ["Espresso", "Cappuccino"]}
    )
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        name="Coffee machine",
        device_type="coffee_machine",
        program={"entity_id": "sensor.washer_program"},
        source="per_program",
        water="per_program",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "doses": [{"id": "dose-beans", "material_id": "material-beans"}],
            "program_defaults": {
                "default": {"doses": {"dose-beans": 8}, "kwh": 0.02, "litres": 0.125},
                "programs": {
                    "Espresso": {
                        "doses": {"dose-beans": 8},
                        "kwh": 0.012,
                        "litres": 0.04,
                    },
                },
            },
        },
    )
    hass.states.async_set(WASHER_STATUS, "running")
    await clock.advance(seconds=40)
    hass.states.async_set(WASHER_STATUS, "finished")
    await hass.async_block_till_done()

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    ids = {
        subentry.subentry_id: "device-coffee-machine",
        run["id"]: "espresso",
        **{
            item["id"]: f"espresso-{item['kind']}"
            for item in detail["run"]["line_items"]
        },
    }
    assert_recorded("devices-list-coffee-machine", stable_ids(devices, ids))
    assert_recorded("runs-get-coffee-machine", stable_ids(detail, ids))


async def test_record_measured_suggestions_of_under_a_litre(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """Two measured Runs without a Program of 0.04 and 0.05 L, 0.012 kWh each."""

    def report(kwh: float, litres: float) -> None:
        for meter, reading, unit in (
            (WASHER_ENERGY, kwh, "kWh"),
            (WASHER_WATER, litres, "L"),
        ):
            hass.states.async_set(
                meter, str(reading), {"unit_of_measurement": unit}, force_update=True
            )

    readings = [(100, 1000), (100.012, 1000.04), (100.024, 1000.09)]
    report(*readings[0])
    hass.states.async_set(WASHER_STATUS, "off")
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        name="Coffee machine",
        device_type="coffee_machine",
        water="meter",
    )
    for start, end in pairwise(readings):
        hass.states.async_set(WASHER_STATUS, "running")
        # Reported at the start, so the meters aren't interpolated from the last Run's end.
        report(*start)
        await clock.advance(seconds=40)
        report(*end)
        hass.states.async_set(WASHER_STATUS, "finished")
        await clock.advance(minutes=10)

    suggestions = await panel.call(
        "coinop/devices/measured_suggestions", device_id=subentry.subentry_id
    )

    assert_recorded("devices-measured-suggestions-small", suggestions)


async def test_record_an_oven(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """An Oven on an energy meter, a Device with a Program and no Doses, after a
    measured "Fan plus 180°" Run."""
    hass.config.currency = "EUR"
    kwh = {"unit_of_measurement": "kWh"}
    hass.states.async_set(WASHER_ENERGY, "100", kwh)
    hass.states.async_set(WASHER_STATUS, "off")
    hass.states.async_set(
        "sensor.washer_program",
        "Fan plus 180°",
        {"options": ["Fan plus 180°", "Conventional heat"]},
    )
    subentry = await add_washing_machine(
        hass,
        await add_hub(hass),
        name="Oven",
        device_type="oven",
        program={"entity_id": "sensor.washer_program"},
        water=None,
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={
            "program_defaults": {
                "default": {"doses": {}, "kwh": 1.0},
                "programs": {"Fan plus 180°": {"doses": {}, "kwh": 1.6}},
            }
        },
    )
    hass.states.async_set(WASHER_STATUS, "running")
    await clock.advance(minutes=50)
    hass.states.async_set(WASHER_ENERGY, "101.4", kwh)
    hass.states.async_set(WASHER_STATUS, "finished")
    await hass.async_block_till_done()
    hass.states.async_set(WASHER_ENERGY, "101.4", kwh, force_update=True)
    await hass.async_block_till_done()

    devices = await panel.call("coinop/devices/list")
    suggestions = await panel.call(
        "coinop/devices/measured_suggestions", device_id=subentry.subentry_id
    )

    assert_recorded(
        "devices-list-oven", stable_ids(devices, {subentry.subentry_id: "device-oven"})
    )
    assert_recorded("devices-measured-suggestions-oven", suggestions)


async def test_record_what_deleting_a_run_drops(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    await add_hub(hass)

    preview = await panel.call("coinop/runs/delete_preview", run_ids=["helmet"])

    assert_recorded("runs-delete-preview", preview)


PANEL_GROUPINGS = [
    [],
    ["month"],
    ["month", "kind"],
    ["outcome"],
    ["kind", "material"],
    ["kind"],
    ["device"],
    ["tag"],
]


async def test_record_the_aggregates_of_overview_and_analysis(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    place_materials(hass_storage, *materials())
    await add_hub(hass)

    answers = [
        {"group_by": group_by}
        | await panel.call("coinop/aggregates/get", group_by=group_by)
        for group_by in PANEL_GROUPINGS
    ]
    # The totals of each selection of Runs: gallery, basket, failed + cancelled.
    ids = sorted(run["id"] for run in history())
    answers += [
        {"group_by": [], "run_ids": list(run_ids)}
        | await panel.call("coinop/aggregates/get", run_ids=list(run_ids))
        for count in range(1, len(ids) + 1)
        for run_ids in combinations(ids, count)
    ]

    assert_recorded("aggregates-get", answers)


async def test_record_washing_machine_runs_by_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    washer: dict[str, Any] = {
        "device_id": "device-washer",
        "device_name": "Washer",
        "part_count": None,
    }
    started = CLOCK_START - DAY
    place_runs(
        hass_storage,
        stored_run("vase", name="Vase"),
        stored_run("monday", **washer, name="Cotton 60°", program="Cotton 60°"),
        stored_run(
            "tuesday",
            **washer,
            name="Cotton 60°",
            program="Cotton 60°",
            started=started + timedelta(hours=3),
            line_items=[
                electricity(0.24, 0.30, started, started + timedelta(hours=2)),
                line_item("other", 0.5, id="tuesday-rinse", label="Extra rinse"),
            ],
        ),
        stored_run("eco", **washer, name="Eco 40-60", program="Eco 40-60"),
        stored_run("unknown", **washer, name=None),
    )
    await add_hub(hass)

    runs = await panel.call("coinop/runs/list")
    run_ids = ["eco", "monday", "tuesday", "unknown"]
    by_program = {"group_by": ["program"], "run_ids": run_ids} | await panel.call(
        "coinop/aggregates/get", group_by=["program"], run_ids=run_ids
    )

    assert_recorded("aggregates-by-program", runs | {"aggregates": [by_program]})


async def test_record_a_robotic_mower_and_its_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A robotic mower, the Device Type without any Capability, and a mowing Run that
    was paused while the mower charged."""
    mower = await add_mower(hass)
    await mow(hass, clock)

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    [electricity] = detail["run"]["line_items"]
    ids = {
        mower.subentry_id: "device-mower",
        run["id"]: "mowing",
        electricity["id"]: "mowing-electricity",
    }
    assert_recorded("devices-list-robotic-mower", stable_ids(devices, ids))
    assert_recorded("runs-get-robotic-mower", stable_ids(detail, ids))


async def test_record_an_ev_charger(hass: HomeAssistant, panel: PanelClient) -> None:
    """An EV charger on its session energy sensor."""
    charger = await add_charger(hass)

    devices = await panel.call("coinop/devices/list")

    assert_recorded(
        "devices-list-ev-charger",
        stable_ids(devices, {charger.subentry_id: "device-wallbox"}),
    )


async def test_record_other_devices_and_a_firing(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """Other Devices under two Type Names: a kiln ("Kiln") that has nothing and
    estimates its electricity, and a pool pump and a pond pump (both "Pump") whose
    meters count each Run from 0; and a firing of the kiln."""
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry)
    pool = await add_pump(hass, entry)
    pond = await add_pump(
        hass, entry, name="Pond pump", status="sensor.pond_pump_status"
    )
    await fire(hass, clock)

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    [electricity] = detail["run"]["line_items"]
    ids = {
        kiln.subentry_id: "device-kiln",
        pool.subentry_id: "device-pool-pump",
        pond.subentry_id: "device-pond-pump",
        run["id"]: "firing",
        electricity["id"]: "firing-electricity",
    }
    assert_recorded("devices-list-other", stable_ids(devices, ids))
    assert_recorded("runs-get-other", stable_ids(detail, ids))


async def test_record_an_other_device_with_images_and_a_part_count(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    """A studio kiln ("Kiln") that has images and a Part Count and no job, and its
    firing "Mugs" of 9 parts with its Thumbnail and its Snapshot."""
    await add_kiln_preview(hass, picture("red"))
    await add_kiln_camera(hass, picture("blue"))
    kiln = await add_kiln(
        hass,
        name="Studio kiln",
        has=["images", "part_count"],
        thumbnail=KILN_PREVIEW,
        camera=KILN_CAMERA,
    )
    await fire(hass, clock)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], name="Mugs", part_count=9)

    devices = await panel.call("coinop/devices/list")
    detail = await panel.call("coinop/runs/get", run_id=run["id"])

    [electricity] = detail["run"]["line_items"]
    thumbnail, snapshot = detail["run"]["images"]
    assert (thumbnail["kind"], snapshot["kind"]) == ("thumbnail", "snapshot")
    ids = {
        kiln.subentry_id: "device-studio-kiln",
        run["id"]: "mugs",
        electricity["id"]: "mugs-electricity",
        thumbnail["id"]: "mugs-thumbnail",
        snapshot["id"]: "mugs-snapshot",
    }
    assert_recorded("devices-list-other-images", stable_ids(devices, ids))
    assert_recorded("runs-get-other-images", stable_ids(detail, ids))


async def test_record_an_other_device_with_a_program_and_its_loaves(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    """A bread maker ("Bread maker"): an Other Device with a Program and no Doses,
    its electricity per Program, after a loaf without a Program and a "Whole wheat"
    one; its Program input also knows "Basic"."""
    bread_maker = await add_bread_maker(hass, panel)
    await bake(hass, clock)
    await clock.advance(hours=1)
    await bake(hass, clock, "Whole wheat")
    await set_bread_program(hass, "unknown", {"options": ["Basic", "Whole wheat"]})

    devices = await panel.call("coinop/devices/list")
    runs = await panel.call("coinop/runs/list")
    [plain] = [run for run in runs["runs"] if run["program"] is None]
    [wheat] = [run for run in runs["runs"] if run["program"] == "Whole wheat"]
    detail = await panel.call("coinop/runs/get", run_id=wheat["id"])
    by_program = await panel.call(
        "coinop/aggregates/get",
        group_by=["program"],
        run_ids=[plain["id"], wheat["id"]],
    )

    [electricity] = detail["run"]["line_items"]
    ids = {
        bread_maker.subentry_id: "device-bread-maker",
        plain["id"]: "plain-loaf",
        wheat["id"]: "wheat-loaf",
        electricity["id"]: "wheat-loaf-electricity",
    }
    asked = {"group_by": ["program"], "run_ids": ["plain-loaf", "wheat-loaf"]}
    assert_recorded("devices-list-other-program", stable_ids(devices, ids))
    assert_recorded("runs-get-other-program", stable_ids(detail, ids))
    assert_recorded(
        "aggregates-other-program",
        stable_ids(runs | {"aggregates": [asked | by_program]}, ids),
    )


async def test_record_an_other_device_with_doses_and_no_program_and_a_bottle(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A soda maker ("Soda maker"): an Other Device with Doses and no Program, dosing
    8 g of "co2" and 40 ml of "syrup" in its Default row, with the electricity source
    none, and a bottle it carbonated. The catalogue holds the Materials of its Doses
    and of the brew kettle's below."""
    soda_maker = await add_soda_maker(hass, hass_storage)
    await dose(panel, soda_maker, {"dose-co2": 8, "dose-syrup": 40})
    await carbonate(hass, clock)

    devices = await panel.call("coinop/devices/list")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = await panel.call("coinop/runs/get", run_id=run["id"])
    await panel.subscribe("coinop/catalog/subscribe")
    catalogue = await panel.event()

    co2, syrup = detail["run"]["line_items"]
    ids = {
        soda_maker.subentry_id: "device-soda-maker",
        run["id"]: "bottle",
        co2["id"]: "bottle-co2",
        syrup["id"]: "bottle-syrup",
    }
    assert_recorded("devices-list-other-doses", stable_ids(devices, ids))
    assert_recorded("runs-get-other-doses", stable_ids(detail, ids))
    assert_recorded("catalog-subscribe-other-doses", catalogue)


async def test_record_an_other_device_with_a_program_doses_and_water(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A brew kettle ("Brew kettle"): an Other Device with a Program, Doses and water,
    its electricity and its water per Program, dosing "malt" and "hops"."""
    brew_kettle = await add_brew_kettle(hass, panel, hass_storage)

    devices = await panel.call("coinop/devices/list")

    assert_recorded(
        "devices-list-other-program-doses",
        stable_ids(devices, {brew_kettle.subentry_id: "device-brew-kettle"}),
    )


async def test_record_an_other_device_with_job_and_material_and_its_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A CNC router ("CNC router"): an Other Device with Job and Material, Images and
    a Part Count, with its job name and Material used inputs, no image input and the
    default Material "mdf", and its Run "Sign Oak" of 3 parts that used 120 g. The
    catalogue holds "mdf" (by g) and "plywood" (by piece)."""
    router = await add_cnc_router(
        hass, panel, hass_storage, has=["job", "images", "part_count"]
    )
    await cut(hass, clock, "Sign_Oak.gcode", grams=120)
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await panel.call("coinop/runs/update", run_id=run["id"], part_count=3)

    devices = await panel.call("coinop/devices/list")
    detail = await panel.call("coinop/runs/get", run_id=run["id"])
    await panel.subscribe("coinop/catalog/subscribe")
    catalogue = await panel.event()

    electricity, material = detail["run"]["line_items"]
    ids = {
        router.subentry_id: "device-cnc-router",
        run["id"]: "sign",
        electricity["id"]: "sign-electricity",
        material["id"]: "sign-material",
    }
    assert_recorded("devices-list-other-job", stable_ids(devices, ids))
    assert_recorded("runs-get-other-job", stable_ids(detail, ids))
    assert_recorded("catalog-subscribe-other-job", catalogue)


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
    path = "/api/coinop/runs/benchy/images"

    status, uploaded = await http.upload(path, picture("green"))
    refused = await http.upload(path, *[picture()] * 10)
    [upload] = uploaded["images"]
    cover = await panel.call(
        "coinop/images/set_cover", run_id="benchy", image_id=upload["id"]
    )
    deleted = await panel.call(
        "coinop/images/delete", run_id="benchy", image_id=upload["id"]
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
    types = await panel.call("coinop/materials/types")
    await panel.subscribe("coinop/catalog/subscribe")
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
        result = await panel.call("coinop/materials/create", material=material)
        created.append(result["material"]["id"])
        await panel.event()
    await panel.call("coinop/materials/archive", material_id=created[-1])
    tags = ["Cosplay helmet", "Gift", "Spare"]
    await panel.call("coinop/runs/update", run_id="vase", tags=tags)
    rename = await panel.call("coinop/tags/rename", tag="Spare", name="Spare parts")
    templates = []
    for fields in TEMPLATES:
        result = await panel.call("coinop/templates/create", template=fields)
        templates.append(result["template"])
        await panel.event()
    updated = await panel.call(
        "coinop/templates/update",
        template_id=templates[2]["id"],
        template={"unit_price": 0.6},
    )
    # A panel opened now gets the whole catalogue at once.
    later = connect_panel(hass_admin_user)
    await later.subscribe("coinop/catalog/subscribe")
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


async def test_record_laundry_materials(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    created = []
    for name, material in (
        (
            "detergent",
            {
                "name": "Liquid detergent",
                "form": "detergent",
                "type": "Liquid detergent",
                "density": 1.04,
                "price": {
                    "source": "fixed",
                    "pack_price": 7.8,
                    "pack_size": 1500,
                    "pack_unit": "ml",
                },
            },
        ),
        (
            "pods",
            {
                "name": "Colour pods",
                "form": "detergent",
                "type": "Detergent pods",
                "price": {
                    "source": "fixed",
                    "pack_price": 12,
                    "pack_size": 40,
                    "pack_unit": "pcs",
                },
            },
        ),
    ):
        result = await panel.call("coinop/materials/create", material=material)
        created.append((result["material"], f"material-{name}"))

    assert_recorded(
        "materials-create-laundry",
        stable_ids(
            [material for material, _ in created],
            {material["id"]: fixed for material, fixed in created},
        ),
    )


async def test_record_dishwasher_and_beverage_materials(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)
    created = []
    for name, material in (
        (
            "tabs",
            {
                "name": "All-in-one tabs",
                "form": "dishwasher_product",
                "type": "Dishwasher tabs",
                "price": {
                    "source": "fixed",
                    "pack_price": 9,
                    "pack_size": 60,
                    "pack_unit": "pcs",
                },
            },
        ),
        (
            "beans",
            {
                "name": "Espresso beans",
                "form": "beverage_ingredient",
                "type": "Coffee beans",
                "density": 0.4,
                "price": {
                    "source": "fixed",
                    "pack_price": 16,
                    "pack_size": 1000,
                    "pack_unit": "g",
                },
            },
        ),
    ):
        result = await panel.call("coinop/materials/create", material=material)
        created.append((result["material"], f"material-{name}"))

    assert_recorded(
        "materials-create-dishwasher-and-beverage",
        stable_ids(
            [material for material, _ in created],
            {material["id"]: fixed for material, fixed in created},
        ),
    )


async def test_record_a_material_of_the_form_other(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    result = await panel.call(
        "coinop/materials/create",
        material={
            "name": "Liquid fertiliser",
            "form": "other",
            "type": "Fertiliser",
            "density": 1.2,
            "price": {
                "source": "fixed",
                "pack_price": 6,
                "pack_size": 500,
                "pack_unit": "ml",
            },
        },
    )

    material = result["material"]
    assert_recorded(
        "materials-create-other",
        stable_ids(material, {material["id"]: "material-fertiliser"}),
    )


async def test_record_a_run_split_across_slots(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    pla, petg = materials()
    place_materials(
        hass_storage, pla | {"colour": "#1a1a1a"}, petg | {"default_for_type": True}
    )
    entry = await add_hub(hass)
    used = {"unit_of_measurement": "mm"}
    hass.states.async_set(FILAMENT, "0", used)
    hass.states.async_set("sensor.ace_slot_1", "PLA", {"color_hex": "#1A1A1A"})
    hass.states.async_set("sensor.ace_slot_2", "PETG", {"color_hex": "#FFFFFF"})
    hass.states.async_set("sensor.ace_loaded_slot", "1")
    subentry = await add_device(
        hass,
        entry,
        material=FILAMENT,
        slots=["sensor.ace_slot_1", "sensor.ace_slot_2"],
        colour_attribute="color_hex",
        loaded_slot="sensor.ace_loaded_slot",
    )
    await panel.call(
        "coinop/devices/update_settings",
        device_id=subentry.subentry_id,
        settings={"default_material": "pla-black"},
    )
    hass.states.async_set(STATUS, "printing")
    await clock.advance(minutes=45)
    hass.states.async_set("sensor.ace_loaded_slot", "2")
    await clock.advance(minutes=15)
    hass.states.async_set(FILAMENT, "4000", used)
    hass.states.async_set(STATUS, "finished")
    await hass.async_block_till_done()
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    detail = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    electricity_item, pla_item, petg_item = detail["line_items"]

    corrected = await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=petg_item["id"],
        quantity=4,
    )

    ids = {
        run["id"]: "keychain",
        subentry.subentry_id: "device-kobra",
        electricity_item["id"]: "keychain-electricity",
        pla_item["id"]: "keychain-pla",
        petg_item["id"]: "keychain-petg",
    }
    assert_recorded("line-items-split", stable_ids(corrected, ids))


async def test_record_what_spoolman_answers(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    place_materials(hass_storage, stored_material("pla-black", name="PLA black"))
    petg = filament(
        8,
        name="PETG Galaxy Black",
        vendor={"id": 2, "name": "Prusament"},
        material="PETG",
        price=None,
        density=1.27,
        color_hex="2B2B33",
    )
    entry = await add_spoolman_hub(
        hass,
        aioclient_mock,
        filaments=[
            filament(7),
            petg,
            filament(9, name="TPU clear", material="TPU", price=None, color_hex=None),
        ],
        spools=[spool(1, petg, price=29.99, initial_weight=1000.0)],
    )

    listed = await panel.call("coinop/spoolman/filaments")
    created = await panel.call("coinop/materials/create_from_spoolman", filament_id=8)
    linked = await panel.call(
        "coinop/materials/update",
        material_id="pla-black",
        material={"price": {"source": "spoolman", "filament_id": 7}},
    )
    spoolman_down(aioclient_mock)
    unreachable = await panel.call("coinop/spoolman/filaments")
    await set_options(hass, entry)
    not_configured = await panel.call("coinop/spoolman/filaments")

    assert_recorded("spoolman-filaments", listed)
    assert_recorded("spoolman-filaments-unavailable", [not_configured, unreachable])
    ids = {created["material"]["id"]: "material-petg"}
    assert_recorded("materials-create-from-spoolman", stable_ids(created, ids))
    assert_recorded("materials-link-spoolman", linked)


async def test_record_the_cost_statement_export(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, *history())
    entry = await add_hub(hass)
    await set_options(hass, entry, markup=10)

    defaults = await panel.call("coinop/cost_statement/defaults")
    created = await panel.call(
        "coinop/cost_statement/create",
        run_ids=["benchy", "helmet"],
        detail="compact",
        language="en",
        markup=10,
    )

    path, signature = created["path"].split("?authSig=")
    token = path.rsplit("/", 1)[1]
    assert_recorded("cost-statement-defaults", defaults)
    assert_recorded(
        "cost-statement-create",
        stable_ids(created, {token: "export-token", signature: "signature"}),
    )
