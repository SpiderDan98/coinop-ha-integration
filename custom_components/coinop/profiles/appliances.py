"""Integration Profiles and kind checks of appliance integrations."""

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from custom_components.coinop.const import (
    DEVICE_TYPE_COFFEE_MACHINE,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_OVEN,
    DEVICE_TYPE_TUMBLE_DRYER,
    DEVICE_TYPE_WASHING_MACHINE,
)
from custom_components.coinop.device_config import ConsumptionSource, WaterSource

from .base import Find, NoDeviceType, found, mapping

# The Device Types an appliance of WashData, Miele or Home Connect can be.
DEVICE_TYPES = (
    DEVICE_TYPE_WASHING_MACHINE,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_TUMBLE_DRYER,
    DEVICE_TYPE_COFFEE_MACHINE,
    DEVICE_TYPE_OVEN,
)
# WashData's program sensor until it recognises a program (its match_rules.py).
WASHDATA_PLACEHOLDERS = [
    "off",
    "starting",
    "detecting...",
    "restored...",
    "none",
    "unknown",
]


def washdata(find: Find) -> dict[str, Any]:
    """3dg1luk43/ha_washdata: unique ids `<entry id>_<key>`.

    Its energy and cost sensors are left alone: electricity is the plug's meter.
    """
    status = find("sensor", "_washer_state")
    program = find("sensor", "_washer_program")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                running=["running", "ending"],
                paused=["paused", "user_paused"],
                # Anti-wrinkle and clean only wait for the door to open.
                finished=["finished", "anti_wrinkle", "clean"],
                cancelled=["interrupted", "force_stopped"],
                ignored=["off", "idle", "starting", "delay_wait", "unknown"],
            ),
        ),
        "program": found(
            program, entity_id=program, attribute=None, ignored=WASHDATA_PLACEHOLDERS
        ),
    }


def miele(find: Find) -> dict[str, Any]:
    """HA core `miele`: unique ids `<serial>-<key>`.

    Its energy and water sensors count the current cycle and reset at the next one.
    """
    status = find("sensor", "-state_status")
    program = find("sensor", "-state_program_id")
    energy = find("sensor", "-current_energy_consumption")
    water = find("sensor", "-current_water_consumption")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
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
        "program": found(program, entity_id=program, attribute=None),
        "consumption": found(
            energy,
            source=ConsumptionSource.ENERGY.value,
            entity_id=energy,
            attribute=None,
        ),
        "water": found(
            water, source=WaterSource.METER.value, entity_id=water, attribute=None
        ),
    }


# The Home Connect API's operation states, `BSH.Common.EnumType.OperationState.<state>`.
HOME_CONNECT_STATES = {
    "running": ["Run"],
    "paused": ["Pause", "ActionRequired"],
    "finished": ["Finished"],
    "cancelled": ["Aborting"],
    "fault": ["Error"],
    "ignored": ["Inactive", "Ready", "DelayedStart"],
}


def _operation_state(
    status: str | None, program: str | None, state: Callable[[str], str]
) -> dict[str, Any]:
    """A Home Connect appliance's inputs, its operation states as `state` reports
    them."""
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                **{
                    target: [state(value) for value in values]
                    for target, values in HOME_CONNECT_STATES.items()
                }
            ),
        ),
        "program": found(program, entity_id=program, attribute=None),
    }


def home_connect(find: Find) -> dict[str, Any]:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`."""
    return _operation_state(
        find("sensor", "-BSH.Common.Status.OperationState"),
        find("select", "-BSH.Common.Root.ActiveProgram"),
        str.lower,
    )


def home_connect_local(find: Find) -> dict[str, Any]:
    """chris-mc1/homeconnect_local_hass (`homeconnect_ws`): unique ids
    `<device id>-<key>`, states as HA core's `home_connect` reports them."""
    return _operation_state(
        find("sensor", "-sensor_operation_state"),
        find("sensor", "-sensor_active_program"),
        str.lower,
    )


def home_connect_alt(find: Find) -> dict[str, Any]:
    """ekutner/home-connect-hass (`home_connect_alt`): unique ids
    `<haId>_<BSH key in lower case, dots as underscores>`, states the API's own unless
    its translation mode is `server`, which reports the display texts instead."""
    return _operation_state(
        find("sensor", "_bsh_common_status_operationstate"),
        find("sensor", "_active_program"),
        "BSH.Common.EnumType.OperationState.{}".format,
    )


# WashData's device types (`DEVICE_TYPES` in its const.py) that say what the device
# is. Its `generic` and `other` say nothing, so they aren't listed.
WASHDATA_KINDS: dict[str, str | NoDeviceType] = {
    "washing_machine": DEVICE_TYPE_WASHING_MACHINE,
    "washer_dryer": DEVICE_TYPE_WASHING_MACHINE,
    "dryer": DEVICE_TYPE_TUMBLE_DRYER,
    "dishwasher": DEVICE_TYPE_DISHWASHER,
    "pump": NoDeviceType.NOT_A_DEVICE,
}


def washdata_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The kind the user picked in WashData: in its config entry's data when the
    entry was created, in its options once changed, a washing machine without one."""
    kind = config_entry.options.get(
        "device_type", config_entry.data.get("device_type", "washing_machine")
    )
    return WASHDATA_KINDS.get(kind, NoDeviceType.CANT_TELL)


# The models HA core's `miele` gives an HA device that are a Device Type: an appliance
# type's tag (`DEVICE_TYPE_TAGS` in its const.py), capitalised, underscores as spaces.
MIELE_KINDS = {
    "Washing machine": DEVICE_TYPE_WASHING_MACHINE,
    "Washer dryer": DEVICE_TYPE_WASHING_MACHINE,
    "Tumble dryer": DEVICE_TYPE_TUMBLE_DRYER,
    "Dishwasher": DEVICE_TYPE_DISHWASHER,
    "Coffee system": DEVICE_TYPE_COFFEE_MACHINE,
    "Oven": DEVICE_TYPE_OVEN,
    "Oven microwave": DEVICE_TYPE_OVEN,
    "Steam oven": DEVICE_TYPE_OVEN,
    "Steam oven combi": DEVICE_TYPE_OVEN,
    "Steam oven micro": DEVICE_TYPE_OVEN,
    "Dialog oven": DEVICE_TYPE_OVEN,
    "Microwave": DEVICE_TYPE_OVEN,
}


def miele_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The appliance type Miele reports, which every appliance has: any other model
    is a fridge, a hob, a hood or another appliance that is no Device Type."""
    return MIELE_KINDS.get(device.model or "", NoDeviceType.NOT_A_DEVICE)


# From `EVENT_SENSORS` in its sensor.py as Home Assistant 2026.5, the minimum, has them.
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


def home_connect_kind(
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


def cant_tell(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> NoDeviceType:
    """Home Connect Local and Home Connect Alt: Quick Start asks the Device Type."""
    return NoDeviceType.CANT_TELL


LG_THINQ_DEVICE_TYPES = (
    DEVICE_TYPE_WASHING_MACHINE,
    DEVICE_TYPE_TUMBLE_DRYER,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_OVEN,
)


def lg_thinq(find: Find) -> dict[str, Any]:
    """HA core `lg_thinq`: unique ids `<device id>_<property>`, a property with a
    location as `<location>_<key>` (a washer's `main`, an oven's `oven`).

    Its energy sensors count per day and month, so no meter is pre-filled. Of a
    TWINWash or a double oven, whose halves share an HA device, the main washer or
    the upper cavity is read.
    """
    status = find(
        "sensor", "_main_current_state", "_upper_current_state", "_current_state"
    )
    program = find("sensor", "_current_dish_washing_course")
    return {
        "status": found(status, entity_id=status, attribute=None),
        # The integration has one list of states for all appliances (its strings.json).
        "mapping": found(
            status,
            **mapping(
                running=[
                    "running",
                    "detecting",
                    "display_loadsize",
                    "detergent_amount",
                    "dispensing",
                    "add_drain",
                    "prewash",
                    "soaking",
                    "softening",
                    "steam_softening",
                    "rinsing",
                    "spinning",
                    "refreshing",
                    "steam",
                    "drying",
                    "cool_down",
                    "end_cooling",
                    "checking_turbidity",
                    "night_dry",
                    "sterilize",
                    "smart_grid_run",
                    "preheat",
                    "preheating",
                    "preheat_complete",
                    "preheating_is_done",
                    "temperature_stabilization",
                    "proofing",
                    "cook",
                    "cooking_in_progress",
                    "cooling",
                    "cleaning",
                ],
                paused=["pause", "paused", "rinse_hold"],
                # Wrinkle care only tumbles the dry load until the door opens.
                finished=[
                    "end",
                    "complete",
                    "done",
                    "running_end",
                    "cook_complete",
                    "cleaning_is_done",
                    "wrinkle_care",
                ],
                cancelled=["cancel"],
                fault=["error", "as_pop_up", "power_fail"],
                # Freeze protection runs by itself and is no cycle.
                ignored=[
                    "power_off",
                    "power_on",
                    "initial",
                    "initializing",
                    "standby",
                    "sleep",
                    "reserved",
                    "reservation",
                    "macrosector",
                    "setdate",
                    "preference",
                    "change_condition",
                    "lock",
                    "diagnosis",
                    "firmware",
                    "fota",
                    "frozen_prevent_initial",
                    "frozen_prevent_running",
                    "frozen_prevent_pause",
                ],
            ),
        ),
        "program": found(program, entity_id=program, attribute=None),
    }


# thinqconnect's `DeviceType`s that are a Device Type: a Styler, a fridge, an air
# conditioner and every other type are not.
LG_THINQ_KINDS = {
    "DEVICE_WASHER": DEVICE_TYPE_WASHING_MACHINE,
    "DEVICE_WASHCOMBO_MAIN": DEVICE_TYPE_WASHING_MACHINE,
    "DEVICE_WASHCOMBO_MINI": DEVICE_TYPE_WASHING_MACHINE,
    "DEVICE_WASHTOWER_WASHER": DEVICE_TYPE_WASHING_MACHINE,
    "DEVICE_DRYER": DEVICE_TYPE_TUMBLE_DRYER,
    "DEVICE_WASHTOWER_DRYER": DEVICE_TYPE_TUMBLE_DRYER,
    "DEVICE_DISH_WASHER": DEVICE_TYPE_DISHWASHER,
    "DEVICE_OVEN": DEVICE_TYPE_OVEN,
    "DEVICE_MICROWAVE_OVEN": DEVICE_TYPE_OVEN,
}
# A WashTower is an HA device per half, whose locations are its sub ids.
LG_THINQ_WASHTOWER_HALVES = {
    "_washer_current_state": DEVICE_TYPE_WASHING_MACHINE,
    "_dryer_current_state": DEVICE_TYPE_TUMBLE_DRYER,
}


def lg_thinq_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The device type the integration writes into the model, `<model> (<type>)`."""
    device_type = (device.model or "").rpartition("(")[2].removesuffix(")")
    if device_type == "DEVICE_WASHTOWER":
        return next(
            (
                kind
                for suffix, kind in LG_THINQ_WASHTOWER_HALVES.items()
                if find("sensor", suffix)
            ),
            NoDeviceType.NOT_A_DEVICE,
        )
    return LG_THINQ_KINDS.get(device_type, NoDeviceType.NOT_A_DEVICE)


SMARTTHINGS_DEVICE_TYPES = (
    DEVICE_TYPE_WASHING_MACHINE,
    DEVICE_TYPE_DISHWASHER,
    DEVICE_TYPE_TUMBLE_DRYER,
    DEVICE_TYPE_OVEN,
)
# By capability with a machine state sensor: the kind it tells, and its running,
# paused and finished values (finished is also the idle state).
SMARTTHINGS_MACHINE_STATES = {
    "washerOperatingState": (DEVICE_TYPE_WASHING_MACHINE, "run", "pause", "stop"),
    "dryerOperatingState": (DEVICE_TYPE_TUMBLE_DRYER, "run", "pause", "stop"),
    "dishwasherOperatingState": (DEVICE_TYPE_DISHWASHER, "run", "pause", "stop"),
    "ovenOperatingState": (DEVICE_TYPE_OVEN, "running", "paused", "ready"),
}


def _smartthings_machine_state(
    find: Find, *, disabled: bool = False
) -> tuple[str, str] | None:
    """The `main` component's machine state sensor and its capability: a washer's
    upper washer and an oven's second cavity have one of their own."""
    return next(
        (
            (status, capability)
            for capability in SMARTTHINGS_MACHINE_STATES
            if (
                status := find(
                    "sensor",
                    f"_main_{capability}_machineState_machineState",
                    disabled=disabled,
                )
            )
        ),
        None,
    )


def smartthings(find: Find) -> dict[str, Any]:
    """HA core `smartthings`: unique ids
    `<device id>_<component>_<capability>_<attribute>_<key>`.

    Its machine state doesn't tell a finished cycle from a stopped one, so every
    Run ends as Completed. It reports no program a Run could be named after.
    """
    machine_state = _smartthings_machine_state(find)
    if machine_state is None:
        return {"status": {}, "mapping": {}}
    status, capability = machine_state
    _, running, paused, finished = SMARTTHINGS_MACHINE_STATES[capability]
    energy = find(
        "sensor", "_main_powerConsumptionReport_powerConsumption_energy_meter"
    )
    return {
        "status": {"entity_id": status, "attribute": None},
        "mapping": mapping(running=[running], paused=[paused], finished=[finished]),
        "consumption": found(
            energy,
            source=ConsumptionSource.ENERGY.value,
            entity_id=energy,
            attribute=None,
        ),
    }


# What a steam closet (an AirDresser) registers along with a dryer's machine state.
SMARTTHINGS_STEAM_CLOSET = {
    "binary_sensor": (
        "_main_samsungce.steamClosetKeepFreshMode_operatingState_operatingState"
    ),
    "switch": "_main_samsungce.steamClosetSanitizeMode_status_status",
}


def smartthings_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """The kind the capability of the machine state sensor tells; a device without
    one is a TV, a fridge or another device that is no Device Type."""
    machine_state = _smartthings_machine_state(find, disabled=True)
    if machine_state is None or any(
        find(platform, suffix, disabled=True)
        for platform, suffix in SMARTTHINGS_STEAM_CLOSET.items()
    ):
        return NoDeviceType.NOT_A_DEVICE
    return SMARTTHINGS_MACHINE_STATES[machine_state[1]][0]
