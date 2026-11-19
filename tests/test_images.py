"""Run images: the Thumbnail and the Snapshot, stored re-encoded and served privately."""

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .clock import Clock
from .devices import add_device, add_hub, configure, reconfigure, start_reconfigure
from .http import HttpClient
from .images import CAMERA, THUMBNAIL, add_thumbnail, colour, opened, picture
from .test_device_flow import suggested
from .test_runs import set_status
from .websocket import PanelClient


def stored_files(files: Path) -> list[Path]:
    """Every file in WattBill's file folder."""
    return sorted(path for path in files.rglob("*") if path.is_file())


async def run_images(panel: PanelClient) -> list[dict[str, Any]]:
    """The images of the only Run, as the Run page receives them."""
    [summary] = (await panel.call("wattbill/runs/list"))["runs"]
    run = (await panel.call("wattbill/runs/get", run_id=summary["id"]))["run"]
    images: list[dict[str, Any]] = run["images"]
    return images


async def test_the_thumbnail_is_copied_when_a_run_starts(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_thumbnail(hass, picture("red"))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)

    await set_status(hass, "printing")

    [image] = await run_images(panel)
    assert image["kind"] == "thumbnail"
    assert colour(await http.content(image["url"])) == "red"


async def test_images_are_stored_as_downscaled_webp_with_a_tile(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_thumbnail(hass, picture(size=(4000, 3000), image_format="PNG"))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)

    await set_status(hass, "printing")

    [image] = await run_images(panel)
    full = opened(await http.content(image["url"]))
    tile = opened(await http.content(image["tile_url"]))
    assert (full.format, full.size) == ("WEBP", (1600, 1200))
    assert (tile.format, tile.size) == ("WEBP", (480, 360))


async def test_images_are_turned_upright_and_stripped_of_all_metadata(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    # Orientation 6: the camera was turned, so the stored pixels lie on their side.
    await add_thumbnail(hass, picture(size=(300, 200), orientation=6))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)

    await set_status(hass, "printing")

    [image] = await run_images(panel)
    for url in (image["url"], image["tile_url"]):
        stored = opened(await http.content(url))
        assert stored.size == (200, 300)
        assert dict(stored.getexif()) == {}
        assert not {"exif", "xmp", "icc_profile"} & set(stored.info)


async def test_only_the_re_encoded_images_are_kept(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    await add_thumbnail(hass, picture())
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)

    await set_status(hass, "printing")

    [image] = await run_images(panel)
    assert {path.name for path in stored_files(files)} == {
        f"{image['id']}.webp",
        f"{image['id']}.tile.webp",
    }


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
