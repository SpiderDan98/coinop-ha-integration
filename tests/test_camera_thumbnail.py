"""A camera as Thumbnail: fetched while the Run is running, never after it ended."""

from pathlib import Path

from homeassistant.core import HomeAssistant

from .clock import Clock
from .devices import add_device, add_hub, reconfigure
from .http import HttpClient
from .images import CAMERA, add_camera, add_cameras, picture
from .test_images import only_run, snapshot_colour, thumbnail_colour
from .test_runs import NO_MATERIAL, set_status
from .websocket import PanelClient

PREVIEW = "camera.printer_thumbnail"


async def test_the_images_step_takes_a_camera_as_thumbnail(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    subentry = await add_device(hass, entry, thumbnail=PREVIEW)

    assert subentry.data["images"]["thumbnail"] == PREVIEW


async def test_reconfigure_takes_a_camera_as_thumbnail(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry)

    await reconfigure(
        hass, entry, subentry, {"next_step_id": "images"}, {"thumbnail": PREVIEW}
    )

    assert entry.subentries[subentry.subentry_id].data["images"]["thumbnail"] == PREVIEW


async def test_a_run_ends_with_the_picture_the_camera_showed_while_it_ran(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_camera(hass, picture("red"), entity_id=PREVIEW)
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=PREVIEW)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    assert await thumbnail_colour(panel, http) == "red"


async def test_a_camera_without_a_picture_yet_is_asked_again_while_the_run_runs(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    camera = await add_camera(hass, entity_id=PREVIEW)
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=PREVIEW)
    await set_status(hass, "printing")
    assert await thumbnail_colour(panel, http) is None

    camera.answers = [picture("green")]
    await clock.advance(minutes=5)
    await set_status(hass, "finished")

    assert await thumbnail_colour(panel, http) == "green"


async def test_a_camera_is_asked_again_while_the_run_runs_and_the_latest_picture_kept(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    """At the start some show a placeholder, or the previous print's preview."""
    camera = await add_camera(hass, picture("red"), entity_id=PREVIEW)
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=PREVIEW)
    await set_status(hass, "printing")
    assert await thumbnail_colour(panel, http) == "red"

    camera.answers = [picture("green")]
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    assert await thumbnail_colour(panel, http) == "green"


async def test_a_camera_without_a_picture_leaves_the_run_without_a_thumbnail(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    camera = await add_camera(hass, entity_id=PREVIEW)
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=PREVIEW)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    asked = camera.requests

    camera.answers = [picture("green")]
    await clock.advance(hours=1)

    run = await only_run(panel)
    assert run["cover"] is None
    detail = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert detail["flags"] == NO_MATERIAL
    assert camera.requests == asked, "nothing is fetched after the Run ended"


async def test_a_camera_thumbnail_and_a_snapshot_camera_work_side_by_side(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    preview, webcam = await add_cameras(hass, PREVIEW, CAMERA)
    preview.answers = [picture("red")]
    webcam.answers = [picture("blue")]
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=PREVIEW, camera=CAMERA)

    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")

    assert await thumbnail_colour(panel, http) == "red"
    assert await snapshot_colour(panel, http) == "blue"
    assert webcam.requests == 1, "the webcam is asked for the Snapshot alone"
