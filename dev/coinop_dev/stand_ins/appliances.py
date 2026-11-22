"""How the appliance integrations register an appliance, with what tells its kind.

Their states are those of an appliance that is switched off or waits for a program.
"""

from typing import Any

from homeassistant.util import slugify

from . import ENTRY_ID, EntityShape, HaDeviceShape, Registration

# A timestamp sensor's state, and that of one whose time hasn't come.
TIME = "2026-05-01T09:30:00+00:00"
NO_TIME = "unknown"


def washdata(
    device_type: str | None = "washing_machine",
    *,
    name: str = "Washer",
    changed_to: str | None = None,
) -> Registration:
    """3dg1luk43/ha_washdata: one HA device per config entry, named after it, unique
    ids `<entry id>_<key>`.

    `device_type` is the kind picked when the entry was created, which WashData keeps
    in the entry's data (None: an entry without one, which WashData reads as a washing
    machine). `changed_to` is a kind picked later: it goes to the options, and the
    data keeps the old one.
    """
    settings = {"power_sensor": "sensor.plug_power", "min_power": 2.0}
    kind = {} if device_type is None else {"device_type": device_type}
    sensors = {
        "washer_state": (None, "off"),
        "washer_program": (None, "off"),
        "current_power": ("W", "0"),
        "energy_total": ("kWh", "123.4"),
        "last_cycle_energy": ("kWh", "0.9"),
        "last_cycle_cost": (None, "0.27"),
        # Carries WashData's own projection as attributes while a cycle runs.
        "cycle_progress": ("%", "0"),
        "time_remaining": ("min", "0"),
    }
    return Registration(
        "ha_washdata",
        (
            HaDeviceShape(
                {
                    "identifiers": {("ha_washdata", ENTRY_ID)},
                    "manufacturer": "WashData",
                    "name": name,
                },
                {
                    key: EntityShape(
                        "sensor",
                        f"{ENTRY_ID}_{key}",
                        state=state,
                        unit=unit,
                        object_id=key,
                    )
                    for key, (unit, state) in sensors.items()
                },
            ),
        ),
        entry={
            "title": name,
            "version": 3,
            "minor_version": 13,
            "data": {"name": name} | kind | settings,
            "options": {"device_type": changed_to} | settings if changed_to else {},
        },
    )


# HA core `miele`'s sensors by key: object id, unit and a state.
MIELE_SENSORS = {
    "state_status": ("status", None, "off"),
    "state_program_id": ("program", None, "no_program"),
    "state_program_phase": ("program_phase", None, "not_running"),
    "state_remaining_time": ("remaining_time", "min", "0"),
    "current_energy_consumption": ("energy_consumption", "kWh", "0"),
    "current_water_consumption": ("water_consumption", "L", "0"),
}
_STATUS = ("state_status",)
_PROGRAM = (
    *_STATUS,
    "state_program_id",
    "state_program_phase",
    "state_remaining_time",
)
_ENERGY = (*_PROGRAM, "current_energy_consumption")
_WATER = (*_ENERGY, "current_water_consumption")
# By the HA device's model (`DEVICE_TYPE_TAGS` in its const.py), its sensors' `types`.
MIELE_MODELS = {
    "Washing machine": _WATER,
    "Washer dryer": _WATER,
    "Dishwasher": _WATER,
    "Tumble dryer": _ENERGY,
    "Coffee system": _PROGRAM,
    "Oven": _PROGRAM,
    "Oven microwave": _PROGRAM,
    "Steam oven": _PROGRAM,
    "Steam oven combi": _PROGRAM,
    "Steam oven micro": _PROGRAM,
    "Dialog oven": _PROGRAM,
    "Microwave": _PROGRAM,
    "Warming drawer": _PROGRAM,
    "Hob": _STATUS,
    "Hood": _STATUS,
    "Refrigerator": _STATUS,
}


def miele(
    model: str = "Washing machine",
    *,
    serial: str = "000123456789",
    name: str | None = None,
) -> Registration:
    """HA core `miele`: every appliance of an account on one config entry, unique ids
    `<serial>-<key>`.

    `model` is the appliance's kind as the integration writes it on the HA device; it
    also decides which sensors the integration registers. `name` is the HA device's,
    its kind by default. A second appliance needs its own `serial`.
    """
    name = name or model
    return Registration(
        "miele",
        (
            HaDeviceShape(
                {
                    "identifiers": {("miele", serial)},
                    "manufacturer": "Miele",
                    "name": name,
                    "model": model,
                    "serial_number": serial,
                },
                {
                    key: EntityShape(
                        "sensor",
                        f"{serial}-{key}",
                        state=MIELE_SENSORS[key][2],
                        unit=MIELE_SENSORS[key][1],
                        object_id=f"{name} {MIELE_SENSORS[key][0]}",
                    )
                    for key in MIELE_MODELS[model]
                },
            ),
        ),
        account=True,
    )


# `APPLIANCES_WITH_PROGRAMS` in HA core `home_connect`'s const.py.
HOME_CONNECT_WITH_PROGRAMS = (
    "AirConditioner",
    "CleaningRobot",
    "CoffeeMaker",
    "Dishwasher",
    "Dryer",
    "Hood",
    "Microwave",
    "Oven",
    "WarmingDrawer",
    "Washer",
    "WasherDryer",
)
# `EVENT_SENSORS` in its sensor.py, without 17 more of a coffee maker.
HOME_CONNECT_EVENT_SENSORS = {
    "BSH.Common.Event.ProgramAborted": (
        "program_aborted",
        ("Dishwasher", "Microwave", "CleaningRobot", "CookProcessor"),
    ),
    "BSH.Common.Event.ProgramFinished": (
        "program_finished",
        (
            "Oven",
            "Dishwasher",
            "Washer",
            "Dryer",
            "Microwave",
            "WasherDryer",
            "CleaningRobot",
            "CookProcessor",
        ),
    ),
    "BSH.Common.Event.AlarmClockElapsed": (
        "alarm_clock_elapsed",
        ("Oven", "Cooktop", "Hob"),
    ),
    "BSH.Common.Event.Favorite.001.ExternalTrigger": (
        "favorite_short_press",
        ("Hood", "Cooktop", "Hob"),
    ),
    "BSH.Common.Event.Favorite.002.ExternalTrigger": (
        "favorite_long_press",
        ("Hood", "Cooktop", "Hob"),
    ),
    "Cooking.Oven.Event.PreheatFinished": (
        "preheat_finished",
        ("Oven", "Cooktop", "Hob"),
    ),
    "Cooking.Oven.Event.RegularPreheatFinished": (
        "regular_preheat_finished",
        ("Oven",),
    ),
    "LaundryCare.Dryer.Event.DryingProcessFinished": (
        "drying_process_finished",
        ("Dryer",),
    ),
    "Dishcare.Dishwasher.Event.MachineCareAndFilterCleaningReminder": (
        "machine_care_and_filter_cleaning_reminder",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.MachineCareAndLowMaintenanceFilterCleaningReminder": (
        "machine_care_and_low_maintenance_filter_cleaning_reminder",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.MachineCareReminder": (
        "machine_care_reminder",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.ProgramBlockedSaltLack": (
        "program_blocked_salt_lack",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.SaltLack": ("salt_lack", ("Dishwasher",)),
    "Dishcare.Dishwasher.Event.SaltNearlyEmpty": (
        "salt_nearly_empty",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.RinseAidLack": ("rinse_aid_lack", ("Dishwasher",)),
    "Dishcare.Dishwasher.Event.RinseAidNearlyEmpty": (
        "rinse_aid_nearly_empty",
        ("Dishwasher",),
    ),
    "Dishcare.Dishwasher.Event.SmartFilterCleaningReminder": (
        "smart_filter_cleaning_reminder",
        ("Dishwasher",),
    ),
    "ConsumerProducts.CoffeeMaker.Event.BeanContainerEmpty": (
        "bean_container_empty",
        ("CoffeeMaker",),
    ),
    "ConsumerProducts.CoffeeMaker.Event.WaterTankEmpty": (
        "water_tank_empty",
        ("CoffeeMaker",),
    ),
    "ConsumerProducts.CoffeeMaker.Event.DripTrayFull": (
        "drip_tray_full",
        ("CoffeeMaker",),
    ),
    "Refrigeration.FridgeFreezer.Event.DoorAlarmFreezer": (
        "freezer_door_alarm",
        ("FridgeFreezer", "Freezer"),
    ),
    "Refrigeration.FridgeFreezer.Event.DoorAlarmRefrigerator": (
        "refrigerator_door_alarm",
        ("FridgeFreezer", "Refrigerator"),
    ),
    "Refrigeration.FridgeFreezer.Event.TemperatureAlarmFreezer": (
        "freezer_temperature_alarm",
        ("FridgeFreezer", "Freezer"),
    ),
    "ConsumerProducts.CleaningRobot.Event.EmptyDustBoxAndCleanFilter": (
        "empty_dust_box_and_clean_filter",
        ("CleaningRobot",),
    ),
    "ConsumerProducts.CleaningRobot.Event.RobotIsStuck": (
        "robot_is_stuck",
        ("CleaningRobot",),
    ),
    "ConsumerProducts.CleaningRobot.Event.DockingStationNotFound": (
        "docking_station_not_found",
        ("CleaningRobot",),
    ),
    "LaundryCare.Washer.Event.IDos1FillLevelPoor": (
        "poor_i_dos_1_fill_level",
        ("Washer", "WasherDryer"),
    ),
    "LaundryCare.Washer.Event.IDos2FillLevelPoor": (
        "poor_i_dos_2_fill_level",
        ("Washer", "WasherDryer"),
    ),
    "Cooking.Common.Event.Hood.GreaseFilterMaxSaturationNearlyReached": (
        "grease_filter_max_saturation_nearly_reached",
        ("Hood",),
    ),
    "Cooking.Common.Event.Hood.GreaseFilterMaxSaturationReached": (
        "grease_filter_max_saturation_reached",
        ("Hood",),
    ),
}
# `BSH_PROGRAM_SENSORS` in its sensor.py.
HOME_CONNECT_PROGRAM_SENSORS = {
    "BSH.Common.Option.RemainingProgramTime": (
        "program_finish_time",
        (
            "CoffeeMaker",
            "CookProcessor",
            "Dishwasher",
            "Dryer",
            "Microwave",
            "Hood",
            "Oven",
            "Washer",
            "WasherDryer",
        ),
    ),
    "BSH.Common.Option.ProgramProgress": (
        "program_progress",
        HOME_CONNECT_WITH_PROGRAMS,
    ),
}
# The types Home Assistant 2026.5, Coin-op's minimum, registers fewer event sensors for.
HOME_CONNECT_MINIMUM_HA: dict[str, tuple[str, ...]] = {
    "BSH.Common.Event.AlarmClockElapsed": ("Oven", "Cooktop"),
    "BSH.Common.Event.Favorite.001.ExternalTrigger": (),
    "BSH.Common.Event.Favorite.002.ExternalTrigger": (),
    "Cooking.Oven.Event.PreheatFinished": ("Oven", "Cooktop"),
    "Dishcare.Dishwasher.Event.MachineCareAndFilterCleaningReminder": (),
    "Dishcare.Dishwasher.Event.MachineCareAndLowMaintenanceFilterCleaningReminder": (),
    "Dishcare.Dishwasher.Event.MachineCareReminder": (),
    "Dishcare.Dishwasher.Event.ProgramBlockedSaltLack": (),
    "Dishcare.Dishwasher.Event.SaltLack": (),
    "Dishcare.Dishwasher.Event.RinseAidLack": (),
    "Dishcare.Dishwasher.Event.SmartFilterCleaningReminder": (),
}
# A program each appliance type with programs offers, by its BSH key.
HOME_CONNECT_PROGRAMS = {
    "CoffeeMaker": "ConsumerProducts.CoffeeMaker.Program.Beverage.Coffee",
    "Dishwasher": "Dishcare.Dishwasher.Program.Eco50",
    "Dryer": "LaundryCare.Dryer.Program.Cotton",
    "Oven": "Cooking.Oven.Program.HeatingMode.HotAir",
    "Washer": "LaundryCare.Washer.Program.Cotton",
    "WasherDryer": "LaundryCare.WasherDryer.Program.Cotton",
}


def home_connect_program(appliance_type: str) -> str:
    """A program of the type as HA core `home_connect` names a select's option."""
    key = HOME_CONNECT_PROGRAMS.get(appliance_type, "BSH.Common.Program.Favorite.001")
    return slugify(key.replace(".", "_"))


def home_connect(
    appliance_type: str = "Washer", *, name: str = "Washer", minimum_ha: bool = False
) -> Registration:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`.

    `appliance_type` is the API's type of the appliance, which is on no registry
    entry. It only decides what the integration registers: the event sensors of the
    type, disabled by default, and the program sensors, both even for an appliance
    that reports nothing, here as the locked Home Assistant does or, with
    `minimum_ha`, as Coin-op's minimum does. The operation state comes from what the
    appliance reports; every stand-in has one, so that it is its kind that decides
    whether Quick Start offers it. Every appliance of an account is on one config
    entry, a device of its own.
    """
    object_id = slugify(name)
    ha_id = f"SIEMENS-{object_id.upper()}-0123"

    def add(platform: str, key: str, suffix: str, **kwargs: Any) -> EntityShape:
        return EntityShape(
            platform, f"{ha_id}-{key}", object_id=f"{object_id}_{suffix}", **kwargs
        )

    event_sensors = {
        key: add("sensor", key, suffix, state="off", disabled=True)
        for key, (suffix, types) in HOME_CONNECT_EVENT_SENSORS.items()
        if appliance_type
        in (HOME_CONNECT_MINIMUM_HA.get(key, types) if minimum_ha else types)
    }
    program_sensors = {
        key: add("sensor", key, suffix, state=NO_TIME)
        for key, (suffix, types) in HOME_CONNECT_PROGRAM_SENSORS.items()
        if appliance_type in types
    }
    status = {
        "BSH.Common.Status.OperationState": add(
            "sensor",
            "BSH.Common.Status.OperationState",
            "operation_state",
            state="ready",
        )
    }
    program = home_connect_program(appliance_type)
    programs = (
        {
            "BSH.Common.Status.DoorState": add(
                "sensor", "BSH.Common.Status.DoorState", "door", state="closed"
            ),
            "BSH.Common.Root.SelectedProgram": add(
                "select",
                "BSH.Common.Root.SelectedProgram",
                "selected_program",
                state=program,
            ),
            "BSH.Common.Root.ActiveProgram": add(
                "select",
                "BSH.Common.Root.ActiveProgram",
                "active_program",
                state="unknown",
            ),
        }
        if appliance_type in HOME_CONNECT_WITH_PROGRAMS
        else {}
    )
    return Registration(
        "home_connect",
        (
            HaDeviceShape(
                {"identifiers": {("home_connect", ha_id)}, "name": name},
                event_sensors | program_sensors | status | programs,
            ),
        ),
        account=True,
    )


def home_connect_local(appliance_type: str = "Dishwasher") -> Registration:
    """chris-mc1/homeconnect_local_hass (domain `homeconnect_ws`): one appliance per
    config entry, unique ids `<device id>-<key>`, the API's appliance type as the HA
    device's model."""
    device_id = f"BOSCH-{appliance_type.upper()}-68A40E000000"
    name = f"Bosch {appliance_type}"
    program = home_connect_program(appliance_type)
    keys = {
        "sensor_operation_state": ("sensor", "ready", None),
        "sensor_active_program": ("sensor", "unknown", None),
        "sensor_door_state": ("sensor", "closed", None),
        "sensor_remaining_program_time": ("sensor", "0", "s"),
        "sensor_program_progress": ("sensor", "0", "%"),
        "select_program": ("select", program, None),
    }
    return Registration(
        "homeconnect_ws",
        (
            HaDeviceShape(
                {
                    "identifiers": {("homeconnect_ws", device_id)},
                    "manufacturer": "Bosch",
                    "model": appliance_type,
                    "name": name,
                },
                {
                    key: EntityShape(
                        platform,
                        f"{device_id}-{key}",
                        state=state,
                        unit=unit,
                        object_id=f"{name} {key[len(platform) + 1 :]}",
                    )
                    for key, (platform, state, unit) in keys.items()
                },
            ),
        ),
        entry={"title": appliance_type, "unique_id": device_id},
    )


def home_connect_alt(
    *, active_program: bool = True, name: str = "Washer"
) -> Registration:
    """ekutner/home-connect-hass (domain `home_connect_alt`): every appliance of an
    account on one config entry, unique ids `<haId>_<BSH key in lower case, dots as
    underscores>`, the haId in lower case with underscores; a washer named `name`
    here. Its active program sensor is registered only once the appliance has run a
    program while the integration was loaded. Its states are the API's own."""
    ha_id = "BOSCH-WAT28400-68A40E000000"
    safe_ha_id = ha_id.lower().replace("-", "_")
    program = HOME_CONNECT_PROGRAMS["Washer"]
    keys = {
        "BSH.Common.Status.OperationState": (
            "sensor",
            "operation_state",
            "BSH.Common.EnumType.OperationState.Ready",
        ),
        "BSH.Common.Status.DoorState": (
            "sensor",
            "door_state",
            "BSH.Common.EnumType.DoorState.Closed",
        ),
        "BSH.Common.Option.RemainingProgramTime": (
            "sensor",
            "remaining_program_time",
            NO_TIME,
        ),
        "BSH.Common.Option.ProgramProgress": ("sensor", "program_progress", "0"),
        "selected_program": ("sensor", "selected_program", program),
        "active_program": ("sensor", "active_program", "unknown"),
        "programs": ("select", "programs", program),
    }
    if not active_program:
        del keys["active_program"]
    return Registration(
        "home_connect_alt",
        (
            HaDeviceShape(
                {
                    "identifiers": {("home_connect_alt", safe_ha_id)},
                    "manufacturer": "Bosch",
                    "model": "WAT28400",
                    "name": name,
                },
                {
                    key: EntityShape(
                        platform,
                        f"{safe_ha_id}_{key.lower().replace('.', '_')}",
                        state=state,
                        object_id=f"{name} {suffix}",
                    )
                    for key, (platform, suffix, state) in keys.items()
                },
            ),
        ),
        account=True,
    )


# HA core `lg_thinq`'s sensors by its device type, as `<location>_<key>` where the
# property has a location, and `<key>` where it hasn't. As Home Assistant 2026.5 has
# them, and thinqconnect 1.0.12's device profiles.
LG_THINQ_SENSORS = {
    "DEVICE_WASHER": ("main_current_state", "main_cycle_count", "main_remain"),
    "DEVICE_WASHCOMBO_MAIN": ("current_state", "cycle_count", "remain"),
    "DEVICE_WASHCOMBO_MINI": ("current_state", "cycle_count", "remain"),
    "DEVICE_WASHTOWER_WASHER": ("main_current_state", "main_remain"),
    "DEVICE_DRYER": ("current_state", "cycle_count", "remain"),
    "DEVICE_WASHTOWER_DRYER": ("current_state", "remain"),
    "DEVICE_DISH_WASHER": (
        "current_state",
        "current_dish_washing_course",
        "rinse_level",
        "softening_level",
        "remain",
    ),
    "DEVICE_OVEN": ("oven_current_state", "oven_target_temperature"),
    "DEVICE_MICROWAVE_OVEN": ("current_state",),
    "DEVICE_STYLER": ("current_state", "remain"),
    "DEVICE_AIR_CONDITIONER": ("pm1", "pm2", "humidity"),
    "DEVICE_REFRIGERATOR": ("fridge_water_filter_info_used_time",),
    # Two Status sensors on one HA device, the second half first: a TWINWash's mini
    # washer, a double oven's lower cavity.
    "TWINWASH": (
        "mini_current_state",
        "mini_remain",
        "main_current_state",
        "main_remain",
    ),
    "DOUBLE_OVEN": (
        "lower_current_state",
        "upper_current_state",
        "upper_target_temperature",
        "lower_target_temperature",
    ),
}
LG_THINQ_DEVICE_TYPES = {"TWINWASH": "DEVICE_WASHER", "DOUBLE_OVEN": "DEVICE_OVEN"}
# Its energy sensors (`ENERGY_USAGE_SENSORS`), which count per day and month, with a
# state each.
LG_THINQ_ENERGY_USAGE = {"yesterday": "0.8", "this_month": "12.3", "last_month": "14.1"}
# A state by the property, whatever its location.
LG_THINQ_STATES = {
    "current_state": "power_off",
    "cycle_count": "42",
    "remain": NO_TIME,
    "current_dish_washing_course": "auto",
    "rinse_level": "level_2",
    "softening_level": "level_2",
    "target_temperature": "0",
    "pm1": "4",
    "pm2": "6",
    "humidity": "45",
    "water_filter_info_used_time": "120",
}


def _lg_thinq_state(key: str) -> str:
    return next(state for name, state in LG_THINQ_STATES.items() if key.endswith(name))


def lg_thinq(
    appliance: str = "DEVICE_WASHER",
    *,
    name: str = "Washer",
    device_id: str = "MW2-0B530EFD-1ADF-4F54-A2C3-46C37F94C689",
    sub_id: str | None = None,
) -> Registration:
    """HA core `lg_thinq`: every appliance of an account on one config entry, unique
    ids `<device id>_<property>`; a second appliance needs its own `device_id`.

    `appliance` is a ThinQ device type, written into the HA device's model, or one of
    the combined units above. `sub_id` is one half of a `DEVICE_WASHTOWER`, which the
    integration registers as an HA device of its own: `washer` or `dryer`.
    """
    unique_id = f"{device_id}_{sub_id}" if sub_id else device_id
    sensors = (
        (f"{sub_id}_current_state", f"{sub_id}_remain")
        if sub_id
        else LG_THINQ_SENSORS[appliance]
    )
    entities = {
        key: EntityShape("sensor", f"{unique_id}_{key}", state=_lg_thinq_state(key))
        for key in sensors
    } | {
        f"energy_{key}": EntityShape(
            "sensor", f"{unique_id}_energyUsage_{key}", state=state, unit="kWh"
        )
        for key, state in LG_THINQ_ENERGY_USAGE.items()
    }
    model = LG_THINQ_DEVICE_TYPES.get(appliance, appliance)
    return Registration(
        "lg_thinq",
        (
            HaDeviceShape(
                {
                    "identifiers": {("lg_thinq", unique_id)},
                    "manufacturer": "LGE",
                    "model": f"F4V5RYP0W ({model})",
                    "name": f"{name} {sub_id}" if sub_id else name,
                },
                entities,
            ),
        ),
        account=True,
    )


SMARTTHINGS_ENERGY_METERS = {
    "energy": "powerConsumptionReport_powerConsumption_energy_meter",
    "energy_difference": "powerConsumptionReport_powerConsumption_deltaEnergy_meter",
    "energy_saved": "powerConsumptionReport_powerConsumption_energySaved_meter",
    "power_energy": "powerConsumptionReport_powerConsumption_powerEnergy_meter",
}
SMARTTHINGS_POWER_METER = {
    "power": "powerConsumptionReport_powerConsumption_power_meter"
}


def _operating_state(
    capability: str, job_state: str, *, progress: bool = False
) -> dict[str, str]:
    """A machine's operating state sensors; with `progress` its Samsung CE one's
    progress too."""
    return {
        "machine_state": f"{capability}_machineState_machineState",
        "job_state": f"{capability}_{job_state}_{job_state}",
        "completion_time": f"{capability}_completionTime_completionTime",
    } | ({"progress": f"samsungce.{capability}_progress_progress"} if progress else {})


# By kind: the sensors of its `main` component, by entity key.
SMARTTHINGS_APPLIANCES = {
    "washer": _operating_state("washerOperatingState", "washerJobState", progress=True),
    "dryer": _operating_state("dryerOperatingState", "dryerJobState", progress=True),
    "dishwasher": _operating_state("dishwasherOperatingState", "dishwasherJobState"),
    "oven": _operating_state("ovenOperatingState", "ovenJobState")
    | {
        "oven_mode": "ovenMode_ovenMode_ovenMode",
        "setpoint": "ovenSetpoint_ovenSetpoint_ovenSetpoint",
        "temperature": "temperatureMeasurement_temperature_temperature",
    },
    # An AirDresser: a steam closet with a dryer's operating state.
    "steam_closet": _operating_state("dryerOperatingState", "dryerJobState"),
    "refrigerator": {
        "water_filter_usage": "custom.waterFilter_waterFilterUsage_waterFilterUsage",
    },
    "tv": {},
}
# Other components' sensors: a washer's upper washer, an oven's second cavity.
SMARTTHINGS_COMPONENTS = {
    "sub": ("upper_washer", "washerOperatingState"),
    "cavity-01": ("second_cavity", "ovenOperatingState"),
}
SMARTTHINGS_STEAM_CLOSET_ENTITIES = {
    "keep_fresh_mode_active": (
        "binary_sensor",
        "samsungce.steamClosetKeepFreshMode_operatingState_operatingState",
    ),
    "auto_cycle_link": (
        "switch",
        "samsungce.steamClosetAutoCycleLink_steamClosetAutoCycleLink_steamClosetAutoCycleLink",
    ),
    "sanitize": ("switch", "samsungce.steamClosetSanitizeMode_status_status"),
}
# A state by entity key: a machine that stopped after its last cycle.
SMARTTHINGS_STATES = {
    "machine_state": "stop",
    "job_state": "none",
    "completion_time": TIME,
    "progress": "100",
    "oven_mode": "bake",
    "setpoint": "0",
    "temperature": "21",
    "water_filter_usage": "12",
    "energy": "1234.5",
    "energy_difference": "0",
    "energy_saved": "0",
    "power_energy": "0",
    "power": "0",
}


def smartthings(
    kind: str = "washer",
    *,
    name: str = "Washer",
    device_id: str = "f984b91d-f250-9d42-3436-33f09a422a47",
    energy: bool = True,
    component: str | None = None,
    disabled: tuple[str, ...] = (),
) -> Registration:
    """HA core `smartthings`: every device of an account on one config entry, unique
    ids `<device id>_<component>_<capability>_<attribute>_<key>`, as of Home Assistant
    2026.5 and its test snapshots.

    `energy` is whether the device reports energy in its power consumption report,
    which is when the integration registers the energy meters. `component` adds
    that component's machine state sensor (`sub`, `cavity-01`); `disabled` are keys
    of entities the user disabled. A second device needs its own `device_id`.
    """
    object_id = slugify(name)
    sensors = SMARTTHINGS_APPLIANCES[kind] | (
        SMARTTHINGS_ENERGY_METERS | SMARTTHINGS_POWER_METER if energy else {}
    )
    entities = {
        key: EntityShape(
            "sensor",
            f"{device_id}_main_{unique_id}",
            state=SMARTTHINGS_STATES[key],
            unit="kWh"
            if key in SMARTTHINGS_ENERGY_METERS
            else "W"
            if key in SMARTTHINGS_POWER_METER
            else None,
            object_id=f"{object_id}_{key}",
            disabled=key in disabled,
        )
        for key, unique_id in sensors.items()
    }
    if component is not None:
        suffix, capability = SMARTTHINGS_COMPONENTS[component]
        # Registered first, so that only its component tells it from the main one.
        entities = {
            f"{suffix}_machine_state": EntityShape(
                "sensor",
                f"{device_id}_{component}_{capability}_machineState_machineState",
                state="stop",
                object_id=f"{object_id}_{suffix}_machine_state",
            )
        } | entities
    if kind == "steam_closet":
        entities |= {
            key: EntityShape(
                platform,
                f"{device_id}_main_{unique_id}",
                state="off",
                object_id=f"{object_id}_{key}",
            )
            for key, (platform, unique_id) in SMARTTHINGS_STEAM_CLOSET_ENTITIES.items()
        }
    return Registration(
        "smartthings",
        (
            HaDeviceShape(
                {
                    "identifiers": {("smartthings", device_id)},
                    "manufacturer": "Samsung Electronics",
                    "name": name,
                },
                entities,
            ),
        ),
        account=True,
    )
