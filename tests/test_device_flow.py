"""Add Device: name, Status entity, Status mapping, job, consumption estimate, price."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from .devices import MAPPING, STATUS, add_device, add_hub, configure, walk_to_mapping


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

    assert result["type"] is FlowResultType.MENU


async def test_a_value_mapped_to_two_targets_is_refused(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(hass, entry)

    result = await configure(hass, result, MAPPING | {"ended": ["idle", "finished"]})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "value_mapped_twice"}
