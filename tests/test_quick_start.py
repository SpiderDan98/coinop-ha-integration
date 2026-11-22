"""Quick Start: a Device added from a known integration's HA device in two forms."""

from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from custom_components.coinop.profiles import INTEGRATIONS

from .clock import Clock
from .devices import (
    ENERGY,
    POWER,
    PRICE,
    WASHER_ENERGY,
    add_hub,
    add_printer,
    add_washing_machine,
    configure,
    walk_to_price,
)
from .registry import (
    add_anycubic_local,
    add_home_connect,
    add_home_connect_local,
    add_miele,
    add_washdata,
)
from .test_device_flow import fields, suggested
from .test_runs import stored_runs

WATER_METER = "sensor.washing_machine_water_consumption"


def register(hass: HomeAssistant, entity_id: str, unit: str | None) -> None:
    domain, object_id = entity_id.split(".")
    er.async_get(hass).async_get_or_create(
        domain,
        "plug",
        object_id,
        suggested_object_id=object_id,
        unit_of_measurement=unit,
    )


QUICK_START_STATES = (
    "quick_start",
    "quick_start_nothing_found",
    "quick_start_all_followed",
)


async def open_quick_start_in(hass: HomeAssistant, state: str) -> Any:
    """Open Add Device with Quick Start in `state`, one of `QUICK_START_STATES`: a
    WashData washer to offer, none, or one already a Device."""
    if state != "quick_start_nothing_found":
        washer = add_washdata(hass)
    entry = await add_hub(hass)
    if state == "quick_start_all_followed":
        await quick_start(hass, entry, washer.device.id, price=0.3)
    result = await open_add_device(hass, entry)
    assert result["step_id"] == state
    return result


async def open_add_device(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )


def offered(result: Any) -> list[dict[str, str]]:
    [selector] = result["data_schema"].schema.values()
    options: list[dict[str, str]] = selector.config["options"]
    return options


async def pick(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    device_type: str | None = None,
) -> Any:
    """Open Add Device and pick the HA device in Quick Start; returns its second form.
    `device_type` answers the Device Type step of a device whose kind can't be told."""
    result = await open_add_device(hass, entry)
    assert result["step_id"] == "quick_start"
    result = await configure(hass, result, {"device": device_id})
    if device_type is not None:
        assert result["step_id"] == "quick_start_device_type", result.get("errors")
        result = await configure(hass, result, {"device_type": device_type})
    assert result["step_id"] == "quick_start_confirm", result.get("errors")
    return result


async def quick_start(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    device_type: str | None = None,
    **answers: Any,
) -> dict[str, Any]:
    """Add the HA device through Quick Start, as `device_type` if it is asked for;
    returns the new Device's data."""
    result = await configure(
        hass, await pick(hass, entry, device_id, device_type), answers
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    return dict(list(entry.subentries.values())[-1].data)


async def test_without_a_known_integrations_device_quick_start_names_those_it_knows(
    hass: HomeAssistant,
) -> None:
    add_printer(hass)
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "quick_start_nothing_found"
    assert offered(result) == [{"value": "manual", "label": "manual"}]
    assert result["description_placeholders"]["integrations"] == ", ".join(
        integration.name for integration in INTEGRATIONS.values()
    )


async def test_with_every_device_followed_quick_start_says_so(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, washer.device.id, price=0.3)

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "quick_start_all_followed"
    assert offered(result) == [{"value": "manual", "label": "manual"}]


async def test_with_its_status_used_by_another_device_quick_start_says_so(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, WASHER_ENERGY, "kWh")
    entry = await add_hub(hass)
    await add_washing_machine(hass, entry, status=washer["washer_state"])

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "quick_start_all_followed"


@pytest.mark.parametrize("state", QUICK_START_STATES)
async def test_manual_setup_leads_to_the_device_type_in_every_state(
    hass: HomeAssistant, state: str
) -> None:
    result = await open_quick_start_in(hass, state)

    result = await configure(hass, result, {"device": "manual"})

    assert result["step_id"] == "user"


async def test_quick_start_offers_the_devices_of_known_integrations(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    washer = add_washdata(hass)
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "quick_start"
    # The ACE unit has no Status of its own, so it is no Device.
    assert offered(result) == [
        {
            "value": printer.device.id,
            "label": "Anycubic Kobra S1 · Anycubic 3D Printer - Local Control",
        },
        {"value": washer.device.id, "label": "Washer · WashData"},
        {"value": "manual", "label": "manual"},
    ]
    assert suggested(result, "device") == printer.device.id


async def test_a_device_whose_status_entity_is_disabled_is_not_offered(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    washer = add_washdata(hass)
    entity_registry.async_update_entity(
        washer["washer_state"], disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "quick_start_nothing_found"


async def test_a_renamed_ha_device_is_offered_by_the_users_name(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    dr.async_get(hass).async_update_device(washer.device.id, name_by_user="Waschkeller")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert offered(result)[0]["label"] == "Waschkeller · WashData"


async def test_manual_setup_leads_to_the_device_type(hass: HomeAssistant) -> None:
    add_washdata(hass)
    entry = await add_hub(hass)

    result = await configure(
        hass, await open_add_device(hass, entry), {"device": "manual"}
    )

    assert result["step_id"] == "user"
    result = await configure(hass, result, {"device_type": "washing_machine"})
    assert result["step_id"] == "device"


async def test_the_device_type_choice_leads_back_to_quick_start(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": "manual"}
    )
    assert offered(result)[-1] == "quick_start"

    result = await configure(hass, result, {"device_type": "quick_start"})

    assert result["step_id"] == "quick_start"
    assert [option["value"] for option in offered(result)] == [
        washer.device.id,
        "manual",
    ]


async def test_back_to_quick_start_shows_it_in_the_state_it_is_in(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": "manual"}
    )

    result = await configure(hass, result, {"device_type": "quick_start"})

    assert result["step_id"] == "quick_start_nothing_found"


async def test_after_going_back_to_quick_start_a_pick_keeps_nothing_of_before(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": "manual"}
    )
    result = await configure(hass, result, {"device_type": "quick_start"})
    result = await configure(hass, result, {"device": "manual"})
    assert result["step_id"] == "user"
    result = await configure(hass, result, {"device_type": "quick_start"})

    result = await configure(hass, result, {"device": washer.device.id})
    result = await configure(hass, result, {"price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["device_type"] == "washing_machine"
    assert subentry.data["printer_device_id"] == washer.device.id


async def test_quick_start_shows_what_the_profile_found(hass: HomeAssistant) -> None:
    washer = add_washdata(hass)
    hass.states.async_set(
        washer["washer_state"], "off", {"friendly_name": "Washer State"}
    )
    entry = await add_hub(hass)

    result = await pick(hass, entry, washer.device.id)

    assert result["description_placeholders"] == {
        "device": "Washer",
        "device_type": "Washing machine",
        "integration": "WashData",
        "inputs": f"- Washer State\n- {washer['washer_program']}",
        "currency": "EUR",
    }


async def test_a_washing_machine_is_added_with_its_plugs_meter_and_a_price(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, WASHER_ENERGY, "kWh")
    entry = await add_hub(hass)

    result = await pick(hass, entry, washer.device.id)
    assert fields(result) == [
        "optional_meter",
        "price",
        "price_entity",
        "water_price",
        "pick_another_device",
    ]
    result = await configure(
        hass, result, {"optional_meter": WASHER_ENERGY, "price": 0.3}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.title == "Washer"
    assert subentry.data == {
        "device_type": "washing_machine",
        "printer_device_id": washer.device.id,
        "status": {"entity_id": washer["washer_state"], "attribute": None},
        "mapping": {
            "running": ["running", "ending"],
            "paused": ["paused", "user_paused"],
            "finished": ["finished", "anti_wrinkle", "clean"],
            "cancelled": ["interrupted", "force_stopped"],
            "ended": [],
            "fault": [],
            "ignored": ["off", "idle", "starting", "delay_wait", "unknown"],
        },
        "program": {
            "entity_id": washer["washer_program"],
            "attribute": None,
            "ignored": [
                "off",
                "starting",
                "detecting...",
                "restored...",
                "none",
                "unknown",
            ],
        },
        "progress": {"remaining_time": None},
        "consumption": {
            "source": "energy",
            "entity_id": WASHER_ENERGY,
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.3},
        "water": {"source": "none"},
    }


async def test_a_power_sensor_is_told_from_an_energy_meter_by_its_unit(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, "sensor.washer_plug_power", "W")
    entry = await add_hub(hass)

    data = await quick_start(
        hass,
        entry,
        washer.device.id,
        optional_meter="sensor.washer_plug_power",
        price=0.3,
    )

    assert data["consumption"] == {
        "source": "power",
        "entity_id": "sensor.washer_plug_power",
        "attribute": None,
        "unit": "W",
        "factor": None,
    }


async def test_a_meter_that_is_neither_energy_nor_power_is_refused(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, "sensor.washer_temperature", "°C")
    entry = await add_hub(hass)

    result = await configure(
        hass,
        await pick(hass, entry, washer.device.id),
        {"optional_meter": "sensor.washer_temperature", "price": 0.3},
    )

    assert result["errors"] == {"optional_meter": "not_energy_or_power"}
    assert suggested(result, "price") == 0.3


async def test_a_washing_machine_without_a_meter_takes_its_kwh_per_program(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, washer.device.id, price=0.3)

    assert data["consumption"] == {"source": "per_program"}


async def test_a_water_price_takes_the_litres_per_program(hass: HomeAssistant) -> None:
    washer = add_home_connect(hass)
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, washer.device.id, price=0.3, water_price=4.0)

    assert data["water"] == {"source": "per_program"}
    assert data["water_price"] == {"source": "fixed", "value": 4.0}


async def test_mieles_own_meters_need_no_meter_from_the_user(
    hass: HomeAssistant,
) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)

    result = await pick(hass, entry, washer.device.id)
    assert fields(result) == [
        "price",
        "price_entity",
        "water_price",
        "pick_another_device",
    ]
    result = await configure(hass, result, {"price": 0.3, "water_price": 4.0})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["consumption"] == {
        "source": "energy",
        "entity_id": washer["current_energy_consumption"],
        "attribute": None,
        "unit": "kWh",
        "factor": None,
    }
    assert subentry.data["water"] == {
        "source": "meter",
        "entity_id": WATER_METER,
        "attribute": None,
        "unit": "L",
        "factor": None,
    }
    assert subentry.data["water_price"] == {"source": "fixed", "value": 4.0}


async def test_without_a_water_price_no_water_is_recorded(hass: HomeAssistant) -> None:
    washer = add_miele(hass)
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, washer.device.id, price=0.3)

    assert data["water"] == {"source": "none"}
    assert "water_price" not in data


async def test_a_printer_is_added_with_every_input_its_profile_finds(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)

    result = await pick(hass, entry, printer.device.id)
    assert fields(result) == ["meter", "price", "price_entity", "pick_another_device"]
    result = await configure(hass, result, {"meter": POWER, "price": 0.3})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.title == "Anycubic Kobra S1"
    data = subentry.data
    assert data["device_type"] == "3d_printer"
    assert data["status"]["entity_id"] == printer["print_event"]
    assert data["mapping"]["running"] == ["started", "resumed"]
    assert data["job"] == {
        "entity_id": printer["filename"],
        "attribute": None,
        "material": {
            "entity_id": printer["filament_used"],
            "attribute": "length_mm",
            "unit": "mm",
        },
        "slots": [printer[f"ace0_slot_{number}"] for number in range(1, 5)],
        "colour_attribute": "color",
        "loaded_slot": printer["ace0_loaded_slot"],
    }
    assert data["images"] == {
        "thumbnail": printer["object_top_view"],
        "camera": printer["camera"],
        "snapshot": True,
    }
    assert data["progress"] == {"remaining_time": printer["time_remaining"]}
    assert data["consumption"] == {
        "source": "power",
        "entity_id": POWER,
        "attribute": None,
        "unit": "W",
        "factor": None,
        "running_power": None,
    }


async def test_inputs_a_profile_doesnt_find_are_stored_as_unused(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass, images=())
    registry = er.async_get(hass)
    for key in ("filename", "filament_used", "camera", "ace0_slot_1", "time_remaining"):
        registry.async_remove(printer[key])
    register(hass, ENERGY, "kWh")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, printer.device.id, meter=ENERGY, price=0.3)

    assert data["job"] == {
        "entity_id": None,
        "attribute": None,
        "material": None,
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": printer["ace0_loaded_slot"],
    }
    assert data["images"] == {"thumbnail": None, "camera": None, "snapshot": False}
    assert data["progress"] == {"remaining_time": None}


async def test_a_printer_needs_a_meter(hass: HomeAssistant) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)

    result = await pick(hass, entry, printer.device.id)
    result = await configure(hass, result, {"price": 0.3})

    assert result["errors"] == {"meter": "meter_required"}
    assert suggested(result, "price") == 0.3


async def test_the_device_type_step_leads_back_to_the_device_list(
    hass: HomeAssistant,
) -> None:
    appliance = add_home_connect_local(hass)
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": appliance.device.id}
    )
    assert result["step_id"] == "quick_start_device_type"
    assert offered(result)[-1] == "pick_another_device"

    result = await configure(hass, result, {"device_type": "pick_another_device"})

    assert result["step_id"] == "quick_start"
    assert [option["value"] for option in offered(result)] == [
        appliance.device.id,
        "manual",
    ]


async def test_the_meter_and_prices_step_leads_back_with_nothing_filled_in(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    entry = await add_hub(hass)
    result = await pick(hass, entry, printer.device.id)
    assert fields(result)[-1] == "pick_another_device"

    result = await configure(hass, result, {"pick_another_device": True})

    assert result["step_id"] == "quick_start"


async def test_after_picking_another_device_nothing_of_the_first_is_kept(
    hass: HomeAssistant,
) -> None:
    printer = add_anycubic_local(hass)
    appliance = add_home_connect_local(hass)
    register(hass, POWER, "W")
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_add_device(hass, entry), {"device": appliance.device.id}
    )
    result = await configure(hass, result, {"device_type": "dishwasher"})
    result = await configure(hass, result, {"pick_another_device": True})

    data = await quick_start(hass, entry, printer.device.id, meter=POWER, price=0.3)

    assert data["device_type"] == "3d_printer"
    assert data["printer_device_id"] == printer.device.id
    assert "program" not in data
    assert "water" not in data
    assert list(entry.subentries.values())[-1].title == "Anycubic Kobra S1"


@pytest.mark.parametrize("answers", [{}, {"price": 0.3, "price_entity": PRICE}])
async def test_the_price_is_either_fixed_or_an_entity(
    hass: HomeAssistant, answers: dict[str, Any]
) -> None:
    washer = add_washdata(hass)
    register(hass, PRICE, "EUR/kWh")
    entry = await add_hub(hass)

    result = await configure(hass, await pick(hass, entry, washer.device.id), answers)

    assert result["errors"] == {"price": "one_price"}


async def test_a_price_entity_gives_a_dynamic_price(hass: HomeAssistant) -> None:
    washer = add_washdata(hass)
    register(hass, PRICE, "EUR/kWh")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, washer.device.id, price_entity=PRICE)

    assert data["price"] == {
        "source": "entity",
        "entity_id": PRICE,
        "attribute": None,
        "unit": "EUR/kWh",
        "factor": None,
    }


async def test_a_price_entity_in_an_unknown_unit_is_refused(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, PRICE, "points")
    entry = await add_hub(hass)

    result = await configure(
        hass, await pick(hass, entry, washer.device.id), {"price_entity": PRICE}
    )

    assert result["errors"] == {"price_entity": "unknown_price_unit"}


async def test_the_prices_of_the_last_device_are_pre_filled(
    hass: HomeAssistant,
) -> None:
    first = add_miele(hass)
    second = add_washdata(hass)
    entry = await add_hub(hass)
    await quick_start(hass, entry, first.device.id, price=0.27, water_price=4.2)

    result = await pick(hass, entry, second.device.id)

    assert suggested(result, "price") == 0.27
    assert suggested(result, "price_entity") is None
    assert suggested(result, "water_price") == 4.2


async def test_the_price_entity_of_the_last_device_is_pre_filled_and_kept_whole(
    hass: HomeAssistant,
) -> None:
    washer = add_washdata(hass)
    register(hass, PRICE, "points")
    entry = await add_hub(hass)
    result = await walk_to_price(hass, entry)
    result = await configure(hass, result, {"next_step_id": "price_entity"})
    result = await configure(hass, result, {"entity_id": PRICE})
    result = await configure(hass, result, {"entity_id": PRICE, "factor": 0.01})
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    [first] = entry.subentries.values()

    result = await pick(hass, entry, washer.device.id)
    assert suggested(result, "price") is None
    assert suggested(result, "price_entity") == PRICE
    result = await configure(hass, result, {"price_entity": PRICE})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert list(entry.subentries.values())[-1].data["price"] == first.data["price"]


async def test_a_device_added_by_quick_start_records_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    washer = add_washdata(hass)
    register(hass, WASHER_ENERGY, "kWh")
    hass.states.async_set(washer["washer_state"], "off")
    hass.states.async_set(washer["washer_program"], "off")
    hass.states.async_set(WASHER_ENERGY, "10", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    await quick_start(
        hass, entry, washer.device.id, optional_meter=WASHER_ENERGY, price=0.3
    )

    hass.states.async_set(washer["washer_state"], "running")
    hass.states.async_set(washer["washer_program"], "Cotton 60°")
    await clock.advance(hours=1)
    hass.states.async_set(WASHER_ENERGY, "11", {"unit_of_measurement": "kWh"})
    hass.states.async_set(washer["washer_state"], "finished")
    await clock.advance(minutes=10)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "completed"
    assert run["program"] == "Cotton 60°"
    [electricity] = [
        item for item in run["line_items"] if item["kind"] == "electricity"
    ]
    assert electricity["quantity"] == pytest.approx(1)
    assert electricity["amount"] == pytest.approx(0.3)
