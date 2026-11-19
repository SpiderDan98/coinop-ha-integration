"""Electricity price: a fixed value or a price entity, each kWh at the price that applied."""

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .devices import PRICE, add_device, add_hub, configure, walk_to_price
from .test_device_flow import fields, suggested


async def set_price(
    hass: HomeAssistant, value: float | str, unit: str = "EUR/kWh"
) -> None:
    hass.states.async_set(PRICE, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def test_the_price_is_a_fixed_value_or_a_price_entity(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_to_price(hass, entry)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["fixed_price", "price_entity"]


async def test_a_price_entity_with_a_price_per_kwh_is_accepted(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, STATE_UNAVAILABLE, "ct/kWh")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})
    assert fields(result) == ["entity_id", "attribute"]

    result = await configure(hass, result, {"entity_id": PRICE})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"] == {
        "source": "entity",
        "entity_id": PRICE,
        "attribute": None,
        "unit": "ct/kWh",
        "factor": None,
    }


async def test_a_price_entity_without_a_recognisable_unit_needs_a_conversion_factor(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 25, "points")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(hass, result, {"entity_id": PRICE})
    assert result["errors"] == {"entity_id": "unknown_unit"}
    assert fields(result) == ["entity_id", "attribute", "factor"]
    result = await configure(hass, result, {"entity_id": PRICE, "factor": 0.01})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"]["factor"] == 0.01


async def test_a_price_in_another_currency_is_not_recognised(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 0.3, "USD/kWh")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(hass, result, {"entity_id": PRICE})

    assert result["errors"] == {"entity_id": "unknown_unit"}


async def test_a_price_attribute_asks_for_its_unit(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.tariff", "high", {"price": 31.2})
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})

    result = await configure(
        hass, result, {"entity_id": "sensor.tariff", "attribute": "price"}
    )
    assert result["step_id"] == "price_unit"
    result = await configure(hass, result, {"unit": "pts"})
    assert result["errors"] == {"unit": "unknown_unit"}
    assert fields(result) == ["unit", "factor"]
    result = await configure(hass, result, {"unit": "ct/kWh"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["price"]["unit"] == "ct/kWh"


async def test_the_first_devices_price_is_empty(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)

    result = await configure(hass, result, {"next_step_id": "fixed_price"})

    assert suggested(result, "price") is None


async def test_a_new_devices_fixed_price_is_pre_filled_from_the_last_device(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, price=0.27)
    await add_device(hass, entry, name="Voron", status="sensor.voron", price=0.31)
    result = await walk_to_price(hass, entry, status="sensor.prusa")

    result = await configure(hass, result, {"next_step_id": "fixed_price"})

    assert suggested(result, "price") == 0.31


async def test_a_new_devices_price_entity_is_pre_filled_from_the_last_device(
    hass: HomeAssistant,
) -> None:
    await set_price(hass, 0.3)
    entry = await add_hub(hass)
    await add_device(hass, entry, price={"entity_id": PRICE})
    result = await walk_to_price(hass, entry, status="sensor.voron")

    result = await configure(hass, result, {"next_step_id": "price_entity"})

    assert suggested(result, "entity_id") == PRICE
