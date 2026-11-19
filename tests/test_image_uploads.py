"""Uploaded photos, the Cover Image choice and deleting single images."""

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockUser

from .clock import Clock
from .devices import add_device, add_hub
from .http import HttpClient
from .images import THUMBNAIL, add_thumbnail, colour, opened, picture
from .test_images import only_run, run_images, stored_files
from .test_lifecycle import start_wattbill, stop_wattbill
from .test_runs import set_status
from .websocket import PanelClient


def uploads(run_id: str) -> str:
    return f"/api/wattbill/runs/{run_id}/images"


async def open_run(hass: HomeAssistant, thumbnail: str | None = None) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, thumbnail=thumbnail)
    await set_status(hass, "printing")


async def ended_run(
    hass: HomeAssistant, clock: Clock, thumbnail: str | None = None
) -> None:
    await open_run(hass, thumbnail)
    await clock.advance(hours=1)
    await set_status(hass, "finished")


async def test_several_photos_can_be_uploaded_at_once_to_an_open_run(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await open_run(hass)
    run_id = (await only_run(panel))["id"]

    status, body = await http.upload(
        uploads(run_id),
        picture("red"),
        (picture("green", image_format="PNG"), "image/png"),
        (picture("blue", image_format="WEBP"), "image/webp"),
    )

    assert status == HTTPStatus.OK
    images = await run_images(panel)
    assert [image["kind"] for image in images] == ["upload"] * 3
    assert [image["id"] for image in body["images"]] == [i["id"] for i in images]
    assert [colour(await http.content(i["url"])) for i in images] == [
        "red",
        "green",
        "blue",
    ]


async def test_uploads_are_turned_upright_downscaled_and_stripped_of_all_metadata(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await ended_run(hass, clock)
    run_id = (await only_run(panel))["id"]

    # A phone photo with GPS, taken turned (orientation 6).
    await http.upload(uploads(run_id), picture(size=(4000, 3000), orientation=6))

    [image] = await run_images(panel)
    full = opened(await http.content(image["url"]))
    tile = opened(await http.content(image["tile_url"]))
    assert (full.format, full.size) == ("WEBP", (1200, 1600))
    assert (tile.format, tile.size) == ("WEBP", (360, 480))
    for stored in (full, tile):
        assert dict(stored.getexif()) == {}
        assert not {"exif", "xmp", "icc_profile"} & set(stored.info)
    assert {path.name for path in stored_files(files)} == {
        f"{image['id']}.webp",
        f"{image['id']}.tile.webp",
    }


async def test_a_run_takes_up_to_ten_uploads(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_thumbnail(hass, picture())
    await ended_run(hass, clock, thumbnail=THUMBNAIL)
    run_id = (await only_run(panel))["id"]
    await http.upload(uploads(run_id), *[picture()] * 8)

    status, body = await http.upload(uploads(run_id), *[picture("blue")] * 3)

    assert (status, body["code"]) == (HTTPStatus.CONFLICT, "too_many")
    assert len(await run_images(panel)) == 9
    status, _ = await http.upload(uploads(run_id), *[picture("blue")] * 2)
    assert status == HTTPStatus.OK
    assert len(await run_images(panel)) == 11
    assert len(stored_files(files)) == 22


async def test_a_photo_may_have_up_to_20_mb(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await ended_run(hass, clock)
    run_id = (await only_run(panel))["id"]
    photo = picture()
    # JPEG readers ignore what follows the image.
    largest = photo + bytes(20 * 1024 * 1024 - len(photo))

    status, body = await http.upload(uploads(run_id), largest + b"\0")

    assert (status, body["code"]) == (HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too_large")
    assert await run_images(panel) == []
    assert (await http.upload(uploads(run_id), largest))[0] == HTTPStatus.OK


async def test_only_jpeg_png_and_webp_are_taken_and_a_refused_one_stops_the_request(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await ended_run(hass, clock)
    run_id = (await only_run(panel))["id"]

    for refused in (
        (picture(image_format="GIF"), "image/gif"),
        (b"not a photo", "image/jpeg"),
    ):
        status, body = await http.upload(uploads(run_id), picture(), refused)

        assert (status, body["code"]) == (
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "invalid_format",
        )
    assert await run_images(panel) == []
    assert stored_files(files) == []


async def test_uploads_are_for_admins_and_existing_runs_only(
    hass: HomeAssistant,
    clock: Clock,
    files: Path,
    panel: PanelClient,
    http: HttpClient,
    connect_http: Callable[[MockUser], HttpClient],
    hass_read_only_user: MockUser,
) -> None:
    await ended_run(hass, clock)
    run_id = (await only_run(panel))["id"]

    read_only = connect_http(hass_read_only_user)
    status, _ = await read_only.upload(uploads(run_id), picture())
    assert status == HTTPStatus.UNAUTHORIZED
    status, body = await http.upload(uploads("unknown"), picture())
    assert (status, body["code"]) == (HTTPStatus.NOT_FOUND, "not_found")
    assert await run_images(panel) == []


async def run_with_photos(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, http: HttpClient
) -> tuple[str, list[dict[str, Any]]]:
    """An ended Run with a red Thumbnail and a green and a blue upload."""
    await add_thumbnail(hass, picture("red"))
    await ended_run(hass, clock, thumbnail=THUMBNAIL)
    run_id = (await only_run(panel))["id"]
    await http.upload(uploads(run_id), picture("green"), picture("blue"))
    return run_id, await run_images(panel)


async def test_set_as_cover_picks_the_cover_image(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    run_id, [_thumbnail, _green, blue] = await run_with_photos(hass, clock, panel, http)
    await panel.subscribe("wattbill/runs/subscribe")
    await panel.event()

    result = await panel.call(
        "wattbill/images/set_cover", run_id=run_id, image_id=blue["id"]
    )

    assert result["run"]["cover"]["id"] == blue["id"]
    pushed = await panel.event()
    assert (pushed["change"], pushed["run"]["cover"]["id"]) == ("updated", blue["id"])
    assert colour(await http.content((await only_run(panel))["cover"]["url"])) == "blue"


async def test_the_cover_image_choice_outlives_a_restart(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    run_id, [*_, blue] = await run_with_photos(hass, clock, panel, http)
    await panel.call("wattbill/images/set_cover", run_id=run_id, image_id=blue["id"])
    entry = hass.config_entries.async_entries("wattbill")[0]

    await stop_wattbill(hass, entry)
    await start_wattbill(hass, entry)

    assert (await only_run(panel))["cover"]["id"] == blue["id"]


async def test_deleting_the_picked_cover_falls_back_to_the_rule(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    run_id, [thumbnail, _green, blue] = await run_with_photos(hass, clock, panel, http)
    await panel.call("wattbill/images/set_cover", run_id=run_id, image_id=blue["id"])

    result = await panel.call(
        "wattbill/images/delete", run_id=run_id, image_id=blue["id"]
    )

    assert result["run"]["cover"]["id"] == thumbnail["id"]
    assert (await only_run(panel))["cover"]["id"] == thumbnail["id"]


async def test_any_single_image_can_be_deleted_with_its_files(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    run_id, [thumbnail, green, blue] = await run_with_photos(hass, clock, panel, http)

    for image in (green, thumbnail):
        await panel.call("wattbill/images/delete", run_id=run_id, image_id=image["id"])
    await hass.async_block_till_done()

    assert [i["id"] for i in await run_images(panel)] == [blue["id"]]
    assert {path.name for path in stored_files(files)} == {
        f"{blue['id']}.webp",
        f"{blue['id']}.tile.webp",
    }
    assert (await http.get(green["url"]))[0] == HTTPStatus.NOT_FOUND
    assert (await only_run(panel))["cover"]["id"] == blue["id"]


async def test_cover_and_delete_need_an_existing_image(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    run_id, [thumbnail, *_] = await run_with_photos(hass, clock, panel, http)

    for command in ("wattbill/images/set_cover", "wattbill/images/delete"):
        for ids in (
            {"run_id": run_id, "image_id": "unknown"},
            {"run_id": "unknown", "image_id": thumbnail["id"]},
        ):
            assert (await panel.error(command, **ids))["code"] == "not_found"
    assert len(await run_images(panel)) == 3
