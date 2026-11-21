"""Integration Profiles: Device Input defaults for known integrations.

A profile only pre-fills the Add Device and Detect again steps; the Device stores the
concrete entities it found, so nothing stays coupled to the profile (ADR 0004).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from itertools import takewhile
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DEVICE_TYPE_3D_PRINTER,
    DEVICE_TYPE_COFFEE_MACHINE,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_OVEN,
    DEVICE_TYPE_TUMBLE_DRYER,
    DEVICE_TYPE_WASHING_MACHINE,
)
from .device_config import ConsumptionSource, Target, WaterSource
from .quantities import ELECTRICITY, WATER

# Finds the entity of a platform whose unique id ends in one of the suffixes, in order.
# A Device Input must be enabled; `disabled=True` also finds a disabled entity, which
# still tells a kind check that the integration registered it.
Find = Callable[..., str | None]


class NoDeviceType(Enum):
    """What a kind check answers for an HA device it has no Device Type for."""

    NOT_A_DEVICE = "not_a_device"
    CANT_TELL = "cant_tell"


# Tells an HA device's kind from its entities, its registry entry and its config entry.
KindCheck = Callable[[Find, dr.DeviceEntry, ConfigEntry], str | NoDeviceType]


@dataclass(frozen=True)
class Integration:
    """A known integration: its name, the profile that finds its Device Inputs, the
    Device Types it serves and how it tells which of them an HA device is."""

    name: str
    profile: Callable[[Find], dict[str, Any]]
    device_types: tuple[str, ...]
    kind: KindCheck


SLOTS = range(1, 5)
# Sections a profile pre-fills only in Add Device: Detect again leaves them alone.
METERS = (ELECTRICITY.source_key, WATER.source_key)
# WashData's program sensor until it recognises a program (its match_rules.py).
WASHDATA_PLACEHOLDERS = [
    "off",
    "starting",
    "detecting...",
    "restored...",
    "none",
    "unknown",
]


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
        "program": _found(
            program, entity_id=program, attribute=None, ignored=WASHDATA_PLACEHOLDERS
        ),
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


def _always(device_type: str) -> KindCheck:
    return lambda *_: device_type


# WashData's device types (`DEVICE_TYPES` in its const.py) that say what the device
# is. Its `generic` and `other` say nothing, so they aren't listed.
WASHDATA_KINDS: dict[str, str | NoDeviceType] = {
    "washing_machine": DEVICE_TYPE_WASHING_MACHINE,
    "washer_dryer": DEVICE_TYPE_WASHING_MACHINE,
    "dryer": DEVICE_TYPE_TUMBLE_DRYER,
    "dishwasher": DEVICE_TYPE_DISHWASHER,
    "pump": NoDeviceType.NOT_A_DEVICE,
}


def _washdata_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The kind the user picked in WashData: in its config entry's data when the
    entry was created, in its options once changed, a washing machine without one."""
    kind = config_entry.options.get(
        "device_type", config_entry.data.get("device_type", "washing_machine")
    )
    return WASHDATA_KINDS.get(kind, NoDeviceType.CANT_TELL)


# Event sensors `home_connect` registers for an appliance's type alone (`EVENT_SENSORS`
# in its sensor.py), by unique id suffix; the first one found tells the kind. Each
# is registered since Home Assistant 2026.5, the minimum.
HOME_CONNECT_KINDS: dict[str, str | NoDeviceType] = {
    "-LaundryCare.Washer.Event.IDos1FillLevelPoor": DEVICE_TYPE_WASHING_MACHINE,
    "-LaundryCare.Dryer.Event.DryingProcessFinished": DEVICE_TYPE_TUMBLE_DRYER,
    "-Dishcare.Dishwasher.Event.SaltNearlyEmpty": DEVICE_TYPE_DISHWASHER,
    "-ConsumerProducts.CoffeeMaker.Event.BeanContainerEmpty": (
        DEVICE_TYPE_COFFEE_MACHINE
    ),
    "-Cooking.Oven.Event.RegularPreheatFinished": DEVICE_TYPE_OVEN,
    "-Refrigeration.FridgeFreezer.Event.DoorAlarmRefrigerator": (
        NoDeviceType.NOT_A_DEVICE
    ),
    "-Refrigeration.FridgeFreezer.Event.DoorAlarmFreezer": NoDeviceType.NOT_A_DEVICE,
    "-Cooking.Common.Event.Hood.GreaseFilterMaxSaturationReached": (
        NoDeviceType.NOT_A_DEVICE
    ),
    "-ConsumerProducts.CleaningRobot.Event.RobotIsStuck": NoDeviceType.NOT_A_DEVICE,
    # A hob: an oven has the alarm clock too, and was told above.
    "-BSH.Common.Event.AlarmClockElapsed": NoDeviceType.NOT_A_DEVICE,
}
# Sensors several types share (`BSH_PROGRAM_SENSORS` and an event sensor): which of
# them it has tells a type no event sensor is registered for alone.
HOME_CONNECT_SHARED = (
    "-BSH.Common.Event.ProgramAborted",
    "-BSH.Common.Option.RemainingProgramTime",
    "-BSH.Common.Option.ProgramProgress",
)
HOME_CONNECT_SHARED_KINDS: dict[tuple[bool, ...], str | NoDeviceType] = {
    # A microwave: a dishwasher has all three too, and was told by its own.
    (True, True, True): DEVICE_TYPE_OVEN,
    # A cook processor.
    (True, True, False): NoDeviceType.NOT_A_DEVICE,
    # A warming drawer or an air conditioner.
    (False, False, True): NoDeviceType.NOT_A_DEVICE,
}


def _home_connect_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The kind the sensors registered for the appliance's type tell: nothing on the
    HA device does, its model is the product code. The event sensors are disabled
    until the user enables them."""

    def registered(suffix: str) -> bool:
        return find("sensor", suffix, disabled=True) is not None

    for suffix, kind in HOME_CONNECT_KINDS.items():
        if registered(suffix):
            return kind
    return HOME_CONNECT_SHARED_KINDS.get(
        tuple(registered(suffix) for suffix in HOME_CONNECT_SHARED),
        NoDeviceType.CANT_TELL,
    )


# By integration domain, in the order Quick Start and the HA device step list them.
INTEGRATIONS = {
    "anycubic": Integration(
        "Anycubic 3D Printer - Local Control",
        _anycubic,
        (DEVICE_TYPE_3D_PRINTER,),
        _always(DEVICE_TYPE_3D_PRINTER),
    ),
    "anycubic_cloud": Integration(
        "Anycubic Cloud & LAN",
        _anycubic_cloud,
        (DEVICE_TYPE_3D_PRINTER,),
        _always(DEVICE_TYPE_3D_PRINTER),
    ),
    "ha_washdata": Integration(
        "WashData",
        _washdata,
        (
            DEVICE_TYPE_WASHING_MACHINE,
            DEVICE_TYPE_DISHWASHER,
            DEVICE_TYPE_TUMBLE_DRYER,
            DEVICE_TYPE_COFFEE_MACHINE,
            DEVICE_TYPE_OVEN,
        ),
        _washdata_kind,
    ),
    "miele": Integration(
        "Miele",
        _miele,
        (DEVICE_TYPE_WASHING_MACHINE,),
        _always(DEVICE_TYPE_WASHING_MACHINE),
    ),
    "home_connect": Integration(
        "Home Connect",
        _home_connect,
        (
            DEVICE_TYPE_WASHING_MACHINE,
            DEVICE_TYPE_DISHWASHER,
            DEVICE_TYPE_TUMBLE_DRYER,
            DEVICE_TYPE_COFFEE_MACHINE,
            DEVICE_TYPE_OVEN,
        ),
        _home_connect_kind,
    ),
}


def _serving(device_type: str) -> dict[str, Integration]:
    return {
        domain: integration
        for domain, integration in INTEGRATIONS.items()
        if device_type in integration.device_types
    }


def known_integrations(device_type: str) -> str:
    """The names of the integrations with a profile for the Device Type."""
    return ", ".join(integration.name for integration in _serving(device_type).values())


def _finder(hass: HomeAssistant, device_id: str, config_entry: ConfigEntry) -> Find:
    """Finds the integration's entities of the HA device and the devices linked to it."""
    # A multi-material unit is its own HA device, linked to the printer's.
    device_ids = [
        device.id
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), config_entry.entry_id
        )
        if device_id in (device.id, device.via_device_id)
    ]
    entities = er.async_get(hass)
    candidates = [
        entity
        for device in device_ids
        for entity in er.async_entries_for_device(
            entities, device, include_disabled_entities=True
        )
        if entity.platform == config_entry.domain
    ]

    def find(platform: str, *suffixes: str, disabled: bool = False) -> str | None:
        return next(
            (
                entity.entity_id
                for suffix in suffixes
                for entity in candidates
                if entity.domain == platform
                and entity.unique_id.endswith(suffix)
                and (disabled or not entity.disabled)
            ),
            None,
        )

    return find


def detect(
    hass: HomeAssistant, device_type: str, device_id: str | None
) -> dict[str, Any] | None:
    """The Device Input sections the HA device's profile fills in.

    None if the device belongs to no integration that serves the Device Type; what
    kind of device it is isn't asked. Inputs the profile can't find are left out of
    their section, and the mapping with the Status.
    """
    serving = _serving(device_type)
    ha_device = dr.async_get(hass).async_get(device_id) if device_id else None
    if ha_device is None:
        return None
    config_entry = next(
        (
            config_entry
            for entry_id in ha_device.config_entries
            if (config_entry := hass.config_entries.async_get_entry(entry_id))
            and config_entry.domain in serving
        ),
        None,
    )
    if config_entry is None:
        return None
    return serving[config_entry.domain].profile(
        _finder(hass, ha_device.id, config_entry)
    )


@dataclass(frozen=True)
class Candidate:
    """An HA device Quick Start can add: the Device Types it can be added as (one
    where its integration tells its kind, else those the integration serves), its
    integration's name and the sections its profile fills in."""

    device_types: tuple[str, ...]
    integration: str
    sections: dict[str, Any]


def candidates(hass: HomeAssistant) -> dict[str, Candidate]:
    """The HA devices Quick Start can add, by device id.

    Those are the devices a profile finds a Status for, so not a multi-material unit,
    and whose kind is a Device Type or can't be told.
    """
    devices = dr.async_get(hass)
    found: dict[str, Candidate] = {}
    for domain, integration in INTEGRATIONS.items():
        for config_entry in hass.config_entries.async_entries(
            domain, include_ignore=False, include_disabled=False
        ):
            for device in dr.async_entries_for_config_entry(
                devices, config_entry.entry_id
            ):
                find = _finder(hass, device.id, config_entry)
                sections = integration.profile(find)
                if not sections["status"]:
                    continue
                kind = integration.kind(find, device, config_entry)
                if kind is NoDeviceType.NOT_A_DEVICE:
                    continue
                device_types = (
                    integration.device_types
                    if kind is NoDeviceType.CANT_TELL
                    else (kind,)
                )
                found.setdefault(
                    device.id, Candidate(device_types, integration.name, sections)
                )
    return found
