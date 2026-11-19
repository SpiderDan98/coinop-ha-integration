"""Measured material usage: a Run's Material Line Items from the Material used input."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from .devices import MAPPING, add_device, add_hub, configure, walk_to_mapping

FILAMENT = "sensor.kobra_filament_used"


async def walk_to_job(hass: HomeAssistant) -> Any:
    entry = await add_hub(hass)
    result = await configure(hass, await walk_to_mapping(hass, entry), MAPPING)
    assert result["step_id"] == "job"
    return result


async def test_the_material_used_input_is_a_length_or_a_mass(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    grams = entity_registry.async_get_or_create(
        "sensor", "printer", "grams", unit_of_measurement="g"
    )
    hass.states.async_set(grams.entity_id, STATE_UNAVAILABLE)
    hass.states.async_set(FILAMENT, "0", {"unit_of_measurement": "W"})
    result = await walk_to_job(hass)

    refused = await configure(hass, result, {"material_entity_id": FILAMENT})
    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {"material_entity_id": "not_length_or_mass"}

    # The unit comes from the entity registry while the entity is unavailable.
    accepted = await configure(hass, refused, {"material_entity_id": grams.entity_id})
    assert accepted["step_id"] == "images", accepted.get("errors")


async def test_a_material_used_attribute_asks_for_its_unit(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(FILAMENT, "idle", {"length": 1200})
    result = await walk_to_job(hass)

    result = await configure(
        hass,
        result,
        {"material_entity_id": FILAMENT, "material_attribute": "length"},
    )
    assert result["step_id"] == "material_unit"
    refused = await configure(hass, result, {"unit": "pcs"})
    assert refused["errors"] == {"unit": "not_length_or_mass"}
    result = await configure(hass, refused, {"unit": "mm"})

    assert result["step_id"] == "images", result.get("errors")


async def test_the_material_used_input_is_stored_with_the_job(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(FILAMENT, "12", {"unit_of_measurement": "m"})
    entry = await add_hub(hass)

    device = await add_device(hass, entry, job="sensor.kobra_job", material=FILAMENT)

    assert device.data["job"] == {
        "entity_id": "sensor.kobra_job",
        "attribute": None,
        "material": {"entity_id": FILAMENT, "attribute": None, "unit": "m"},
    }
