"""Integration Profiles of 3D printer integrations."""

from itertools import takewhile
from typing import Any

from custom_components.coinop.const import DEVICE_TYPE_3D_PRINTER

from .base import Find, always, found, mapping

DEVICE_TYPES = (DEVICE_TYPE_3D_PRINTER,)
KIND = always(DEVICE_TYPE_3D_PRINTER)
SLOTS = range(1, 5)


def _slots(find: Find, suffix: str) -> list[str]:
    """The Slots in order, up to the first one missing: a gap would shift the numbers."""
    slots = (find("sensor", suffix.format(number)) for number in SLOTS)
    return [entity_id for entity_id in takewhile(bool, slots) if entity_id]


def anycubic(find: Find) -> dict[str, Any]:
    """chrisfore/anycubic_ha_local: unique ids `<serial>_<key>`, the ACE `<serial>_ace0_<key>`."""
    status = find("event", "_print_event")
    job = find("sensor", "_filename")
    filament = find("sensor", "_filament_used")
    slots = _slots(find, "_ace0_slot_{}")
    loaded = find("sensor", "_ace0_loaded_slot")
    thumbnail = find("image", "_object_top_view", "_object_thumbnail")
    camera = find("camera", "_camera")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                running=["started", "resumed"],
                paused=["paused"],
                finished=["finished"],
                cancelled=["stopped"],
                fault=["error"],
                # The bed cool-down after a print.
                ignored=["clear_ready", "clear_done", "clear_failed"],
            ),
        ),
        "job": found(job, entity_id=job, attribute=None)
        # The state is grams from a guessed density; the attribute is the measured length.
        | found(
            filament,
            material={"entity_id": filament, "attribute": "length_mm", "unit": "mm"},
        )
        | found(slots, slots=slots, colour_attribute="color")
        | found(loaded, loaded_slot=loaded),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
    }


def anycubic_cloud(find: Find) -> dict[str, Any]:
    """Nino6689/hass-anycubic 3.0 and 2.x alike: unique ids `<MAC>-<key>`.

    Its job cost and energy sensors are left alone: CoinOp computes every cost itself.
    """
    status = find("sensor", "-job_state")
    job = find("sensor", "-job_name")
    filament = find("sensor", "-job_filament_used")
    slots = _slots(find, "-ace_slot_{}")
    loaded = find("sensor", "-ace_loaded_slot")
    # Only exists while the integration talks to the cloud.
    thumbnail = find("image", "-job_image_url")
    camera = find("camera", "-camera")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                running=["printing", "preheating", "levelling"],
                paused=["paused"],
                finished=["finished"],
                # `failed` is the cloud's word for a cancelled job.
                cancelled=["cancelled", "failed"],
                # 2.x over LAN goes from printing straight to idle.
                ended=["idle"],
                ignored=["downloading", "checking", "slicing"],
            ),
        ),
        "job": found(job, entity_id=job, attribute=None)
        | found(
            filament, material={"entity_id": filament, "attribute": None, "unit": "mm"}
        )
        | found(slots, slots=slots, colour_attribute="color_hex")
        | found(loaded, loaded_slot=loaded),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
    }


def bambu_lab(find: Find) -> dict[str, Any]:
    """greghesp/ha-bambulab: unique ids `<serial>_<key>`; an AMS is its own HA device."""
    status = find("sensor", "_print_status")
    job = find("sensor", "_subtask_name")
    # The slicer's planned weight of the whole print, not a measured one.
    weight = find("sensor", "_print_weight")
    thumbnail = find("image", "_cover_image")
    # Missing where the printer's camera is turned off or offered as an image.
    camera = find("camera", "_camera")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                # Heating and levelling belong to the Run.
                running=["running", "prepare"],
                paused=["pause"],
                finished=["finish"],
                # A print stopped on the printer, or one that failed.
                cancelled=["failed"],
                ignored=["idle", "init", "slicing", "offline", "unknown"],
            ),
        ),
        "job": found(job, entity_id=job, attribute=None)
        | found(weight, material={"entity_id": weight, "attribute": None, "unit": "g"}),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
    }


def octoprint(find: Find) -> dict[str, Any]:
    """HA core `octoprint`: unique ids `<Name>-<device id>`, the camera's the device id.

    The separator belongs to the name, or `Current File` would match `Current File Size`.
    """
    status = find("sensor", "Current State-", start=True)
    job = find("sensor", "Current File-", start=True)
    # Its only camera, there while the webcam is enabled in OctoPrint.
    camera = find("camera", "")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                running=[
                    "printing",
                    "printing_sd",
                    "starting",
                    "starting_sd",
                    "resuming",
                ],
                paused=["pausing", "paused"],
                # Only a print that completed passes through it, for a few seconds.
                finished=["finishing"],
                cancelled=["cancelling"],
                ended=["operational"],
                fault=["error", "offline_after_error"],
                # Sending a file to the SD card is an upload, not a print.
                ignored=[
                    "open_serial",
                    "detect_serial",
                    "connecting",
                    "offline",
                    "starting_streaming",
                    "printing_streaming",
                    "transferring_file",
                ],
            ),
        ),
        "job": found(job, entity_id=job, attribute=None),
        "images": found(camera, camera=camera, snapshot=True),
    }
