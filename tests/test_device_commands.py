"""The Devices tab reads each Device's HA-side settings and keeps its panel settings."""

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .devices import STATUS, add_device, add_hub
from .stored import place_materials, stored_material
from .test_device_management import remove
from .test_persistence import restart
from .websocket import PanelClient

SETTINGS = "coinop.device_settings"
NO_SETTINGS: dict[str, Any] = {
    "tags_for_new_runs": [],
    "automatic_templates": [],
    "default_material": None,
    "cover_kind": "thumbnail",
    "doses": [],
    "program_defaults": {"default": {"doses": {}}, "programs": {}},
}


async def test_each_device_lists_its_ha_side_settings(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(
        hass,
        entry,
        name="Kobra",
        job="sensor.kobra_job",
        running_power=120,
        paused_power=10,
        price=0.30,
    )
    mini = await add_device(hass, entry, name="Mini", status="sensor.mini_status")

    result = await panel.call("coinop/devices/list")

    assert result["devices"] == [
        {
            "id": kobra.subentry_id,
            "name": "Kobra",
            "type": "3d_printer",
            "capabilities": [
                "average_power",
                "images",
                "job",
                "material",
                "part_count",
            ],
            "ha_settings": {
                "printer_device_id": None,
                "status": {"entity_id": STATUS, "attribute": None},
                "mapping": {
                    "running": ["printing"],
                    "paused": ["paused"],
                    "finished": ["finished"],
                    "cancelled": ["cancelled"],
                    "ended": ["idle"],
                    "fault": [],
                    "ignored": [],
                },
                "job": {
                    "entity_id": "sensor.kobra_job",
                    "attribute": None,
                    "material": None,
                    "planned_material": None,
                    "slots": [],
                    "colour_attribute": None,
                    "loaded_slot": None,
                },
                "images": {"thumbnail": None, "camera": None, "snapshot": False},
                "progress": {
                    "remaining_time": None,
                    "progress": None,
                    "expected_energy": None,
                },
                "consumption": {
                    "source": "estimate",
                    "running_power": 120,
                    "paused_power": 10,
                },
                "price": {"source": "fixed", "value": 0.30},
            },
            "settings": NO_SETTINGS,
            "known_programs": [],
        },
        {
            "id": mini.subentry_id,
            "name": "Mini",
            "type": "3d_printer",
            "capabilities": result["devices"][1]["capabilities"],
            "ha_settings": result["devices"][1]["ha_settings"],
            "settings": NO_SETTINGS,
            "known_programs": [],
        },
    ]
    assert result["devices"][1]["ha_settings"]["status"]["entity_id"] == (
        "sensor.mini_status"
    )


async def test_a_panel_setting_is_kept_across_restarts(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    [listed] = (await panel.call("coinop/devices/list"))["devices"]
    assert listed["settings"] == NO_SETTINGS

    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"tags_for_new_runs": ["Workshop"]},
    )
    await restart(hass, entry)

    assert result == {"settings": NO_SETTINGS | {"tags_for_new_runs": ["Workshop"]}}
    [listed] = (await panel.call("coinop/devices/list"))["devices"]
    assert listed["settings"] == NO_SETTINGS | {"tags_for_new_runs": ["Workshop"]}


async def test_an_update_leaves_settings_it_does_not_name_alone(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"tags_for_new_runs": ["Workshop"]},
    )

    result = await panel.call(
        "coinop/devices/update_settings", device_id=kobra.subentry_id, settings={}
    )

    assert result == {"settings": NO_SETTINGS | {"tags_for_new_runs": ["Workshop"]}}


async def test_an_unknown_setting_or_value_is_rejected(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)

    unknown = await panel.error(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"colour": "red"},
    )
    wrong = await panel.error(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"tags_for_new_runs": "Workshop"},
    )

    assert unknown["code"] == wrong["code"] == "invalid_format"


async def test_a_removed_device_has_no_settings_to_update(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    await remove(hass, entry, kobra)

    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"tags_for_new_runs": ["Workshop"]},
    )

    assert error["code"] == "not_found"
    assert (await panel.call("coinop/devices/list")) == {"devices": []}


async def test_a_removed_devices_settings_are_dropped(
    hass: HomeAssistant,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    mini = await add_device(hass, entry, name="Mini", status="sensor.mini_status")
    for device in (kobra, mini):
        await panel.call(
            "coinop/devices/update_settings",
            device_id=device.subentry_id,
            settings={"tags_for_new_runs": [device.title]},
        )

    await remove(hass, entry, kobra)

    assert hass_storage[SETTINGS]["data"] == {
        "devices": {mini.subentry_id: {"tags_for_new_runs": ["Mini"]}}
    }


async def test_settings_written_by_a_newer_version_are_kept(
    hass: HomeAssistant,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    newer = {"devices": {kobra.subentry_id: {"snapshot": True}}}
    hass_storage[SETTINGS] = {"version": 1, "minor_version": 9, "data": newer}
    await restart(hass, entry)

    await panel.call(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"tags_for_new_runs": ["Workshop"]},
    )

    assert hass_storage[SETTINGS]["data"]["devices"][kobra.subentry_id] == {
        "snapshot": True,
        "tags_for_new_runs": ["Workshop"],
    }


async def test_the_default_material_is_a_current_material_or_none(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(
        hass_storage, stored_material("pla"), stored_material("old", archived=True)
    )
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)

    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"default_material": "pla"},
    )
    assert result["settings"]["default_material"] == "pla"
    for material, code in (("nope", "not_found"), ("old", "not_allowed")):
        error = await panel.error(
            "coinop/devices/update_settings",
            device_id=kobra.subentry_id,
            settings={"default_material": material},
        )
        assert error["code"] == code, material
    [listed] = (await panel.call("coinop/devices/list"))["devices"]
    assert listed["settings"]["default_material"] == "pla"

    cleared = await panel.call(
        "coinop/devices/update_settings",
        device_id=kobra.subentry_id,
        settings={"default_material": None},
    )
    assert cleared["settings"]["default_material"] is None


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("coinop/devices/list", {}),
        (
            "coinop/devices/update_settings",
            {"device_id": "a", "settings": {}},
        ),
    ],
)
async def test_only_admins_read_and_change_devices(
    hass: HomeAssistant,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    command: str,
    data: dict[str, Any],
) -> None:
    await add_hub(hass)
    user = connect_panel(hass_read_only_user)

    error = await user.error(command, **data)

    assert error["code"] == "unauthorized"
