"""Images and a Part Count on an Other Device: each picked alone, neither with a job."""

from http import HTTPStatus
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import (
    MAPPING,
    OTHER_MAPPING,
    add_hub,
    configure,
    other_input,
    start_reconfigure,
    walk_to_mapping,
)
from .http import HttpClient
from .images import (
    FakeCamera,
    FakeThumbnail,
    add_camera,
    add_thumbnail,
    colour,
    picture,
)
from .test_cost_statement import export
from .test_device_flow import fields
from .test_image_uploads import uploads
from .test_images import only_run, run_images
from .test_manual_runs import create
from .test_other_devices import KILN_STATUS, add_kiln, choose_other, fire, set_kiln
from .test_other_programs import add_bread_maker, bake
from .test_run_event import record_events
from .test_runs import stored_runs
from .test_sensors import state_of
from .websocket import PanelClient

SMALL_KILN_STATUS = "sensor.small_kiln_status"
# What the kiln is firing, as its controller shows it, and the camera looking at it.
KILN_THUMBNAIL = "image.kiln_preview"
KILN_CAMERA = "camera.kiln"


async def add_kiln_thumbnail(
    hass: HomeAssistant, content: bytes = b""
) -> FakeThumbnail:
    return await add_thumbnail(hass, content, entity_id=KILN_THUMBNAIL)


async def add_kiln_camera(hass: HomeAssistant, *answers: bytes) -> FakeCamera:
    return await add_camera(hass, *answers, entity_id=KILN_CAMERA)


async def set_small_kiln(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(SMALL_KILN_STATUS, status)
    await hass.async_block_till_done()


async def add_kiln_with(
    hass: HomeAssistant, *has: str, entry: ConfigEntry | None = None, **options: Any
) -> ConfigSubentry:
    """A kiln (see `add_kiln`) that has the choices `has`: "images", "part_count"."""
    return await add_kiln(hass, entry, has=has, **options)


async def fired_run(panel: PanelClient) -> dict[str, Any]:
    """The only Run, as the Run page receives it."""
    run: dict[str, Any] = (
        await panel.call("coinop/runs/get", run_id=(await only_run(panel))["id"])
    )["run"]
    return run


async def test_an_other_device_can_have_images_and_a_part_count(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    result = await choose_other(hass, entry)

    # Offered after what the Device consumes, before how its meters count.
    assert fields(result)[-3:] == ["images", "part_count", "per_run_meters"]


async def test_images_alone_bring_the_images_step_and_no_job_step(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    result = await walk_to_mapping(
        hass,
        entry,
        name="Kiln",
        status=KILN_STATUS,
        device_type="other",
        other=other_input("Kiln", ["images"]),
    )

    result = await configure(hass, result, OTHER_MAPPING)

    assert result["step_id"] == "images"
    assert fields(result) == ["thumbnail", "camera", "snapshot"]
    result = await configure(
        hass, result, {"thumbnail": KILN_THUMBNAIL, "camera": KILN_CAMERA}
    )
    assert result["step_id"] == "consumption"


async def test_a_printer_sees_the_images_step_an_other_device_sees(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)
    kiln = await walk_to_mapping(
        hass,
        entry,
        name="Kiln",
        status=KILN_STATUS,
        device_type="other",
        other=other_input("Kiln", ["images"]),
    )
    kiln = await configure(hass, kiln, OTHER_MAPPING)

    printer = await configure(hass, await walk_to_mapping(hass, entry), MAPPING)
    assert printer["step_id"] == "job"
    printer = await configure(hass, printer, {})

    assert (printer["step_id"], fields(printer)) == (kiln["step_id"], fields(kiln))
    assert printer["step_id"] == "images"


async def test_a_device_with_images_stores_them_and_can_reconfigure_them(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    kiln = await add_kiln_with(
        hass, "images", entry=entry, thumbnail=KILN_THUMBNAIL, camera=KILN_CAMERA
    )

    assert kiln.data["images"] == {
        "thumbnail": KILN_THUMBNAIL,
        "camera": KILN_CAMERA,
        "snapshot": True,
    }
    assert "job" not in kiln.data
    result = await start_reconfigure(hass, entry, kiln)
    assert result["menu_options"] == [
        "other",
        "status",
        "images",
        "consumption",
        "price",
        "save",
    ]
    result = await configure(hass, result, {"next_step_id": "images"})
    result = await configure(hass, result, {"camera": KILN_CAMERA, "snapshot": False})
    assert result["step_id"] == "reconfigure"


async def test_a_part_count_alone_brings_no_step_and_no_section(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    # `add_kiln` fails on any step between the Status mapping and the electricity.
    kiln = await add_kiln_with(hass, "part_count", entry=entry)

    assert {"job", "images"}.isdisjoint(kiln.data)
    result = await start_reconfigure(hass, entry, kiln)
    assert result["menu_options"] == ["other", "status", "consumption", "price", "save"]


async def test_a_run_gets_its_thumbnail_and_at_its_end_its_snapshot_without_a_job(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    thumbnail = await add_kiln_thumbnail(hass, picture("red"))
    camera = await add_kiln_camera(hass, picture("blue"))
    await add_kiln_with(hass, "images", thumbnail=KILN_THUMBNAIL, camera=KILN_CAMERA)

    await set_kiln(hass, "on")
    [started_with] = await run_images(panel)
    assert started_with["kind"] == "thumbnail"
    assert colour(await http.content(started_with["url"])) == "red"
    await clock.advance(minutes=30)
    thumbnail.show(picture("green"))
    await hass.async_block_till_done()
    assert camera.requests == 0
    await clock.advance(minutes=60)
    await set_kiln(hass, "off")

    images = await run_images(panel)
    assert [(i["kind"], colour(await http.content(i["url"]))) for i in images] == [
        ("thumbnail", "green"),
        ("snapshot", "blue"),
    ]
    run = await fired_run(panel)
    assert (run["name"], run["cover"]["kind"], run["part_count"]) == (
        None,
        "thumbnail",
        None,
    )


async def test_a_run_of_a_device_with_images_takes_photos_and_a_picked_cover_image(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_kiln_camera(hass, picture("blue"))
    await add_kiln_with(hass, "images", camera=KILN_CAMERA)
    await fire(hass, clock)
    run = await only_run(panel)
    assert run["cover"]["kind"] == "snapshot"

    status, uploaded = await http.upload(uploads(run["id"]), picture("green"))
    [photo] = uploaded["images"]
    result = await panel.call(
        "coinop/images/set_cover", run_id=run["id"], image_id=photo["id"]
    )

    assert status == HTTPStatus.OK
    assert [i["kind"] for i in result["run"]["images"]] == ["snapshot", "upload"]
    cover = (await only_run(panel))["cover"]
    assert colour(await http.content(cover["tile_url"])) == "green"


async def test_a_device_without_images_takes_none_by_itself_but_still_photos(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient, http: HttpClient
) -> None:
    await add_kiln_thumbnail(hass, picture("red"))
    camera = await add_kiln_camera(hass, picture("blue"))
    await add_kiln_with(hass, "part_count")

    await fire(hass, clock)

    run = await only_run(panel)
    assert (run["cover"], await run_images(panel), camera.requests) == (None, [], 0)
    status, _ = await http.upload(uploads(run["id"]), picture("green"))
    assert status == HTTPStatus.OK
    assert (await only_run(panel))["cover"]["kind"] == "upload"


async def test_a_run_of_a_device_with_a_part_count_is_costed_per_part(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_kiln_with(hass, "part_count")
    events = record_events(hass, "event.kiln_run")

    await fire(hass, clock)

    run = await fired_run(panel)
    assert (run["total"], run["part_count"], run["cost_per_part"]) == (0.9, 1, 0.9)
    [_, ended] = events
    assert ended["part_count"] == 1
    assert ended["cost_per_part"] == pytest.approx(0.90)
    corrected = await panel.call("coinop/runs/update", run_id=run["id"], part_count=9)
    assert (corrected["run"]["part_count"], corrected["run"]["cost_per_part"]) == (
        9,
        0.1,
    )
    [stored] = stored_runs(hass_storage)
    assert (stored["part_count"], stored["images"]) == (9, [])
    last = state_of(hass, "sensor.kiln_last_run_cost")
    assert last.attributes["part_count"] == 9
    assert last.attributes["cost_per_part"] == pytest.approx(0.10)


async def test_a_run_of_a_device_without_a_part_count_has_none_and_takes_none(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await add_kiln_camera(hass, picture("blue"))
    await add_kiln_with(hass, "images", camera=KILN_CAMERA)
    events = record_events(hass, "event.kiln_run")

    await fire(hass, clock)

    run = await fired_run(panel)
    assert (run["total"], run["part_count"], run["cost_per_part"]) == (0.9, None, None)
    [_, ended] = events
    assert {"part_count", "cost_per_part"}.isdisjoint(ended)
    error = await panel.error("coinop/runs/update", run_id=run["id"], part_count=9)
    assert error["code"] == "not_allowed"
    [stored] = stored_runs(hass_storage)
    assert stored["part_count"] is None
    last = state_of(hass, "sensor.kiln_last_run_cost")
    assert {"part_count", "cost_per_part"}.isdisjoint(last.attributes)


async def test_images_and_a_part_count_go_with_a_program(
    hass: HomeAssistant, clock: Clock, files: Path, panel: PanelClient
) -> None:
    await add_kiln_thumbnail(hass, picture("red"))
    await add_kiln_camera(hass, picture("blue"))
    # The helper expects the images step before the Program step, as Add Device asks.
    await add_bread_maker(
        hass,
        panel,
        has=["program", "images", "part_count"],
        thumbnail=KILN_THUMBNAIL,
        camera=KILN_CAMERA,
    )

    await bake(hass, clock, "Whole wheat")

    run = await fired_run(panel)
    assert (run["name"], run["program"]) == ("Whole wheat", "Whole wheat")
    assert (run["total"], run["part_count"], run["cost_per_part"]) == (0.15, 1, 0.15)
    assert [image["kind"] for image in run["images"]] == ["thumbnail", "snapshot"]


async def test_a_manual_run_has_a_part_count_only_on_a_device_with_one(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln_with(hass, "part_count", entry=entry)
    small = await add_kiln_with(
        hass, "images", entry=entry, name="Small kiln", status=SMALL_KILN_STATUS
    )
    await clock.advance(hours=5)

    bisque = await create(panel, kiln.subentry_id, name="Bisque firing")
    test_tiles = await create(panel, small.subentry_id, name="Test tiles")

    # Two hours at 2 kW and 0.30 per kWh.
    assert (bisque["part_count"], bisque["cost_per_part"]) == (1, 1.2)
    assert (test_tiles["part_count"], test_tiles["cost_per_part"]) == (None, None)


async def fire_both(hass: HomeAssistant, clock: Clock, panel: PanelClient) -> list[str]:
    """A kiln with a Part Count and a small kiln without, fired one after the other
    for 90 minutes each: "Mugs" of 9 parts, then "Test tiles". Returns their ids."""
    entry = await add_hub(hass)
    await add_kiln_with(hass, "part_count", entry=entry)
    await set_small_kiln(hass, "off")
    await add_kiln_with(hass, entry=entry, name="Small kiln", status=SMALL_KILN_STATUS)
    await fire(hass, clock)
    await set_small_kiln(hass, "on")
    await clock.advance(minutes=90)
    await set_small_kiln(hass, "off")
    # Older Home Assistant needs a second pass for the Run to be final.
    await hass.async_block_till_done()
    runs = (await panel.call("coinop/runs/list"))["runs"]
    mugs, tiles = (run["id"] for run in sorted(runs, key=lambda run: run["started"]))
    await panel.call("coinop/runs/update", run_id=mugs, name="Mugs", part_count=9)
    await panel.call("coinop/runs/update", run_id=tiles, name="Test tiles")
    return [mugs, tiles]


async def test_a_cost_statement_lists_the_part_count_only_of_a_device_that_has_one(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    run_ids = await fire_both(hass, clock, panel)

    compact = await export(panel, browser, run_ids=run_ids, detail="compact")
    detailed = await export(panel, browser, run_ids=run_ids)

    header = compact.lines.index("Run Device Start Parts Per part Total")
    assert compact.lines[header + 1 : header + 3] == [
        "Mugs (Unknown) Kiln Jan 15, 2026 9 €0.10 €0.90",
        "Test tiles (Unknown) Small kiln Jan 15, 2026 €0.90",
    ]
    details = [line for line in detailed.lines if "Running time 1 h 30 min" in line]
    assert details == [
        "Kiln · Jan 15, 2026 · Running time 1 h 30 min · 9 parts · €0.10 per part"
        " · Unknown",
        "Small kiln · Jan 15, 2026 · Running time 1 h 30 min · Unknown",
    ]


async def test_a_cost_statement_without_any_part_count_has_no_column_for_it(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    [_, tiles] = await fire_both(hass, clock, panel)

    statement = await export(panel, browser, run_ids=[tiles], detail="compact")

    assert "Run Device Start Total" in statement.lines
    assert "Test tiles (Unknown) Small kiln Jan 15, 2026 €0.90" in statement.lines


async def test_the_devices_command_sends_what_images_and_a_part_count_bring(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_kiln_with(hass, "images", entry=entry, thumbnail=KILN_THUMBNAIL)
    await add_kiln_with(
        hass, "part_count", entry=entry, name="Small kiln", status=SMALL_KILN_STATUS
    )

    kiln, small = (await panel.call("coinop/devices/list"))["devices"]

    assert kiln["capabilities"] == ["average_power", "images"]
    assert kiln["ha_settings"]["images"] == {
        "thumbnail": KILN_THUMBNAIL,
        "camera": None,
        "snapshot": False,
    }
    assert small["capabilities"] == ["average_power", "part_count"]
    assert "job" not in kiln["ha_settings"]
    assert {"job", "images"}.isdisjoint(small["ha_settings"])
