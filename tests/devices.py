"""Set up the hub and add Devices through the real flows, the way a user does."""

from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigSubentry,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.coinop.const import DOMAIN

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


async def start_add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    printer: str | None = None,
    device_type: str = "3d_printer",
) -> Any:
    """Open Add Device, pick the Device Type and the HA device (or none); returns the
    name form."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await configure(hass, result, {"device_type": device_type})
    assert result["step_id"] == "device", result.get("errors")
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
) -> Any:
    result = await configure(
        hass,
        await start_add_device(hass, entry, printer=printer, device_type=device_type),
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
    result = await configure(hass, result, {})
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
) -> ConfigSubentry:
    """Walk Add Device to the end; returns the new Device once the entry reloaded.

    `source` picks the consumption source; Energy and Power take `meter` as input.
    A fixed `price` is a number; a dict is the price entity step's input.
    `material` is the Material used entity; with `material_attribute`, `material_unit`
    answers the unit step. `slots` are the Slot entities in Slot order.
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
    assert result["step_id"] == "images", result.get("errors")
    images = {
        key: value
        for key, value in (
            ("thumbnail", thumbnail),
            ("camera", camera),
            ("snapshot", snapshot),
        )
        if value is not None
    }
    result = await configure(hass, result, images)
    assert result["type"] is FlowResultType.MENU, result.get("errors")
    result = await configure(hass, result, {"next_step_id": source})
    if source == "estimate":
        estimate = {"running_power": running_power}
        if paused_power is not None:
            estimate["paused_power"] = paused_power
        result = await configure(hass, result, estimate)
    else:
        result = await configure(hass, result, meter)
    assert result["step_id"] == "price", result.get("errors")
    result = await configure(hass, result, price_choice(price))
    result = await configure(hass, result, price_input(price))
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


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
    water: str = "none",
    water_meter: dict[str, Any] | None = None,
    water_price: float | dict[str, Any] = 4.0,
) -> ConfigSubentry:
    """Walk Add Device for a washing machine to the end; by default with its plug's
    energy meter, no Program input and no water source.

    `water` is "meter" (on `WASHER_WATER` unless `water_meter` gives the input),
    "flow" or "none"; a fixed `water_price` is per m³.
    """
    result = await walk_to_mapping(
        hass,
        entry,
        name=name,
        printer=device,
        status=status,
        device_type="washing_machine",
    )
    result = await configure(hass, result, mapping)
    assert result["step_id"] == "program", result.get("errors")
    result = await configure(hass, result, program or {})
    assert result["type"] is FlowResultType.MENU, result.get("errors")
    result = await configure(hass, result, {"next_step_id": source})
    result = await configure(hass, result, meter or {"entity_id": WASHER_ENERGY})
    assert result["step_id"] == "price", result.get("errors")
    result = await configure(hass, result, price_choice(price))
    result = await configure(hass, result, price_input(price))
    assert result["step_id"] == "water", result.get("errors")
    result = await configure(hass, result, {"next_step_id": f"water_{water}"})
    if water != "none":
        result = await configure(
            hass, result, water_meter or {"entity_id": WASHER_WATER}
        )
        assert result["step_id"] == "water_price", result.get("errors")
        result = await configure(
            hass,
            result,
            {"next_step_id": f"water_{price_choice(water_price)['next_step_id']}"},
        )
        result = await configure(hass, result, price_input(water_price))
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry


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
    result = await configure(hass, result, {"next_step_id": "save"})
    await hass.async_block_till_done()
    return result
