"""Set up the hub and add Devices through the real flows, the way a user does."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wattbill.const import DOMAIN

STATUS = "sensor.kobra_status"
ENERGY = "sensor.kobra_plug_energy"
POWER = "sensor.kobra_plug_power"
MAPPING = {
    "running": ["printing"],
    "paused": ["paused"],
    "finished": ["finished"],
    "cancelled": ["cancelled"],
    "ended": ["idle"],
}


async def add_hub(hass: HomeAssistant) -> ConfigEntry:
    MockConfigEntry(domain=DOMAIN, title="WattBill").add_to_hass(hass)
    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def start_add_device(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )


async def configure(hass: HomeAssistant, result: Any, user_input: Any) -> Any:
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input
    )


async def walk_to_mapping(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    name: str = "Kobra",
    status: str = STATUS,
    attribute: str | None = None,
) -> Any:
    result = await configure(hass, await start_add_device(hass, entry), {"name": name})
    assert result["step_id"] == "status"
    status_input = {"entity_id": status} | (
        {"attribute": attribute} if attribute else {}
    )
    result = await configure(hass, result, status_input)
    assert result["step_id"] == "mapping", result.get("errors")
    return result


async def walk_to_consumption(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    result = await configure(hass, await walk_to_mapping(hass, entry), MAPPING)
    assert result["type"] is FlowResultType.MENU, result.get("errors")
    return result


async def add_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    name: str = "Kobra",
    status: str = STATUS,
    attribute: str | None = None,
    mapping: dict[str, list[str]] = MAPPING,
    source: str = "estimate",
    meter: dict[str, Any] | None = None,
    running_power: float = 120,
    paused_power: float | None = None,
    price: float = 0.30,
) -> ConfigSubentry:
    """Walk Add Device to the end; returns the new Device once the entry reloaded.

    `source` picks the consumption source; Energy and Power take `meter` as input.
    """
    result = await walk_to_mapping(
        hass, entry, name=name, status=status, attribute=attribute
    )
    result = await configure(hass, result, mapping)
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
    result = await configure(hass, result, {"price": price})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    subentry = list(entry.subentries.values())[-1]
    assert subentry.title == name
    return subentry
