"""Slot attribution: a multi-material unit's loaded Slots pick the Materials a Run used."""

from homeassistant.core import HomeAssistant

from .devices import add_device, add_hub, configure, start_reconfigure
from .test_device_flow import suggested

SLOTS = [f"sensor.ace_slot_{number}" for number in range(1, 5)]
LOADED = "sensor.ace_loaded_slot"


async def test_the_slots_are_stored_in_order_with_the_job(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    device = await add_device(
        hass,
        entry,
        slots=[SLOTS[2], SLOTS[0]],
        colour_attribute="color_hex",
        loaded_slot=LOADED,
    )

    assert device.data["job"] == {
        "entity_id": None,
        "attribute": None,
        "material": None,
        "slots": [SLOTS[2], SLOTS[0]],
        "colour_attribute": "color_hex",
        "loaded_slot": LOADED,
    }


async def test_reconfigure_offers_the_slots_as_stored(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    device = await add_device(
        hass, entry, slots=SLOTS, colour_attribute="color", loaded_slot=LOADED
    )

    menu = await start_reconfigure(hass, entry, device)
    result = await configure(hass, menu, {"next_step_id": "job"})

    assert suggested(result, "slots") == SLOTS
    assert suggested(result, "colour_attribute") == "color"
    assert suggested(result, "loaded_slot") == LOADED
    result = await configure(hass, result, {"slots": SLOTS[:2], "loaded_slot": LOADED})
    await configure(hass, result, {"next_step_id": "save"})
    job = entry.subentries[device.subentry_id].data["job"]
    assert (job["slots"], job["colour_attribute"]) == (SLOTS[:2], None)
