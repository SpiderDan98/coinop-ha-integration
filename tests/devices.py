"""Set up the hub and add Devices through the real flows, the way a user does."""

from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigSubentry,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.coinop.const import DOMAIN

from .clock import Clock

STATUS = "sensor.kobra_status"
ENERGY = "sensor.kobra_plug_energy"
POWER = "sensor.kobra_plug_power"
PRICE = "sensor.electricity_price"
MAPPING = {
    "running": ["printing"],
    "paused": ["paused"],
    "finished": ["finished"],
    "cancelled": ["cancelled"],
    "ended": ["idle"],
}

WASHER_STATUS = "sensor.washer_status"
WASHER_ENERGY = "sensor.washer_plug_energy"
WASHER_WATER = "sensor.washer_water"
WATER_PRICE = "sensor.water_price"
WASHER_MAPPING = {
    "running": ["running"],
    "paused": ["paused"],
    "finished": ["finished"],
    "cancelled": ["cancelled"],
    "ignored": ["off"],
}


async def add_hub(hass: HomeAssistant) -> ConfigEntry:
    MockConfigEntry(domain=DOMAIN, title="Coin-op").add_to_hass(hass)
    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def add_printer(hass: HomeAssistant, name: str = "Kobra S1") -> dr.DeviceEntry:
    """A printer's HA device, as its own integration registers it."""
    printer_entry = MockConfigEntry(domain="printer_integration")
    printer_entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=printer_entry.entry_id,
        identifiers={("printer_integration", name)},
        name=name,
    )


async def open_device_types(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    """Open Add Device and choose manual setup in Quick Start, whatever it offers;
    returns the Device Type choice."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    assert result["step_id"].startswith("quick_start"), result["step_id"]
    result = await configure(hass, result, {"device": "manual"})
    assert result["step_id"] == "user"
    return result


async def start_add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    printer: str | None = None,
    device_type: str = "3d_printer",
    other: dict[str, Any] | None = None,
) -> Any:
    """Open Add Device, pick the Device Type and the HA device (or none); returns the
    name form, set up manually whatever Quick Start offers. `other`
    answers the step only the Device Type Other has (see `other_input`)."""
    result = await open_device_types(hass, entry)
    result = await configure(hass, result, {"device_type": device_type})
    if other is not None:
        assert result["step_id"] == "other", result.get("errors")
        result = await configure(hass, result, other)
    assert result["step_id"] in ("device", "device_without_profile"), result.get(
        "errors"
    )
    result = await configure(
        hass, result, {} if printer is None else {"device": printer}
    )
    assert result["step_id"] == "name", result.get("errors")
    return result


async def configure(hass: HomeAssistant, result: Any, user_input: Any) -> Any:
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )
    if result["type"] is FlowResultType.CREATE_ENTRY:
        # A new Device reloads the hub entry; a test must not end halfway through.
        await hass.async_block_till_done()
    return result


async def walk_to_mapping(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    name: str = "Kobra",
    printer: str | None = None,
    status: str = STATUS,
    attribute: str | None = None,
    device_type: str = "3d_printer",
    other: dict[str, Any] | None = None,
) -> Any:
    result = await configure(
        hass,
        await start_add_device(
            hass, entry, printer=printer, device_type=device_type, other=other
        ),
        {"name": name},
    )
    assert result["step_id"] == "status"
    status_input = {"entity_id": status} | (
        {"attribute": attribute} if attribute else {}
    )
    result = await configure(hass, result, status_input)
    assert result["step_id"] == "mapping", result.get("errors")
    return result


async def walk_to_consumption(
    hass: HomeAssistant, entry: ConfigEntry, *, status: str = STATUS
) -> Any:
    result = await configure(
        hass, await walk_to_mapping(hass, entry, status=status), MAPPING
    )
    assert result["step_id"] == "job", result.get("errors")
    result = await configure(hass, result, {})
    assert result["step_id"] == "images", result.get("errors")
    result = await answer_progress(hass, await configure(hass, result, {}))
    assert result["type"] is FlowResultType.MENU, result.get("errors")
    return result


async def add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    name: str = "Kobra",
    printer: str | None = None,
    status: str = STATUS,
    attribute: str | None = None,
    mapping: dict[str, list[str]] = MAPPING,
    source: str = "estimate",
    meter: dict[str, Any] | None = None,
    job: str | None = None,
    job_attribute: str | None = None,
    material: str | None = None,
    material_attribute: str | None = None,
    material_unit: str | None = None,
    slots: list[str] | None = None,
    colour_attribute: str | None = None,
    loaded_slot: str | None = None,
    thumbnail: str | None = None,
    camera: str | None = None,
    snapshot: bool | None = None,
    running_power: float = 120,
    paused_power: float | None = None,
    price: float | dict[str, Any] = 0.30,
    remaining_time: str | None = None,
    progress: str | None = None,
    drying: Iterable[tuple[str, str | None]] = (),
    drying_power: float | None = None,
) -> ConfigSubentry:
    """Walk Add Device to the end; returns the new Device once the entry reloaded.

    `source` picks the consumption source; Energy and Power take `meter` as input,
    "none" nothing, and no price either.
    A fixed `price` is a number; a dict is the price entity step's input.
    `material` is the Material used entity; with `material_attribute`, `material_unit`
    answers the unit step. `slots` are the Slot entities in Slot order; with them,
    `drying` and `drying_power` answer the drying steps (see `answer_drying`).
    `remaining_time` and `progress` answer the progress step, as in every `add_...`
    helper here.
    """
    result = await walk_to_mapping(
        hass, entry, name=name, printer=printer, status=status, attribute=attribute
    )
    result = await configure(hass, result, mapping)
    assert result["step_id"] == "job", result.get("errors")
    job_input = {
        key: value
        for key, value in (
            ("entity_id", job),
            ("attribute", job_attribute),
            ("material_entity_id", material),
            ("material_attribute", material_attribute),
            ("slots", slots),
            ("colour_attribute", colour_attribute),
            ("loaded_slot", loaded_slot),
        )
        if value
    }
    result = await configure(hass, result, job_input)
    if material_attribute:
        assert result["step_id"] == "material_unit", result.get("errors")
        result = await configure(hass, result, {"unit": material_unit})
    if slots:
        result = await answer_drying(hass, result, drying, drying_power)
    assert result["step_id"] == "images", result.get("errors")
    result = await configure(hass, result, images_input(thumbnail, camera, snapshot))
    estimate = {"running_power": running_power} | (
        {} if paused_power is None else {"paused_power": paused_power}
    )
    result = await answer_electricity(
        hass,
        await answer_progress(hass, result, remaining_time, progress),
        source,
        estimate if source == "estimate" else meter,
        price,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


async def add_basic_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    device_type: str,
    name: str,
    status: str,
    mapping: dict[str, list[str]],
    meter: dict[str, Any] | None = None,
    source: str = "energy",
    price: float | dict[str, Any] = 0.30,
    remaining_time: str | None = None,
    progress: str | None = None,
    expected_energy: dict[str, Any] | None = None,
) -> ConfigSubentry:
    """Walk Add Device to the end for a Device Type with only the sections every
    Device has: HA device and name, Status, mapping, electricity source and price.

    `source` is "energy" or "power", read from `meter`, or "none", which takes no
    meter and no price: the only ones offered.
    """
    result = await walk_to_mapping(
        hass, entry, name=name, status=status, device_type=device_type
    )
    result = await answer_progress(
        hass,
        await configure(hass, result, mapping),
        remaining_time,
        progress,
        expected_energy,
    )
    assert (result["step_id"], result["menu_options"]) == (
        "consumption",
        ["energy", "power", "none"],
    ), result.get("errors")
    result = await answer_electricity(hass, result, source, meter, price)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


# What a Device with only the sections every Device has stores.
BASIC_DATA = [
    "consumption",
    "device_type",
    "mapping",
    "price",
    "printer_device_id",
    "progress",
    "status",
]


def basic_entities(slug: str) -> list[str]:
    """The entities every Device has, of the Device whose entity ids start with
    `slug`: none for water or Material used."""
    sensors = (
        "current_run_cost",
        "electricity_cost",
        "energy_in_runs",
        "flagged_runs",
        "last_run_cost",
        "material_cost",
        "other_cost",
        "projected_run_cost",
        "running_time",
        "runs",
        "total_cost",
    )
    return [f"event.{slug}_run", *(f"sensor.{slug}_{key}" for key in sensors)]


def coinop_entities(entity_registry: er.EntityRegistry) -> list[str]:
    return sorted(
        entity.entity_id
        for entity in entity_registry.entities.values()
        if entity.platform == "coinop"
    )


OTHER_MAPPING = {"running": ["on"], "ended": ["off"]}
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


async def report_status(hass: HomeAssistant, entity_id: str, status: str) -> None:
    """Report `status` on a Device's Status entity and let Coin-op follow it."""
    hass.states.async_set(entity_id, status)
    await hass.async_block_till_done()


async def settle(hass: HomeAssistant) -> None:
    """Wait once more after a Run's end: older Home Assistant needs a second pass
    for the Run event's listeners."""
    await hass.async_block_till_done()


async def run_once(
    hass: HomeAssistant,
    clock: Clock,
    status: str,
    *,
    minutes: float,
    running: str = "on",
    ended: str = "off",
) -> None:
    """A Run on the Status entity `status`: `running` for `minutes`, then `ended`."""
    await report_status(hass, status, running)
    await clock.advance(minutes=minutes)
    await report_status(hass, status, ended)
    await settle(hass)


def other_input(type_name: str, has: Iterable[str] = ()) -> dict[str, Any]:
    """The input of the step only the Device Type Other has: its Type Name and the
    choices picked of what the Device has, by key (such as "per_run_meters")."""
    return {"type_name": type_name} | dict.fromkeys(has, True)


async def add_other_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    type_name: str,
    name: str,
    status: str,
    has: Iterable[str] = (),
    device: str | None = None,
    mapping: dict[str, list[str]] = OTHER_MAPPING,
    job: dict[str, Any] | None = None,
    material_unit: str | None = None,
    thumbnail: str | None = None,
    camera: str | None = None,
    snapshot: bool | None = None,
    program: dict[str, Any] | None = None,
    source: str = "estimate",
    meter: dict[str, Any] | None = None,
    running_power: float = 120,
    price: float | dict[str, Any] = 0.30,
    water: str = "none",
    water_meter: dict[str, Any] | None = None,
    water_price: float | dict[str, Any] = 4.0,
    remaining_time: str | None = None,
    progress: str | None = None,
) -> ConfigSubentry:
    """Walk Add Device to the end for an Other Device with `type_name` that has the
    choices `has`, running while its Status is "on" unless `mapping` says otherwise.

    With the choice "job" (Job and Material), `job` is the job step's input, by its
    fields (`entity_id`, `material_entity_id`, `slots`, `loaded_slot`, ...; no job
    input without it), and `material_unit` answers the unit step that a
    `material_attribute` brings.
    With "images" among `has`, `thumbnail`, `camera` and `snapshot` answer the images
    step, each left as the step has it when not given. With the choice "program",
    `program` is the Program step's input (no Program input without it). `source` is
    "estimate" (from `running_power`), "energy" or "power" (read from `meter`),
    "per_program" or "none", which takes no price. With the choice "water", `water`
    is its source: "meter" or "flow" (read from `water_meter`), "per_program" or
    "none"; a fixed `water_price` is per m³. The choice "doses" brings no step. It
    fails on any step beyond those the choices bring.
    """
    has = list(has)
    result = await walk_to_mapping(
        hass,
        entry,
        name=name,
        printer=device,
        status=status,
        device_type="other",
        other=other_input(type_name, has),
    )
    result = await configure(hass, result, mapping)
    if "job" in has:
        assert result["step_id"] == "job", result.get("errors")
        result = await configure(hass, result, job or {})
        if (job or {}).get("material_attribute"):
            assert result["step_id"] == "material_unit", result.get("errors")
            result = await configure(hass, result, {"unit": material_unit})
        if (job or {}).get("slots"):
            result = await answer_drying(hass, result)
    if "images" in has:
        assert result["step_id"] == "images", result.get("errors")
        result = await configure(
            hass, result, images_input(thumbnail, camera, snapshot)
        )
    if "program" in has:
        assert result["step_id"] == "program", result.get("errors")
        result = await configure(hass, result, program or {})
    estimate = {"running_power": running_power}
    result = await answer_electricity(
        hass,
        await answer_progress(hass, result, remaining_time, progress),
        source,
        estimate if source == "estimate" else meter,
        price,
    )
    if "water" in has:
        result = await answer_water(hass, result, water, water_meter, water_price)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


async def answer_electricity(
    hass: HomeAssistant,
    result: Any,
    source: str,
    meter: dict[str, Any] | None,
    price: float | dict[str, Any],
) -> Any:
    """Answer Add Device's electricity steps from the source menu `result`: the
    `source`, its step's input `meter` unless it is "per_program" or "none" (for
    "estimate" the average powers), and the `price` unless it is "none"."""
    assert result["step_id"] == "consumption", result.get("errors")
    result = await configure(hass, result, {"next_step_id": source})
    if source not in ("per_program", "none"):
        result = await configure(hass, result, meter)
    if source != "none":
        assert result["step_id"] == "price", result.get("errors")
        result = await configure(hass, result, price_choice(price))
        result = await configure(hass, result, price_input(price))
    return result


async def answer_drying(
    hass: HomeAssistant,
    result: Any,
    units: Iterable[tuple[str, str | None]] = (),
    drying_power: float | None = None,
) -> Any:
    """Answer the drying steps from `result` on: the multi-material units by their
    active and drying left entities, and with any, the `drying_power`."""
    units = list(units)
    assert result["step_id"] == "drying", result.get("errors")
    result = await configure(hass, result, {"active": [a for a, _ in units]})
    for _, left in units:
        assert result["step_id"] == "drying_left", result.get("errors")
        result = await configure(hass, result, {"drying_left": left} if left else {})
    if units:
        assert result["step_id"] == "drying_power", result.get("errors")
        result = await configure(
            hass, result, {} if drying_power is None else {"drying_power": drying_power}
        )
    return result


async def answer_progress(
    hass: HomeAssistant,
    result: Any,
    remaining_time: str | None = None,
    progress: str | None = None,
    expected_energy: dict[str, Any] | None = None,
) -> Any:
    """Answer the progress step `result` with the Remaining time and Progress
    entities, each if given, and `expected_energy`, the Expected energy fields
    as the step names them."""
    assert result["step_id"] == "progress", result.get("errors")
    answers = {"remaining_time": remaining_time, "progress": progress}
    return await configure(
        hass,
        result,
        {key: value for key, value in answers.items() if value}
        | (expected_energy or {}),
    )


async def answer_water(
    hass: HomeAssistant,
    result: Any,
    source: str,
    meter: dict[str, Any] | None,
    price: float | dict[str, Any],
) -> Any:
    """Answer Add Device's water steps from the water source menu `result`: the
    `source`, its `meter` for "meter" and "flow", and the `price` unless it is "none"."""
    assert result["step_id"] == "water", result.get("errors")
    result = await configure(hass, result, {"next_step_id": f"water_{source}"})
    if source in ("meter", "flow"):
        result = await configure(hass, result, meter)
    if source != "none":
        assert result["step_id"] == "water_price", result.get("errors")
        result = await configure(
            hass,
            result,
            {"next_step_id": f"water_{price_choice(price)['next_step_id']}"},
        )
        result = await configure(hass, result, price_input(price))
    return result


async def add_washing_machine(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    name: str = "Washer",
    device: str | None = None,
    status: str = WASHER_STATUS,
    mapping: dict[str, list[str]] = WASHER_MAPPING,
    program: dict[str, Any] | None = None,
    source: str = "energy",
    meter: dict[str, Any] | None = None,
    price: float | dict[str, Any] = 0.30,
    water: str | None = "none",
    water_meter: dict[str, Any] | None = None,
    water_price: float | dict[str, Any] = 4.0,
    device_type: str = "washing_machine",
    remaining_time: str | None = None,
    progress: str | None = None,
    expected_energy: dict[str, Any] | None = None,
) -> ConfigSubentry:
    """Walk Add Device for a washing machine to the end; by default with its plug's
    energy meter, no Program input and no water source. `device_type` walks it for
    another Device Type with the washing machine's steps.

    `source` "per_program" takes no `meter`, "none" no `meter` and no `price`.
    `water` is "meter" (on `WASHER_WATER` unless `water_meter` gives the input),
    "flow", "per_program" or "none"; a fixed `water_price` is per m³. `water=None`
    walks a Device Type without water, which is done after its electricity.
    """
    result = await walk_to_mapping(
        hass,
        entry,
        name=name,
        printer=device,
        status=status,
        device_type=device_type,
    )
    result = await configure(hass, result, mapping)
    assert result["step_id"] == "program", result.get("errors")
    result = await configure(hass, result, program or {})
    result = await answer_electricity(
        hass,
        await answer_progress(hass, result, remaining_time, progress, expected_energy),
        source,
        meter or {"entity_id": WASHER_ENERGY},
        price,
    )
    if water is not None:
        result = await answer_water(
            hass, result, water, water_meter or {"entity_id": WASHER_WATER}, water_price
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


def images_input(
    thumbnail: str | None, camera: str | None, snapshot: bool | None
) -> dict[str, Any]:
    """The images step's input; what is None is left as the step has it."""
    return {
        key: value
        for key, value in (
            ("thumbnail", thumbnail),
            ("camera", camera),
            ("snapshot", snapshot),
        )
        if value is not None
    }


def price_choice(price: float | dict[str, Any]) -> dict[str, str]:
    """The price menu's choice for a fixed `price` or a price entity's input."""
    return {
        "next_step_id": "price_entity" if isinstance(price, dict) else "fixed_price"
    }


def price_input(price: float | dict[str, Any]) -> dict[str, Any]:
    return price if isinstance(price, dict) else {"price": price}


async def walk_to_price(
    hass: HomeAssistant, entry: ConfigEntry, *, status: str = STATUS
) -> Any:
    """Walk Add Device with an estimate to the price menu."""
    result = await walk_to_consumption(hass, entry, status=status)
    result = await configure(hass, result, {"next_step_id": "estimate"})
    result = await configure(hass, result, {"running_power": 100})
    assert result["step_id"] == "price", result.get("errors")
    return result


async def start_reconfigure(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> Any:
    """Open the Device's reconfigure menu."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.MENU, result
    return result


async def reconfigure(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry, *inputs: Any
) -> Any:
    """Submit `inputs` in turn from the reconfigure menu, then Save."""
    result = await start_reconfigure(hass, entry, subentry)
    for user_input in inputs:
        result = await configure(hass, result, user_input)
    assert result["step_id"] == "reconfigure", result.get("errors")
    return await save(hass, result)


async def save(hass: HomeAssistant, menu: Any) -> Any:
    """Choose Save in the reconfigure menu; returns what answers, a refusal included,
    once the hub entry reloaded."""
    result = await configure(hass, menu, {"next_step_id": "save"})
    await hass.async_block_till_done()
    return result


async def open_other(
    hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry
) -> Any:
    """Pick the reconfigure menu's entry for an Other Device's Type Name and what it
    has; returns what answers: the `other` step, or the refusal."""
    result = await start_reconfigure(hass, entry, subentry)
    return await configure(hass, result, {"next_step_id": "other"})


async def change_other_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    *inputs: Any,
    type_name: str | None = None,
    has: Iterable[str],
) -> Any:
    """Change what an Other Device has to exactly the choices `has` in its reconfigure
    menu, and its Type Name if `type_name` is given; answer the steps the change
    brings with `inputs` in turn, then Save. It fails unless `inputs` lead back to
    the menu."""
    return await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "other"},
        other_input(type_name or subentry.data["type_name"], has),
        *inputs,
    )
