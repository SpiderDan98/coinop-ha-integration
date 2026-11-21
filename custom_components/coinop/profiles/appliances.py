"""Integration Profiles and kind checks of appliance integrations."""

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


def home_connect(find: Find) -> dict[str, Any]:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`."""
    status = find("sensor", "-BSH.Common.Status.OperationState")
    program = find("select", "-BSH.Common.Root.ActiveProgram")
    return {
        "status": found(status, entity_id=status, attribute=None),
        "mapping": found(
            status,
            **mapping(
                running=["run"],
                paused=["pause", "actionrequired"],
                finished=["finished"],
                cancelled=["aborting"],
                fault=["error"],
                ignored=["inactive", "ready", "delayedstart"],
            ),
        ),
        "program": found(program, entity_id=program, attribute=None),
    }


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
