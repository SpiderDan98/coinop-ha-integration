"""Integration Profiles: Device Input defaults for known integrations, by Device Type.

A profile only pre-fills the Add Device and Detect again steps; the Device stores the
concrete entities it found, so nothing stays coupled to the profile (ADR 0004).
"""

from collections.abc import Callable
from itertools import takewhile
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DEVICE_TYPE_3D_PRINTER, DEVICE_TYPE_WASHING_MACHINE
from .device_config import ConsumptionSource, Target, WaterSource
from .quantities import ELECTRICITY, WATER

# Finds the entity of a platform whose unique id ends in one of the suffixes, in order.
Find = Callable[..., str | None]
SLOTS = range(1, 5)
# Sections a profile pre-fills only in Add Device: Detect again leaves them alone.
METERS = (ELECTRICITY.source_key, WATER.source_key)


def _found(entity: str | list[str] | None, /, **fields: Any) -> dict[str, Any]:
    """The fields of an input, or none if the profile didn't find its entity."""
    return fields if entity else {}


def _mapping(**values: list[str]) -> dict[str, list[str]]:
    return {target.value: values.get(target.value, []) for target in Target}


def _slots(find: Find, suffix: str) -> list[str]:
    """The Slots in order, up to the first one missing: a gap would shift the numbers."""
    found = (find("sensor", suffix.format(number)) for number in SLOTS)
    return [entity_id for entity_id in takewhile(bool, found) if entity_id]


def _anycubic(find: Find) -> dict[str, Any]:
    """chrisfore/anycubic_ha_local: unique ids `<serial>_<key>`, the ACE `<serial>_ace0_<key>`."""
    status = find("event", "_print_event")
    job = find("sensor", "_filename")
    filament = find("sensor", "_filament_used")
    slots = _slots(find, "_ace0_slot_{}")
    loaded = find("sensor", "_ace0_loaded_slot")
    thumbnail = find("image", "_object_top_view", "_object_thumbnail")
    camera = find("camera", "_camera")
    return {
        "status": _found(status, entity_id=status, attribute=None),
        "mapping": _found(
            status,
            **_mapping(
                running=["started", "resumed"],
                paused=["paused"],
                finished=["finished"],
                cancelled=["stopped"],
                fault=["error"],
                # The bed cool-down after a print.
                ignored=["clear_ready", "clear_done", "clear_failed"],
            ),
        ),
        "job": _found(job, entity_id=job, attribute=None)
        # The state is grams from a guessed density; the attribute is the measured length.
        | _found(
            filament,
            material={"entity_id": filament, "attribute": "length_mm", "unit": "mm"},
        )
        | _found(slots, slots=slots, colour_attribute="color")
        | _found(loaded, loaded_slot=loaded),
        "images": _found(thumbnail, thumbnail=thumbnail)
        | _found(camera, camera=camera, snapshot=True),
    }


def _anycubic_cloud(find: Find) -> dict[str, Any]:
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
        "status": _found(status, entity_id=status, attribute=None),
        "mapping": _found(
            status,
            **_mapping(
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
        "job": _found(job, entity_id=job, attribute=None)
        | _found(
            filament, material={"entity_id": filament, "attribute": None, "unit": "mm"}
        )
        | _found(slots, slots=slots, colour_attribute="color_hex")
        | _found(loaded, loaded_slot=loaded),
        "images": _found(thumbnail, thumbnail=thumbnail)
        | _found(camera, camera=camera, snapshot=True),
    }


def _washdata(find: Find) -> dict[str, Any]:
    """3dg1luk43/ha_washdata: unique ids `<entry id>_<key>`.

    Its energy and cost sensors are left alone: electricity is the plug's meter.
    """
    status = find("sensor", "_washer_state")
    program = find("sensor", "_washer_program")
    return {
        "status": _found(status, entity_id=status, attribute=None),
        "mapping": _found(
            status,
            **_mapping(
                running=["running", "ending"],
                paused=["paused", "user_paused"],
                # Anti-wrinkle and clean only wait for the door to open.
                finished=["finished", "anti_wrinkle", "clean"],
                cancelled=["interrupted", "force_stopped"],
                ignored=["off", "idle", "starting", "delay_wait", "unknown"],
            ),
        ),
        "program": _found(program, entity_id=program, attribute=None),
    }


def _miele(find: Find) -> dict[str, Any]:
    """HA core `miele`: unique ids `<serial>-<key>`.

    Its energy and water sensors count the current cycle and reset at the next one.
    """
    status = find("sensor", "-state_status")
    program = find("sensor", "-state_program_id")
    energy = find("sensor", "-current_energy_consumption")
    water = find("sensor", "-current_water_consumption")
    return {
        "status": _found(status, entity_id=status, attribute=None),
        "mapping": _found(
            status,
            **_mapping(
                running=["in_use"],
                paused=["pause", "rinse_hold"],
                finished=["program_ended"],
                cancelled=["program_interrupted"],
                fault=["failure"],
                ignored=[
                    "off",
                    "on",
                    "programmed",
                    "waiting_to_start",
                    "idle",
                    "service",
                    "not_connected",
                ],
            ),
        ),
        "program": _found(program, entity_id=program, attribute=None),
        "consumption": _found(
            energy,
            source=ConsumptionSource.ENERGY.value,
            entity_id=energy,
            attribute=None,
        ),
        "water": _found(
            water, source=WaterSource.METER.value, entity_id=water, attribute=None
        ),
    }


def _home_connect(find: Find) -> dict[str, Any]:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`."""
    status = find("sensor", "-BSH.Common.Status.OperationState")
    program = find("select", "-BSH.Common.Root.ActiveProgram")
    return {
        "status": _found(status, entity_id=status, attribute=None),
        "mapping": _found(
            status,
            **_mapping(
                running=["run"],
                paused=["pause", "actionrequired"],
                finished=["finished"],
                cancelled=["aborting"],
                fault=["error"],
                ignored=["inactive", "ready", "delayedstart"],
            ),
        ),
        "program": _found(program, entity_id=program, attribute=None),
    }


# By Device Type, then integration domain.
PROFILES = {
    DEVICE_TYPE_3D_PRINTER: {"anycubic": _anycubic, "anycubic_cloud": _anycubic_cloud},
    DEVICE_TYPE_WASHING_MACHINE: {
        "ha_washdata": _washdata,
        "miele": _miele,
        "home_connect": _home_connect,
    },
}


def detect(
    hass: HomeAssistant, device_type: str, device_id: str | None
) -> dict[str, Any] | None:
    """The Device Input sections the HA device's profile fills in.

    None if the device belongs to no integration known for the Device Type. Inputs
    the profile can't find are left out of their section, and the mapping with the
    Status.
    """
    profiles = PROFILES.get(device_type, {})
    devices = dr.async_get(hass)
    ha_device = devices.async_get(device_id) if device_id else None
    if ha_device is None:
        return None
    config_entry = next(
        (
            config_entry
            for entry_id in ha_device.config_entries
            if (config_entry := hass.config_entries.async_get_entry(entry_id))
            and config_entry.domain in profiles
        ),
        None,
    )
    if config_entry is None:
        return None
    domain = config_entry.domain
    # A multi-material unit is its own HA device, linked to the printer's.
    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(devices, config_entry.entry_id)
        if ha_device.id in (device.id, device.via_device_id)
    ]
    entities = er.async_get(hass)
    candidates = [
        entity
        for device in device_ids
        for entity in er.async_entries_for_device(entities, device)
        if entity.platform == domain
    ]

    def find(platform: str, *suffixes: str) -> str | None:
        return next(
            (
                entity.entity_id
                for suffix in suffixes
                for entity in candidates
                if entity.domain == platform and entity.unique_id.endswith(suffix)
            ),
            None,
        )

    return profiles[domain](find)
