"""Job and Material on an Other Device: the job section, a Material Line Item on every
Run, and the one combination the list of choices refuses."""

from itertools import combinations
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import (
    MAPPING,
    add_hub,
    add_other_device,
    basic_entities,
    coinop_entities,
    configure,
    other_input,
    price_choice,
    price_input,
    start_reconfigure,
    walk_to_mapping,
)
from .stored import place_materials, stored_material
from .test_device_flow import fields, suggested
from .test_manual_runs import create
from .test_material_usage import material_items
from .test_other_devices import choose_other
from .test_other_images_and_parts import KILN_CAMERA, KILN_PREVIEW
from .test_other_programs import line_items
from .test_run_event import record_events
from .test_runs import stored_runs, value
from .websocket import PanelClient

ROUTER_STATUS = "sensor.router_status"
ROUTER_JOB = "sensor.router_job"
# The stock a job milled away, as the router's controller weighs it.
ROUTER_USED = "sensor.router_stock_used"
ROUTER_MAPPING = {
    "running": ["cutting"],
    "paused": ["paused"],
    "finished": ["done"],
    "cancelled": ["cancelled"],
    "ignored": ["idle"],
}
# 0.005 per g.
MDF = stored_material(
    "mdf",
    name="MDF",
    form="other",
    type="MDF",
    density=0.75,
    diameter=None,
    price={"source": "fixed", "pack_price": 30, "pack_size": 6000, "pack_unit": "g"},
)
# 4.00 per sheet.
PLYWOOD = stored_material(
    "plywood",
    name="Plywood sheet",
    form="other",
    type="Plywood",
    density=None,
    diameter=None,
    price={"source": "fixed", "pack_price": 40, "pack_size": 10, "pack_unit": "pcs"},
)
# Every choice the `other` step offers, in its order.
CHOICES = (
    "program",
    "doses",
    "water",
    "job",
    "images",
    "part_count",
    "per_run_meters",
)


async def set_router(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(ROUTER_STATUS, status)
    await hass.async_block_till_done()


async def set_router_job(hass: HomeAssistant, job: str) -> None:
    hass.states.async_set(ROUTER_JOB, job)
    await hass.async_block_till_done()


async def set_stock_used(hass: HomeAssistant, grams: float | str) -> None:
    hass.states.async_set(ROUTER_USED, str(grams), {"unit_of_measurement": "g"})
    await hass.async_block_till_done()


async def add_cnc_router(
    hass: HomeAssistant,
    panel: PanelClient,
    hass_storage: dict[str, Any] | None = None,
    *,
    entry: ConfigEntry | None = None,
    default: str | None = "mdf",
    **options: Any,
) -> ConfigSubentry:
    """A CNC router, idle, in EUR at 0.30 per kWh: an Other Device with the Type Name
    "CNC router" that has Job and Material, with its job name on `ROUTER_JOB`, its
    Material used on `ROUTER_USED` (in g, at 0) and the default Material `default`,
    estimating its electricity from 300 W unless `options` say otherwise.
    `hass_storage` places the Materials `MDF` and `PLYWOOD`, which the hub reads when
    it is set up."""
    hass.config.currency = "EUR"
    if hass_storage is not None:
        place_materials(hass_storage, MDF, PLYWOOD)
    await set_stock_used(hass, 0)
    await set_router(hass, "idle")
    router: dict[str, Any] = {
        "type_name": "CNC router",
        "name": "CNC router",
        "status": ROUTER_STATUS,
        "mapping": ROUTER_MAPPING,
        "has": ["job"],
        "job": {"entity_id": ROUTER_JOB, "material_entity_id": ROUTER_USED},
        "running_power": 300,
    }
    device = await add_other_device(
        hass, entry or await add_hub(hass), **router | options
    )
    if default:
        await panel.call(
            "coinop/devices/update_settings",
            device_id=device.subentry_id,
            settings={"default_material": default},
        )
    return device


async def walk_other_to_job(
    hass: HomeAssistant, entry: ConfigEntry, *has: str, status: str = ROUTER_STATUS
) -> Any:
    """Add Device for an Other Device with the choices `has`, up to the step after
    the Status mapping."""
    result = await walk_to_mapping(
        hass,
        entry,
        name="CNC router",
        status=status,
        device_type="other",
        other=other_input("CNC router", has),
    )
    return await configure(hass, result, ROUTER_MAPPING)


async def test_job_and_material_is_offered_after_what_the_device_consumes(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)

    assert fields(result) == ["type_name", *CHOICES]


async def test_job_and_material_with_images_and_a_part_count_asks_for_their_sections(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    hass.states.async_set(ROUTER_USED, "0", {"unit_of_measurement": "g"})
    result = await choose_other(hass, entry)

    steps = []
    for user_input in (
        other_input("CNC router", ["job", "images", "part_count"]),
        {},
        {"name": "CNC router"},
        {"entity_id": ROUTER_STATUS},
        ROUTER_MAPPING,
        {"entity_id": ROUTER_JOB, "material_entity_id": ROUTER_USED},
        {"thumbnail": KILN_PREVIEW, "camera": KILN_CAMERA},
        {"next_step_id": "estimate"},
        {"running_power": 300},
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
        "job",
        "images",
        "consumption",
        "estimate",
        "price",
        "fixed_price",
        None,
    ]
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [router] = entry.subentries.values()
    assert router.data["job"] == {
        "entity_id": ROUTER_JOB,
        "attribute": None,
        "material": {"entity_id": ROUTER_USED, "attribute": None, "unit": "g"},
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    }
    assert {"program", "water", "water_price"}.isdisjoint(router.data)
    result = await start_reconfigure(hass, entry, router)
    assert result["menu_options"] == [
        "other",
        "status",
        "job",
        "images",
        "consumption",
        "price",
        "save",
    ]
    result = await configure(hass, result, {"next_step_id": "job"})
    assert (result["step_id"], suggested(result, "entity_id")) == ("job", ROUTER_JOB)
    result = await configure(hass, result, {"entity_id": ROUTER_JOB})
    assert result["step_id"] == "reconfigure"


async def test_job_and_material_alone_brings_the_job_step_a_printer_sees(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    printer = await configure(hass, await walk_to_mapping(hass, entry), MAPPING)

    router = await walk_other_to_job(hass, entry, "job")

    assert (router["step_id"], fields(router)) == (printer["step_id"], fields(printer))
    assert (router["step_id"], fields(router)) == (
        "job",
        [
            "entity_id",
            "attribute",
            "material_entity_id",
            "material_attribute",
            "slots",
            "colour_attribute",
            "loaded_slot",
        ],
    )
    result = await configure(hass, router, {})
    assert result["menu_options"] == ["energy", "power", "estimate", "none"]


async def test_an_other_device_without_job_and_material_is_not_asked_for_a_job(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_other_to_job(hass, entry, "images", "part_count")

    assert result["step_id"] == "images"


async def test_job_and_material_is_refused_with_a_program_or_doses_and_nothing_else_is(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    mixes = [
        list(mix)
        for size in range(len(CHOICES) + 1)
        for mix in combinations(CHOICES, size)
    ]

    refused = []
    for mix in mixes:
        result = await choose_other(hass, entry)
        result = await configure(hass, result, other_input("CNC router", mix))
        if result["step_id"] == "other":
            assert result["errors"] == {"base": "job_with_program_or_doses"}, mix
            refused.append(mix)
        else:
            assert result["step_id"] == "device_without_profile", mix
        hass.config_entries.subentries.async_abort(result["flow_id"])

    assert len(mixes) == 128
    assert refused == [
        mix for mix in mixes if "job" in mix and ("program" in mix or "doses" in mix)
    ]
    assert len(refused) == 48


async def test_a_refused_mix_keeps_what_was_picked_and_is_accepted_once_it_fits(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await choose_other(hass, entry)

    result = await configure(
        hass, result, other_input("  ", ["job", "program", "doses", "water"])
    )

    assert result["errors"] == {
        "type_name": "type_name_required",
        "base": "job_with_program_or_doses",
    }
    assert [choice for choice in CHOICES if suggested(result, choice)] == [
        "program",
        "doses",
        "water",
        "job",
    ]
    result = await configure(hass, result, other_input("CNC router", ["job", "water"]))
    assert result["step_id"] == "device_without_profile"


async def cut(
    hass: HomeAssistant,
    clock: Clock,
    job: str,
    *,
    grams: float | None = None,
    outcome: str = "done",
) -> None:
    """A job of an hour that ends as `outcome`, after which the router is idle again;
    with `grams` its controller reports the stock used as the job ends."""
    await set_router_job(hass, job)
    await set_router(hass, "cutting")
    await clock.advance(hours=1)
    if grams is not None:
        await set_stock_used(hass, grams)
    await set_router(hass, outcome)
    # A Run with a Material used input waits for that input's next report.
    await clock.advance(minutes=5)
    await set_router(hass, "idle")
    # Older Home Assistant needs a second pass for the Run event's listeners.
    await hass.async_block_till_done()


async def test_a_run_is_named_after_its_job_and_charges_the_material_it_used(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    entity_registry: er.EntityRegistry,
) -> None:
    await add_cnc_router(hass, panel, hass_storage)
    fired = record_events(hass, "event.cnc_router_run")

    await cut(hass, clock, "Sign_Oak.gcode", grams=120)

    [run] = stored_runs(hass_storage)
    assert (run["name"], run["job_name"], run["outcome"], run["flags"]) == (
        "Sign Oak",
        "Sign_Oak.gcode",
        "completed",
        [],
    )
    assert (run.get("program"), run["part_count"]) == (None, None)
    assert line_items(run) == [
        ("electricity", "estimated", 0.3, "kWh", 0.09),
        ("material", None, 120, "g", 0.60),
    ]
    [item] = material_items(run)
    assert (item["material_id"], item["measured"]) == ("mdf", True)
    assert coinop_entities(entity_registry) == sorted(
        [*basic_entities("cnc_router"), "sensor.cnc_router_material_used"]
    )
    assert value(hass, "sensor.cnc_router_material_used") == pytest.approx(120)
    assert value(hass, "sensor.cnc_router_material_cost") == pytest.approx(0.60)
    [started, ended] = fired
    assert (started["event_type"], started["name"]) == ("started", "Sign Oak")
    assert (ended["event_type"], ended["name"]) == ("ended", "Sign Oak")
    assert ended["material_grams"] == pytest.approx(120)
    assert ended["total_cost"] == pytest.approx(0.69)
    assert {"program", "water_litres", "part_count"}.isdisjoint(ended)


async def test_without_a_material_used_input_the_default_material_is_left_to_fill_in(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_cnc_router(
        hass, panel, hass_storage, default="plywood", job={"entity_id": ROUTER_JOB}
    )

    await cut(hass, clock, "Shelf.gcode")

    [run] = stored_runs(hass_storage)
    assert (run["name"], run["flags"]) == ("Shelf", ["usage_missing"])
    [item] = material_items(run)
    assert {
        key: item[key]
        for key in ("material_id", "measured", "quantity", "unit", "unit_price")
    } == {
        "material_id": "plywood",
        "measured": False,
        "quantity": None,
        "unit": "pcs",
        "unit_price": pytest.approx(4.0),
    }
    filled = await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=item["id"],
        quantity=2,
    )
    assert filled["run"]["flags"] == []
    assert filled["run"]["subtotals"]["material"] == pytest.approx(8.0)


@pytest.mark.parametrize(
    ("has", "flags", "materials"),
    [
        (["job"], ["usage_missing", "material_missing"], 1),
        (["job", "images", "part_count"], ["usage_missing", "material_missing"], 1),
        (["images", "part_count"], [], 0),
        ([], [], 0),
    ],
    ids=["Job and Material", "with Images and Part Count", "without it", "nothing"],
)
async def test_only_a_device_with_job_and_material_is_asked_to_fill_in_a_runs_material(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    has: list[str],
    flags: list[str],
    materials: int,
) -> None:
    await add_cnc_router(hass, panel, default=None, has=has, job={})

    await cut(hass, clock, "Shelf.gcode")

    [run] = stored_runs(hass_storage)
    assert (run["flags"], len(material_items(run))) == (flags, materials)
    # Without a job input the job's name never reaches the Run.
    assert run["name"] is None


async def test_a_device_without_job_and_material_has_no_material_used_sensor_or_grams(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    entity_registry: er.EntityRegistry,
) -> None:
    await add_cnc_router(hass, panel, default=None, has=["images", "part_count"])
    fired = record_events(hass, "event.cnc_router_run")

    await cut(hass, clock, "Shelf.gcode", grams=120)

    assert coinop_entities(entity_registry) == basic_entities("cnc_router")
    [_, ended] = fired
    assert ended["event_type"] == "ended"
    assert "material_grams" not in ended


async def test_a_material_line_item_can_be_added_by_hand_whatever_the_device_has(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_cnc_router(hass, panel, hass_storage, default=None, has=[])
    await cut(hass, clock, "Shelf.gcode")
    [run] = stored_runs(hass_storage)

    added = await panel.call(
        "coinop/line_items/add",
        run_id=run["id"],
        kind="material",
        material_id="plywood",
        quantity=1,
        unit="pcs",
    )

    [item] = material_items(added["run"])
    assert (item["material_id"], item["amount"]) == ("plywood", pytest.approx(4.0))
    assert added["run"]["flags"] == []


async def test_a_manual_run_of_a_device_with_job_and_material_waits_for_its_material(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    router = await add_cnc_router(hass, panel, hass_storage)
    await clock.advance(hours=5)

    run = await create(panel, router.subentry_id, name="Sign")

    assert (run["name"], run["flags"], run["part_count"]) == (
        "Sign",
        ["usage_missing"],
        None,
    )
    [item] = material_items(run)
    assert (item["material_id"], item["quantity"], item["unit"]) == ("mdf", None, "g")
