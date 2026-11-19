"""Run images: the Thumbnail and the Snapshot, stored re-encoded and served privately."""

from typing import Any

from homeassistant.core import HomeAssistant

from .devices import add_device, add_hub, configure, reconfigure, start_reconfigure
from .test_device_flow import suggested

THUMBNAIL = "image.kobra_thumbnail"
CAMERA = "camera.kobra"


async def test_the_images_step_takes_a_thumbnail_a_camera_and_the_snapshot_toggle(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry, thumbnail=THUMBNAIL, camera=CAMERA)

    assert subentry.data["images"] == {
        "thumbnail": THUMBNAIL,
        "camera": CAMERA,
        "snapshot": True,
    }


async def test_images_are_optional(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry)

    assert subentry.data["images"] == {
        "thumbnail": None,
        "camera": None,
        "snapshot": False,
    }


async def test_the_snapshot_can_be_switched_off(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry, camera=CAMERA, snapshot=False)

    assert subentry.data["images"]["snapshot"] is False


async def test_the_snapshot_toggle_does_nothing_without_a_camera(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry, snapshot=True)

    assert subentry.data["images"]["snapshot"] is False


async def test_reconfigure_pre_fills_the_images_and_turns_the_snapshot_on_with_a_new_camera(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, thumbnail=THUMBNAIL)
    menu = await start_reconfigure(hass, entry, subentry)

    result: Any = await configure(hass, menu, {"next_step_id": "images"})

    assert suggested(result, "thumbnail") == THUMBNAIL
    assert suggested(result, "snapshot") is True

    await reconfigure(
        hass,
        entry,
        subentry,
        {"next_step_id": "images"},
        {"thumbnail": THUMBNAIL, "camera": CAMERA},
    )
    assert entry.subentries[subentry.subentry_id].data["images"] == {
        "thumbnail": THUMBNAIL,
        "camera": CAMERA,
        "snapshot": True,
    }
