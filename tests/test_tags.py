"""Tags group Runs across Devices and periods; they never touch a cost."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .clock import Clock
from .devices import add_device, add_hub
from .stored import place_runs, place_tags, stored_run
from .test_run_event import record_events
from .test_runs import set_status, stored_runs
from .test_sensors import CURRENT, LAST, print_runs, state_of
from .websocket import PanelClient


def catalogue(hass_storage: dict[str, Any]) -> list[str]:
    tags: list[str] = hass_storage["wattbill.catalog"]["data"]["tags"]
    return tags


async def test_typing_a_new_name_creates_the_tag_and_the_run_shows_tags_alphabetically(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("helmet"))
    await add_hub(hass)

    result = await panel.call(
        "wattbill/runs/update", run_id="helmet", tags=["  gift ", "Cosplay helmet"]
    )

    assert result["run"]["tags"] == ["Cosplay helmet", "gift"]
    [stored] = stored_runs(hass_storage)
    assert stored["tags"] == ["Cosplay helmet", "gift"]
    assert catalogue(hass_storage) == ["Cosplay helmet", "gift"]


async def test_a_name_differing_only_in_case_is_the_existing_tag(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("helmet"), stored_run("vase"))
    await add_hub(hass)
    await panel.call("wattbill/runs/update", run_id="helmet", tags=["Gift"])

    result = await panel.call(
        "wattbill/runs/update", run_id="vase", tags=["gift", "GIFT"]
    )

    assert result["run"]["tags"] == ["Gift"]
    assert catalogue(hass_storage) == ["Gift"]


async def test_a_tag_name_is_at_most_40_characters_and_not_blank(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("helmet"))
    await add_hub(hass)

    accepted = await panel.call(
        "wattbill/runs/update", run_id="helmet", tags=[f" {'x' * 40} "]
    )
    errors = [
        await panel.error("wattbill/runs/update", run_id="helmet", tags=[name])
        for name in ("x" * 41, "   ")
    ]

    assert accepted["run"]["tags"] == ["x" * 40]
    assert [error["code"] for error in errors] == ["invalid_format"] * 2
    assert catalogue(hass_storage) == ["x" * 40]


async def test_open_panels_receive_the_tag_catalogue(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, stored_run("helmet"))
    await add_hub(hass)
    await panel.subscribe("wattbill/catalog/subscribe")
    first = await panel.event()

    await panel.call("wattbill/runs/update", run_id="helmet", tags=["Gift", "Cosplay"])

    assert first["tags"] == []
    assert await panel.event() == {"tags": ["Cosplay", "Gift"]}


async def tagged(
    hass: HomeAssistant, hass_storage: dict[str, Any], **runs: list[str]
) -> ConfigEntry:
    """Set up WattBill with one ended Run per keyword, carrying those Tags."""
    place_runs(
        hass_storage, *(stored_run(run_id, tags=tags) for run_id, tags in runs.items())
    )
    place_tags(hass_storage, *{tag for tags in runs.values() for tag in tags})
    return await add_hub(hass)


def run_tags(hass_storage: dict[str, Any]) -> dict[str, list[str]]:
    return {run["id"]: run["tags"] for run in stored_runs(hass_storage)}


async def test_a_rename_changes_the_tag_on_every_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(
        hass, hass_storage, helmet=["Cosplay", "gift"], vase=["gift"], hook=["Spare"]
    )
    await panel.subscribe("wattbill/runs/subscribe")
    await panel.event()

    result = await panel.call("wattbill/tags/rename", tag="gift", name=" Present ")

    assert result == {"tag": "Present"}
    assert run_tags(hass_storage) == {
        "helmet": ["Cosplay", "Present"],
        "vase": ["Present"],
        "hook": ["Spare"],
    }
    assert catalogue(hass_storage) == ["Cosplay", "Present", "Spare"]
    changes = [await panel.event(), await panel.event()]
    assert [(c["change"], c["run"]["id"], c["run"]["tags"]) for c in changes] == [
        ("updated", "helmet", ["Cosplay", "Present"]),
        ("updated", "vase", ["Present"]),
    ]


async def test_a_rename_may_change_only_the_case(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(hass, hass_storage, vase=["gift"])

    result = await panel.call("wattbill/tags/rename", tag="gift", name="Gift")

    assert result == {"tag": "Gift"}
    assert run_tags(hass_storage) == {"vase": ["Gift"]}
    assert catalogue(hass_storage) == ["Gift"]


async def test_renaming_to_an_existing_name_merges_the_tags_without_duplicates(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(
        hass,
        hass_storage,
        helmet=["Gift", "Present"],
        vase=["Present"],
        hook=["Gift"],
    )

    result = await panel.call("wattbill/tags/rename", tag="Present", name="gift")

    assert result == {"tag": "Gift"}
    assert run_tags(hass_storage) == {
        "helmet": ["Gift"],
        "vase": ["Gift"],
        "hook": ["Gift"],
    }
    assert catalogue(hass_storage) == ["Gift"]


async def test_deleting_a_tag_removes_it_from_every_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(hass, hass_storage, helmet=["Cosplay", "Gift"], vase=["Gift"])

    result = await panel.call("wattbill/tags/delete", tag="gift")

    assert result == {}
    assert run_tags(hass_storage) == {"helmet": ["Cosplay"], "vase": []}
    assert catalogue(hass_storage) == ["Cosplay"]


async def test_a_tag_that_does_not_exist_cannot_be_renamed_or_deleted(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(hass, hass_storage, vase=["Gift"])

    errors = [
        await panel.error("wattbill/tags/rename", tag="Cosplay", name="Costume"),
        await panel.error("wattbill/tags/delete", tag="Cosplay"),
        await panel.error("wattbill/tags/rename", tag="Gift", name=" "),
    ]

    assert [error["code"] for error in errors] == [
        "not_found",
        "not_found",
        "invalid_format",
    ]
    assert catalogue(hass_storage) == ["Gift"]


async def test_tags_outlive_their_runs_until_deleted(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await tagged(hass, hass_storage, helmet=["Cosplay"], vase=["Gift"])

    await panel.call("wattbill/runs/delete", run_ids=["helmet"])
    await panel.call("wattbill/runs/update", run_id="vase", tags=[])

    assert catalogue(hass_storage) == ["Cosplay", "Gift"]


async def set_new_run_tags(
    panel: PanelClient, device: ConfigSubentry, tags: list[str]
) -> Any:
    result = await panel.call(
        "wattbill/devices/update_settings",
        device_id=device.subentry_id,
        settings={"tags_for_new_runs": tags},
    )
    return result["settings"]["tags_for_new_runs"]


async def test_every_run_starting_on_a_device_gets_its_tags_for_new_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await tagged(hass, hass_storage, vase=["Gift"])
    kobra = await add_device(hass, entry)
    fired = record_events(hass)

    tags = await set_new_run_tags(panel, kobra, ["gift", " Batch 7 "])
    await print_runs(hass, clock, [1, 1])

    assert tags == ["Batch 7", "Gift"]
    assert catalogue(hass_storage) == ["Batch 7", "Gift"]
    assert [
        tags for run_id, tags in run_tags(hass_storage).items() if run_id != "vase"
    ] == [
        ["Batch 7", "Gift"],
        ["Batch 7", "Gift"],
    ]
    assert [event["tags"] for event in fired] == [["Batch 7", "Gift"]] * 4


async def test_a_device_without_tags_for_new_runs_starts_untagged_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    [listed] = (await panel.call("wattbill/devices/list"))["devices"]

    await set_status(hass, "printing")

    assert listed["settings"]["tags_for_new_runs"] == []
    assert state_of(hass, CURRENT).attributes["tags"] == []
    assert await set_new_run_tags(panel, kobra, []) == []


async def test_tags_follow_on_the_last_run_cost_but_never_touch_costs_or_totals(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await print_runs(hass, clock, [1, 2])
    sensors = [
        entity_id
        for entity_id in hass.states.async_entity_ids("sensor")
        if entity_id != LAST
    ]
    before = {entity_id: state_of(hass, entity_id).state for entity_id in sensors}
    last = state_of(hass, LAST)
    [*_, run_id] = run_tags(hass_storage)

    await panel.call("wattbill/runs/update", run_id=run_id, tags=["Gift"])
    tagged = state_of(hass, LAST).attributes["tags"]
    await panel.call("wattbill/tags/rename", tag="Gift", name="Present")

    assert last.attributes["tags"] == []
    assert tagged == ["Gift"]
    renamed = state_of(hass, LAST)
    assert renamed.attributes["tags"] == ["Present"]
    assert renamed.state == last.state
    assert renamed.attributes["has_flags"] is True
    assert {entity_id: state_of(hass, entity_id).state for entity_id in sensors} == (
        before
    )


async def test_renaming_and_deleting_a_tag_changes_the_devices_tags_for_new_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    entry = await tagged(hass, hass_storage, vase=["Gift", "Present"])
    kobra = await add_device(hass, entry)
    mini = await add_device(hass, entry, name="Mini", status="sensor.mini_status")
    await set_new_run_tags(panel, kobra, ["Gift", "Present"])
    await set_new_run_tags(panel, mini, ["Present", "Spare"])

    await panel.call("wattbill/tags/rename", tag="Present", name="Gift")
    await panel.call("wattbill/tags/delete", tag="Spare")

    devices = (await panel.call("wattbill/devices/list"))["devices"]
    assert [device["settings"]["tags_for_new_runs"] for device in devices] == [
        ["Gift"],
        ["Gift"],
    ]
