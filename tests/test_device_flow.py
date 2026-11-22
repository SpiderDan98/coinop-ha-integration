"""Add Device: name, Status entity, Status mapping, job, images, consumption, price."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .devices import (
    ENERGY,
    MAPPING,
    POWER,
    STATUS,
    add_device,
    add_hub,
    add_printer,
    answer_electricity,
    answer_progress,
    configure,
    open_device_types,
    other_input,
    start_add_device,
    walk_to_consumption,
    walk_to_mapping,
)


def fields(result: Any) -> list[str]:
    return [str(key) for key in result["data_schema"].schema]


def offered(result: Any, target: str = "running") -> list[str]:
    [selector] = [
        value for key, value in result["data_schema"].schema.items() if key == target
    ]
    options: list[str] = selector.config["options"]
    return options


async def test_event_types_are_offered_while_the_printer_is_off(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    event = entity_registry.async_get_or_create(
        "event",
        "printer",
        "print-status",
        suggested_object_id="kobra_print",
        capabilities={"event_types": ["printing", "paused", "finished"]},
    )
    hass.states.async_set(event.entity_id, STATE_UNAVAILABLE)
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry, status=event.entity_id)

    assert offered(result) == ["printing", "paused", "finished"]
    assert offered(result, "ignored") == ["printing", "paused", "finished"]


async def test_enum_options_are_offered(hass: HomeAssistant) -> None:
    hass.states.async_set(
        STATUS, "idle", {"device_class": "enum", "options": ["idle", "printing"]}
    )
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry)

    assert offered(result) == ["idle", "printing"]


async def test_on_and_off_are_offered_for_a_binary_sensor(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.kobra_printing", STATE_UNAVAILABLE)
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry, status="binary_sensor.kobra_printing")

    assert offered(result) == ["on", "off"]


async def test_the_current_state_is_offered_otherwise(hass: HomeAssistant) -> None:
    hass.states.async_set(STATUS, "printing")
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry)

    assert offered(result) == ["printing"]


async def test_the_current_attribute_value_is_offered(hass: HomeAssistant) -> None:
    hass.states.async_set(STATUS, "on", {"job_state": "printing"})
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry, attribute="job_state")

    assert offered(result) == ["printing"]


async def test_a_missing_status_entity_never_blocks_setup(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_to_mapping(hass, entry, status="sensor.not_there_yet")
    assert offered(result) == []
    await add_device(hass, entry, status="sensor.not_there_yet")

    assert [s.title for s in entry.subentries.values()] == ["Kobra"]


async def test_add_device_creates_a_device_subentry(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry, name="Kobra")

    assert subentry.subentry_type == "device"
    assert [s.title for s in entry.subentries.values()] == ["Kobra"]


async def test_add_device_stores_the_device_type(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry)

    assert subentry.data["device_type"] == "3d_printer"


async def test_add_device_adds_further_devices(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    await add_device(hass, entry, name="Kobra")
    await add_device(hass, entry, name="Voron", status="sensor.voron_status")

    assert [s.title for s in entry.subentries.values()] == ["Kobra", "Voron"]


async def test_mapping_without_a_running_value_is_refused(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)

    result = await configure(hass, result, MAPPING | {"running": []})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_running_value"}


async def test_mapping_without_any_ending_value_is_refused(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)

    result = await configure(
        hass, result, {"running": ["printing"], "paused": ["paused"]}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_ending_value"}


async def test_one_ending_value_is_enough(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)

    result = await configure(hass, result, {"running": ["on"], "ended": ["off"]})

    assert result["step_id"] == "job"


async def test_the_job_name_is_optional(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)
    result = await configure(hass, result, MAPPING)

    result = await configure(hass, result, {})

    assert result["step_id"] == "images"


async def test_a_value_mapped_to_two_targets_is_refused(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)

    result = await configure(hass, result, MAPPING | {"ended": ["idle", "finished"]})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "value_mapped_twice"}


async def test_the_consumption_source_is_energy_power_estimate_or_none(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await walk_to_consumption(hass, entry)

    assert result["menu_options"] == ["energy", "power", "estimate", "none"]
    result = await configure(hass, result, {"next_step_id": "energy"})
    assert fields(result) == ["entity_id", "attribute"]


async def test_the_meter_unit_comes_from_the_entity_registry(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    meter = entity_registry.async_get_or_create(
        "sensor", "plug", "energy", unit_of_measurement="Wh"
    )
    hass.states.async_set(meter.entity_id, STATE_UNAVAILABLE)
    entry = await add_hub(hass)

    result = await walk_to_consumption(hass, entry)
    result = await configure(hass, result, {"next_step_id": "energy"})
    result = await configure(hass, result, {"entity_id": meter.entity_id})

    assert result["step_id"] == "price"


async def test_a_power_sensor_takes_an_optional_average_power_for_gaps(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(POWER, "0", {"unit_of_measurement": "kW"})
    entry = await add_hub(hass)

    result = await walk_to_consumption(hass, entry)
    result = await configure(hass, result, {"next_step_id": "power"})
    assert fields(result) == ["entity_id", "attribute", "running_power"]
    result = await configure(hass, result, {"entity_id": POWER})

    assert result["step_id"] == "price"


async def test_a_meter_without_a_recognisable_unit_needs_a_conversion_factor(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(ENERGY, "12", {"unit_of_measurement": "pulses"})
    entry = await add_hub(hass)
    result = await walk_to_consumption(hass, entry)
    result = await configure(hass, result, {"next_step_id": "energy"})

    result = await configure(hass, result, {"entity_id": ENERGY})
    assert result["errors"] == {"entity_id": "unknown_unit"}
    assert fields(result) == ["entity_id", "attribute", "factor"]
    result = await configure(hass, result, {"entity_id": ENERGY, "factor": 0.001})

    assert result["step_id"] == "price"


async def test_a_power_sensor_must_report_power_not_energy(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(POWER, "12", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    result = await walk_to_consumption(hass, entry)
    result = await configure(hass, result, {"next_step_id": "power"})

    result = await configure(hass, result, {"entity_id": POWER})

    assert result["errors"] == {"entity_id": "unknown_unit"}


async def test_a_meter_attribute_asks_for_its_unit(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.kobra_plug", "on", {"total_energy": 3.2})
    entry = await add_hub(hass)
    result = await walk_to_consumption(hass, entry)
    result = await configure(hass, result, {"next_step_id": "energy"})

    result = await configure(
        hass, result, {"entity_id": "switch.kobra_plug", "attribute": "total_energy"}
    )
    assert result["step_id"] == "energy_unit"
    assert offered(result, "unit")[:3] == ["Wh", "kWh", "MWh"]
    result = await configure(hass, result, {"unit": "pulses"})
    assert result["errors"] == {"unit": "unknown_unit"}
    assert fields(result) == ["unit", "factor"]
    result = await configure(hass, result, {"unit": "kWh"})

    assert result["step_id"] == "price"


def suggested(result: Any, field: str) -> Any:
    [key] = [key for key in result["data_schema"].schema if key == field]
    return (key.description or {}).get("suggested_value")


async def test_picking_the_printers_ha_device_pre_fills_the_name(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass, "Kobra S1")
    entry = await add_hub(hass)

    result = await start_add_device(hass, entry, printer=printer.id)

    assert suggested(result, "name") == "Kobra S1"


async def test_the_printers_ha_device_is_optional(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    result = await start_add_device(hass, entry)

    assert suggested(result, "name") is None


async def test_entity_pickers_are_not_limited_to_the_printers_ha_device(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)

    result = await configure(
        hass, await start_add_device(hass, entry, printer=printer.id), {"name": "S1"}
    )

    assert result["step_id"] == "status"
    [selector] = [
        value
        for key, value in result["data_schema"].schema.items()
        if key == "entity_id"
    ]
    assert not selector.config.get("filter")
    assert not selector.config.get("include_entities")


async def test_a_status_entity_used_by_another_device_is_refused(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, name="Kobra")
    result = await configure(
        hass, await start_add_device(hass, entry), {"name": "Kobra again"}
    )

    result = await configure(hass, result, {"entity_id": STATUS})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"entity_id": "status_already_used"}


@pytest.mark.parametrize(
    ("device_type", "step"),
    [("3d_printer", "device"), ("robotic_mower", "device_without_profile")],
)
async def test_the_ha_device_step_leads_back_to_the_device_type(
    hass: HomeAssistant, device_type: str, step: str
) -> None:
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_device_types(hass, entry), {"device_type": device_type}
    )
    assert result["step_id"] == step

    result = await configure(hass, result, {"change_device_type": True})

    assert result["step_id"] == "user"


async def test_a_device_type_chosen_after_going_back_keeps_nothing_of_the_first(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)
    result = await configure(
        hass, await open_device_types(hass, entry), {"device_type": "other"}
    )
    result = await configure(hass, result, other_input("Kiln", ["program", "water"]))
    result = await configure(
        hass, result, {"device": printer.id, "change_device_type": True}
    )
    assert result["step_id"] == "user"

    result = await configure(hass, result, {"device_type": "robotic_mower"})
    result = await configure(hass, result, {})
    result = await configure(hass, result, {"name": "Mower"})
    result = await configure(hass, result, {"entity_id": STATUS})
    result = await configure(hass, result, MAPPING)
    result = await answer_progress(hass, result)
    result = await answer_electricity(hass, result, "none", None, 0)

    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    [subentry] = entry.subentries.values()
    assert sorted(subentry.data) == [
        "consumption",
        "device_type",
        "mapping",
        "printer_device_id",
        "progress",
        "status",
    ]
    assert subentry.data["device_type"] == "robotic_mower"
    assert subentry.data["printer_device_id"] is None


REMAINING = "sensor.kobra_time_remaining"


@pytest.mark.parametrize(
    "device_type",
    [
        "3d_printer",
        "washing_machine",
        "dishwasher",
        "tumble_dryer",
        "coffee_machine",
        "oven",
        "ev_charger",
        "robotic_mower",
        "other",
    ],
)
async def test_every_device_is_asked_for_its_remaining_time_before_its_electricity(
    hass: HomeAssistant, device_type: str
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass,
        entry,
        device_type=device_type,
        other=other_input("Kiln") if device_type == "other" else None,
    )
    result = await configure(hass, result, MAPPING)
    while result["step_id"] != "progress":
        assert result["type"] is FlowResultType.FORM, result["step_id"]
        result = await configure(hass, result, {})

    assert fields(result) == ["remaining_time"]
    result = await configure(hass, result, {"remaining_time": REMAINING})
    assert result["step_id"] == "consumption"


async def test_the_remaining_time_is_stored_with_the_device(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    timed = await add_device(hass, entry, remaining_time=REMAINING)
    untimed = await add_device(hass, entry, name="Voron", status="sensor.voron")

    assert timed.data["progress"] == {"remaining_time": REMAINING}
    assert untimed.data["progress"] == {"remaining_time": None}
