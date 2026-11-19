"""Run images: the Thumbnail and the Snapshot, stored re-encoded and served privately."""

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub, configure, reconfigure, start_reconfigure
from .http import HttpClient
from .images import (
    CAMERA,
    THUMBNAIL,
    add_camera,
    add_thumbnail,
    colour,
    opened,
    picture,
)
from .test_device_flow import suggested
from .test_lifecycle import JOB, start_job, start_wattbill, stop_wattbill
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


async def thumbnail_colour(panel: PanelClient, http: HttpClient) -> str | None:
    images = [i for i in await run_images(panel) if i["kind"] == "thumbnail"]
    if not images:
        return None
    [image] = images
    return colour(await http.content(image["url"]))


async def test_the_thumbnail_follows_the_image_entity_while_the_run_is_open(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    thumbnail = await add_thumbnail(hass, picture("red"))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)
    await set_status(hass, "printing")

    await clock.advance(minutes=1)
    thumbnail.show(picture("green"))
    await hass.async_block_till_done()

    assert await thumbnail_colour(panel, http) == "green"
    assert len(stored_files(files)) == 2, "the replaced image's files are deleted"


async def test_a_run_started_without_a_thumbnail_gets_the_first_one_shown(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    thumbnail = await add_thumbnail(hass)
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)
    await set_status(hass, "printing")
    assert await thumbnail_colour(panel, http) is None

    thumbnail.show(picture("blue"))
    await hass.async_block_till_done()

    assert await thumbnail_colour(panel, http) == "blue"


async def test_an_unavailable_or_empty_thumbnail_never_replaces_the_stored_one(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    thumbnail = await add_thumbnail(hass, picture("red"))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)
    await set_status(hass, "printing")

    await clock.advance(minutes=1)
    thumbnail.show(picture("green"), available=False)
    await hass.async_block_till_done()
    await clock.advance(minutes=1)
    thumbnail.show(b"")
    await hass.async_block_till_done()
    await clock.advance(minutes=1)
    thumbnail.show(b"not an image")
    await hass.async_block_till_done()

    assert await thumbnail_colour(panel, http) == "red"


async def test_the_thumbnail_is_frozen_when_the_run_ends(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    thumbnail = await add_thumbnail(hass, picture("red"))
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=THUMBNAIL)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    thumbnail.show(picture("green"))
    await hass.async_block_till_done()

    assert await thumbnail_colour(panel, http) == "red"


async def snapshot_colour(panel: PanelClient, http: HttpClient) -> str | None:
    images = [i for i in await run_images(panel) if i["kind"] == "snapshot"]
    if not images:
        return None
    [image] = images
    return colour(await http.content(image["url"]))


@pytest.mark.parametrize("ending", ["finished", "cancelled", "idle"])
async def test_the_camera_takes_a_snapshot_when_a_run_ends_whatever_its_outcome(
    hass: HomeAssistant,
    clock: Clock,
    files: Path,
    panel: PanelClient,
    http: HttpClient,
    ending: str,
) -> None:
    camera = await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    assert camera.requests == 0

    await set_status(hass, ending)

    assert await snapshot_colour(panel, http) == "blue"
    assert camera.requests == 1


async def test_no_snapshot_when_it_is_switched_off(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    camera = await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA, snapshot=False)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await set_status(hass, "finished")
    await clock.advance(minutes=1)

    assert await run_images(panel) == []
    assert camera.requests == 0


async def test_a_failed_snapshot_is_tried_again_within_about_30_seconds(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    camera = await add_camera(hass)
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await clock.advance(seconds=10)
    assert camera.requests == 2

    camera.answers = [b"", picture("green")]
    await clock.advance(seconds=10)
    assert await snapshot_colour(panel, http) is None
    await clock.advance(seconds=10)
    await clock.advance(seconds=10)

    assert await snapshot_colour(panel, http) is None
    assert camera.requests == 3, "three attempts at most"


async def test_the_second_attempt_can_bring_the_snapshot(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    camera = await add_camera(hass)
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    camera.answers = [picture("green")]
    await clock.advance(seconds=10)

    assert await snapshot_colour(panel, http) == "green"
    assert camera.requests == 2


async def test_no_snapshot_when_the_end_is_only_noticed_long_after(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    camera = await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await stop_wattbill(hass, entry)
    await set_status(hass, "finished")
    await clock.advance(minutes=3)

    await start_wattbill(hass, entry)

    assert await run_images(panel) == []
    assert camera.requests == 0


async def test_a_snapshot_when_the_end_is_noticed_moments_after(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    await add_device(hass, entry, camera=CAMERA)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await stop_wattbill(hass, entry)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)

    await start_wattbill(hass, entry)

    assert await snapshot_colour(panel, http) == "blue"


async def test_no_snapshot_for_a_run_closed_by_the_next_job(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    camera = await add_camera(hass, picture("blue"))
    entry = await add_hub(hass)
    await add_device(hass, entry, job=JOB, camera=CAMERA)
    await start_job(hass, "benchy.gcode")
    await clock.advance(minutes=30)
    await set_status(hass, "paused")

    await start_job(hass, "cube.gcode")

    assert len((await panel.call("wattbill/runs/list"))["runs"]) == 2
    assert camera.requests == 0
