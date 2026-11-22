"""Integration Profiles of 3D printer integrations."""

from itertools import takewhile
from typing import Any

from custom_components.coinop.const import DEVICE_TYPE_3D_PRINTER

from .base import Find, always, entity_input, found, mapping, progress_inputs

DEVICE_TYPES = (DEVICE_TYPE_3D_PRINTER,)
KIND = always(DEVICE_TYPE_3D_PRINTER)
SLOTS = range(1, 5)


def _slots(find: Find, suffix: str) -> list[str]:
    """The Slots in order, up to the first one missing: a gap would shift the numbers."""
    slots = (find("sensor", suffix.format(number)) for number in SLOTS)
    return [entity_id for entity_id in takewhile(bool, slots) if entity_id]


def _drying(*units: tuple[str | None, str | None]) -> dict[str, Any]:
    """The job section's Drying inputs of the units whose active entity was found."""
    drying = [
        {"active": active, "drying_left": left} for active, left in units if active
    ]
    return {"drying": drying} if drying else {}


def _planned(
    material: str | None, planned: str | None, unit: str, attribute: str | None = None
) -> dict[str, Any]:
    """The Planned material input, kept only next to a Material used input."""
    return found(
        material and planned,
        planned_material={"entity_id": planned, "attribute": attribute, "unit": unit},
    )


def anycubic(find: Find) -> dict[str, Any]:
    """chrisfore/anycubic_ha_local: unique ids `<serial>_<key>`, the ACE `<serial>_ace0_<key>`."""
    status = find("event", "_print_event")
    job = find("sensor", "_filename")
    filament = find("sensor", "_filament_used")
    slots = _slots(find, "_ace0_slot_{}")
    loaded = find("sensor", "_ace0_loaded_slot")
    thumbnail = find("image", "_object_top_view", "_object_thumbnail")
    camera = find("camera", "_camera")
    remaining = find("sensor", "_time_remaining")
    return {
        "status": entity_input(status),
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
        "job": entity_input(job)
        # The state is grams from a guessed density; the attribute is the measured length.
        | found(
            filament,
            material={"entity_id": filament, "attribute": "length_mm", "unit": "mm"},
        )
        | found(slots, slots=slots, colour_attribute="color")
        | found(loaded, loaded_slot=loaded)
        | _drying(
            (find("switch", "_ace0_drying"), find("sensor", "_ace0_drying_remaining"))
        ),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(remaining, find("sensor", "_progress")),
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
        "status": entity_input(status),
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
        "job": entity_input(job)
        | found(
            filament, material={"entity_id": filament, "attribute": None, "unit": "mm"}
        )
        # Its plan declares no unit and none is confirmed upstream: grams assumed.
        | _planned(filament, job, "g", attribute="estimated_filament")
        | found(slots, slots=slots, colour_attribute="color_hex")
        | found(loaded, loaded_slot=loaded)
        # Its drying left declares no unit: minutes, as its own card shows them.
        | _drying(
            *(
                (
                    find("binary_sensor", f"-{ace}dry_status_is_drying"),
                    find("sensor", f"-{ace}dry_status_remaining_time"),
                )
                for ace in ("", "secondary_")
            )
        ),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(
            find("sensor", "-job_time_remaining"), find("sensor", "-job_progress")
        ),
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
        "status": entity_input(status),
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
        "job": entity_input(job)
        | found(weight, material={"entity_id": weight, "attribute": None, "unit": "g"})
        # Measured and planned alike, so no Material is still to come.
        | _planned(weight, weight, "g")
        # Only an AMS that dries has these, each on its own HA device.
        | _drying(
            *(
                (
                    ams("binary_sensor", "_drying"),
                    ams("sensor", "_remaining_drying_time"),
                )
                for ams in find.linked()
            )
        ),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(
            find("sensor", "_remaining_time"), find("sensor", "_print_progress")
        ),
    }


def prusalink(find: Find) -> dict[str, Any]:
    """Home Assistant's PrusaLink: unique ids `<config entry id>_<key>`, no Material used."""
    status = find("sensor", "_printer.state")
    job = find("sensor", "_job.filename")
    # The job preview is a camera; the integration has no webcam.
    thumbnail = find("camera", "_job_preview")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["printing"],
                # `attention` waits for the user, such as on a filament runout.
                paused=["paused", "attention"],
                finished=["finished"],
                cancelled=["stopped"],
                fault=["error"],
                ignored=["idle", "ready", "busy"],
            ),
        ),
        "job": entity_input(job),
        "images": found(thumbnail, thumbnail=thumbnail),
        # Only a finish timestamp, no duration.
        "progress": progress_inputs(
            find("sensor", "_job.finish"), find("sensor", "_job.progress")
        ),
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
        "status": entity_input(status),
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
        "job": entity_input(job),
        "images": found(camera, camera=camera, snapshot=True),
        # A finish timestamp, unknown while paused.
        "progress": progress_inputs(
            find("sensor", "Estimated Finish Time-", start=True),
            find("sensor", "Job Percentage-", start=True),
        ),
    }


def creality(find: Find) -> dict[str, Any]:
    """3dg1luk43/ha_creality_ws: unique ids `<host>-<key>`, moved to a new host in place."""
    status = find("sensor", "-print_status")
    material = find("sensor", "-used_material_length")
    thumbnail = find("image", "-current_print_preview")
    # Registered on models without a camera too, unless set up without a URL.
    camera = find("camera", "-camera")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["printing"],
                paused=["paused"],
                finished=["completed"],
                cancelled=["stopped"],
                fault=["error"],
                # `processing` is a job's warm-up and also where a cancelled job idles.
                ignored=["processing", "self-testing", "idle", "off", "unknown"],
            ),
        ),
        # The job's file is an attribute of the Status.
        "job": found(status, entity_id=status, attribute="file")
        | found(
            material, material={"entity_id": material, "attribute": None, "unit": "cm"}
        )
        | _planned(material, find("sensor", "-expected_material_length"), "cm"),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(
            find("sensor", "-print_left_time"), find("sensor", "-print_progress")
        ),
    }


def elegoo(find: Find) -> dict[str, Any]:
    """danielcherubini/elegoo-homeassistant: unique ids `<machine id>_<key>`."""
    status = find("sensor", "_print_status")
    job = find("sensor", "_filename")
    # FDM printers with OpenCentauri firmware or the CC2 protocol only.
    extrusion = find("sensor", "_current_extrusion")
    # Not on printers that speak MQTT.
    thumbnail = find("image", "_cover_image")
    # Registered for every printer, whether it has a camera or not.
    camera = find("camera", "_chamber_camera")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                # The resin states first; FDM printers may park on a milestone
                # ("preheating_completed") for a whole print.
                running=[
                    "printing",
                    "printing_recovery",
                    "recovery",
                    "homing",
                    "dropping",
                    "lifting",
                    "preheating",
                    "leveling",
                    "loading",
                    "printers_checking",
                    "print_started",
                    "resuming",
                    "resonance_testing",
                    "auto_leveling_completed",
                    "preheating_completed",
                    "homing_completed",
                    "resonance_testing_completed",
                    "auto_feeding",
                    "filament_unloading",
                ],
                # A failed filament unload waits for the user.
                paused=[
                    "pausing",
                    "paused",
                    "filament_unload_paused",
                    "filament_unload_abnormal",
                ],
                finished=["complete"],
                cancelled=["stopping", "stopped"],
                fault=["error"],
                ignored=["idle", "file_checking", "unrecognized"],
            ),
        ),
        "job": entity_input(job)
        | found(
            extrusion,
            material={"entity_id": extrusion, "attribute": None, "unit": "mm"},
        )
        # The CC2 protocol's slicer total, in grams though it declares no unit.
        | _planned(extrusion, find("sensor", "_total_filament_used"), "g"),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(
            find("sensor", "_ticks_remaining"), find("sensor", "_percent_complete")
        ),
    }


def moonraker(find: Find) -> dict[str, Any]:
    """marcolivierarsenault/moonraker-home-assistant: unique ids `<entry id>_<key>`."""
    # The print's state, not the printer's own `state` (ready, shutdown and so on).
    status = find("sensor", "_print_state")
    job = find("sensor", "_filename")
    # This print's measured extrusion; the lifetime total ends in the same key.
    filament = find("sensor", "_filament_used", exclude="_total_filament_used")
    # The print's preview, shown only while it prints.
    thumbnail = find("camera", "_thumbnail")
    # A webcam is `<entry id>_<webcam name>_<index>`: any camera but the preview.
    camera = find("camera", "", exclude="_thumbnail")
    # Hours; both drop to 0 while paused.
    remaining = find("sensor", "_print_time_left")
    progress = find("sensor", "_progress")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["printing"],
                paused=["paused"],
                finished=["complete"],
                cancelled=["cancelled"],
                # Klipper resets to it after a print or an error, never during a print.
                ended=["standby"],
                fault=["error"],
            ),
        ),
        "job": entity_input(job)
        | found(
            filament, material={"entity_id": filament, "attribute": None, "unit": "m"}
        ),
        "images": found(thumbnail, thumbnail=thumbnail)
        | found(camera, camera=camera, snapshot=True),
        "progress": progress_inputs(remaining, progress),
    }
