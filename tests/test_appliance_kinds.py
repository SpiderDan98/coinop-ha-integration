"""Quick Start adds an HA device as the Device Type its integration says it is, asks
where the integration doesn't say, and leaves out what is no Device Type."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .devices import WASHER_ENERGY, add_hub, configure
from .test_device_flow import fields
from .test_quick_start import offered, open_add_device, pick, quick_start
from .test_washer_profiles import WASHDATA_PLACEHOLDERS, walk_pre_filled
from .washers import add_washdata

WASHDATA_MAPPING = {
    "running": ["running", "ending"],
    "paused": ["paused", "user_paused"],
    "finished": ["finished", "anti_wrinkle", "clean"],
    "cancelled": ["interrupted", "force_stopped"],
    "ended": [],
    "fault": [],
    "ignored": ["off", "idle", "starting", "delay_wait", "unknown"],
}


@pytest.mark.parametrize(
    ("kind", "device_type"),
    [
        ("washing_machine", "washing_machine"),
        ("washer_dryer", "washing_machine"),
        ("dryer", "tumble_dryer"),
        ("dishwasher", "dishwasher"),
    ],
)
async def test_a_washdata_device_is_added_as_the_kind_picked_in_washdata(
    hass: HomeAssistant, kind: str, device_type: str
) -> None:
    appliance = add_washdata(hass, kind)
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, appliance.device.id, price=0.3)

    assert data["device_type"] == device_type
    assert data["status"] == {"entity_id": appliance["washer_state"], "attribute": None}
    assert data["mapping"] == WASHDATA_MAPPING
    assert data["program"] == {
        "entity_id": appliance["washer_program"],
        "attribute": None,
        "ignored": WASHDATA_PLACEHOLDERS,
    }


async def test_a_kind_changed_in_washdata_later_counts(hass: HomeAssistant) -> None:
    appliance = add_washdata(hass, "washing_machine", changed_to="dryer")
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, appliance.device.id, price=0.3)

    assert data["device_type"] == "tumble_dryer"


async def test_a_washdata_entry_from_before_it_kept_a_kind_is_a_washing_machine(
    hass: HomeAssistant,
) -> None:
    appliance = add_washdata(hass, None)
    entry = await add_hub(hass)

    data = await quick_start(hass, entry, appliance.device.id, price=0.3)

    assert data["device_type"] == "washing_machine"


@pytest.mark.parametrize("kind", ["generic", "other"])
async def test_a_washdata_device_of_a_generic_kind_is_asked_its_device_type(
    hass: HomeAssistant, kind: str
) -> None:
    plug = add_washdata(hass, kind, name="Plug")
    entry = await add_hub(hass)
    result = await open_add_device(hass, entry)
    assert offered(result)[0] == {"value": plug.device.id, "label": "Plug · WashData"}

    result = await configure(hass, result, {"device": plug.device.id})

    assert result["step_id"] == "quick_start_device_type"
    assert offered(result) == [
        "washing_machine",
        "dishwasher",
        "tumble_dryer",
        "coffee_machine",
        "oven",
    ]
    assert result["description_placeholders"] == {
        "device": "Plug",
        "integration": "WashData",
    }
    result = await configure(hass, result, {"device_type": "oven"})
    assert result["step_id"] == "quick_start_confirm"
    result = await configure(hass, result, {"price": 0.3})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.title == "Plug"
    assert subentry.data == {
        "device_type": "oven",
        "printer_device_id": plug.device.id,
        "status": {"entity_id": plug["washer_state"], "attribute": None},
        "mapping": WASHDATA_MAPPING,
        "program": {
            "entity_id": plug["washer_program"],
            "attribute": None,
            "ignored": WASHDATA_PLACEHOLDERS,
        },
        "consumption": {"source": "per_program"},
        "price": {"source": "fixed", "value": 0.3},
    }


async def test_a_washdata_pump_is_no_device_type_and_not_offered(
    hass: HomeAssistant,
) -> None:
    add_washdata(hass, "pump", name="Sump pump")
    washer = add_washdata(hass)
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert offered(result) == [
        {"value": washer.device.id, "label": "Washer · WashData"},
        {"value": "manual", "label": "manual"},
    ]


async def test_with_nothing_but_a_pump_add_device_starts_at_the_device_type(
    hass: HomeAssistant,
) -> None:
    add_washdata(hass, "pump", name="Sump pump")
    entry = await add_hub(hass)

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "user"


async def test_a_dishwasher_followed_as_a_washing_machine_is_not_offered_again(
    hass: HomeAssistant,
) -> None:
    dishwasher = add_washdata(hass, "dishwasher")
    hass.states.async_set(WASHER_ENERGY, "100", {"unit_of_measurement": "kWh"})
    entry = await add_hub(hass)
    _, device = await walk_pre_filled(
        hass, entry, dishwasher, energy={"entity_id": WASHER_ENERGY}
    )
    assert device.data["device_type"] == "washing_machine"

    result = await open_add_device(hass, entry)

    assert result["step_id"] == "user"


@pytest.mark.parametrize(
    ("language", "named"), [("en", "Dishwasher"), ("de", "Spülmaschine")]
)
async def test_the_second_form_names_the_device_type_in_the_configured_language(
    hass: HomeAssistant, language: str, named: str
) -> None:
    hass.config.language = language
    dishwasher = add_washdata(hass, "dishwasher")
    entry = await add_hub(hass)

    result = await pick(hass, entry, dishwasher.device.id)

    assert result["description_placeholders"]["device_type"] == named


async def test_the_second_form_names_the_device_type_the_user_chose(
    hass: HomeAssistant,
) -> None:
    plug = add_washdata(hass, "generic")
    entry = await add_hub(hass)

    result = await pick(hass, entry, plug.device.id, "coffee_machine")

    assert result["description_placeholders"]["device_type"] == "Coffee machine"


@pytest.mark.parametrize(
    ("kind", "chosen", "device_type", "asked"),
    [
        ("dishwasher", None, "dishwasher", ["water_price"]),
        ("dryer", None, "tumble_dryer", []),
        ("generic", "coffee_machine", "coffee_machine", ["water_price"]),
        ("generic", "oven", "oven", []),
    ],
)
async def test_the_second_form_asks_for_a_water_price_only_for_a_device_type_with_water(
    hass: HomeAssistant,
    kind: str,
    chosen: str | None,
    device_type: str,
    asked: list[str],
) -> None:
    appliance = add_washdata(hass, kind)
    entry = await add_hub(hass)

    result = await pick(hass, entry, appliance.device.id, chosen)
    assert fields(result) == ["optional_meter", "price", "price_entity", *asked]
    result = await configure(hass, result, {"price": 0.3} | dict.fromkeys(asked, 4.0))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [subentry] = entry.subentries.values()
    assert subentry.data["device_type"] == device_type
    assert ("water" in subentry.data, "water_price" in subentry.data) == (
        bool(asked),
        bool(asked),
    )
