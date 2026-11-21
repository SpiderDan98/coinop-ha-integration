"""Registry entries shaped like WashData, Miele and Home Connect register an
appliance.

Unique ids, units, options and what tells the appliance's kind follow each
integration's source.
"""

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry


@dataclass
class Washer:
    device: dr.DeviceEntry
    # Entity ids by the integration's entity key.
    entities: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def _washer(
    hass: HomeAssistant, domain: str, identifier: str, name: str
) -> tuple[MockConfigEntry, Washer]:
    config_entry = MockConfigEntry(domain=domain)
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(domain, identifier)},
        name=name,
    )
    return config_entry, Washer(device)


def _add(
    hass: HomeAssistant,
    washer: Washer,
    config_entry: ConfigEntry,
    platform: str,
    key: str,
    unique_id: str,
    object_id: str,
    **kwargs: Any,
) -> None:
    washer.entities[key] = (
        er.async_get(hass)
        .async_get_or_create(
            platform,
            config_entry.domain,
            unique_id,
            config_entry=config_entry,
            device_id=washer.device.id,
            suggested_object_id=object_id,
            **kwargs,
        )
        .entity_id
    )


def add_washdata(
    hass: HomeAssistant,
    device_type: str | None = "washing_machine",
    *,
    name: str = "Washer",
    changed_to: str | None = None,
) -> Washer:
    """3dg1luk43/ha_washdata: one HA device per config entry, named after it, unique
    ids `<entry id>_<key>`.

    `device_type` is the kind picked when the entry was created, which WashData keeps
    in the entry's data (None: an entry without one, which WashData reads as a washing
    machine). `changed_to` is a kind picked later: it goes to the options, and the
    data keeps the old one.
    """
    settings = {"power_sensor": "sensor.plug_power", "min_power": 2.0}
    kind = {} if device_type is None else {"device_type": device_type}
    config_entry = MockConfigEntry(
        domain="ha_washdata",
        title=name,
        version=3,
        minor_version=13,
        data={"name": name} | kind | settings,
        options={"device_type": changed_to} | settings if changed_to else {},
    )
    config_entry.add_to_hass(hass)
    washer = Washer(
        dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={("ha_washdata", config_entry.entry_id)},
            manufacturer="WashData",
            name=name,
        )
    )

    def add(key: str, **kwargs: Any) -> None:
        _add(
            hass,
            washer,
            config_entry,
            "sensor",
            key,
            f"{config_entry.entry_id}_{key}",
            key,
            translation_key=key,
            **kwargs,
        )

    add("washer_state")
    add("washer_program")
    add("current_power", unit_of_measurement="W")
    add("energy_total", unit_of_measurement="kWh")
    add("last_cycle_energy", unit_of_measurement="kWh")
    add("last_cycle_cost")
    return washer


# HA core `miele`'s sensors by key: object id, translation key and unit.
MIELE_SENSORS = {
    "state_status": ("status", "status", None),
    "state_program_id": ("program", "program_id", None),
    "state_program_phase": ("program_phase", "program_phase", None),
    "current_energy_consumption": ("energy_consumption", "energy_consumption", "kWh"),
    "current_water_consumption": ("water_consumption", "water_consumption", "L"),
}
_STATUS = ("state_status",)
_PROGRAM = (*_STATUS, "state_program_id", "state_program_phase")
_ENERGY = (*_PROGRAM, "current_energy_consumption")
_WATER = (*_ENERGY, "current_water_consumption")
# The sensors it registers for an appliance, by the model it gives the HA device: the
# appliance type's tag (`DEVICE_TYPE_TAGS` in its const.py), capitalised, and the
# `types` of each sensor description in its sensor.py.
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


def add_miele(
    hass: HomeAssistant,
    model: str = "Washing machine",
    *,
    serial: str = "000123456789",
) -> Washer:
    """HA core `miele`: every appliance of an account on one config entry, named
    after its kind, unique ids `<serial>-<key>`.

    `model` is the appliance's kind as the integration writes it on the HA device; it
    also decides which sensors the integration registers. A second appliance needs
    its own `serial`.
    """
    config_entry = next(iter(hass.config_entries.async_entries("miele")), None)
    if config_entry is None:
        config_entry = MockConfigEntry(domain="miele")
        config_entry.add_to_hass(hass)
    washer = Washer(
        dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={("miele", serial)},
            manufacturer="Miele",
            name=model,
            model=model,
            serial_number=serial,
        )
    )
    for key in MIELE_MODELS[model]:
        object_id, translation_key, unit = MIELE_SENSORS[key]
        _add(
            hass,
            washer,
            config_entry,
            "sensor",
            key,
            f"{serial}-{key}",
            f"{slugify(model)}_{object_id}",
            translation_key=translation_key,
            unit_of_measurement=unit,
        )
    return washer


# The API's appliance types HA core `home_connect` fetches programs for
# (`APPLIANCES_WITH_PROGRAMS` in its const.py).
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
# What it registers for an appliance type alone, whatever the appliance reports
# (`EVENT_SENSORS` and `BSH_PROGRAM_SENSORS` in its sensor.py): by BSH key, the
# translation key and the types. A coffee maker has 17 more event sensors.
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
# The event sensors Home Assistant 2026.5, Coin-op's minimum, registers for fewer
# types: it knows no `Hob` and lacks the favorite buttons and most dishwasher events.
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


def add_home_connect(
    hass: HomeAssistant,
    appliance_type: str = "Washer",
    *,
    name: str = "Washer",
    minimum_ha: bool = False,
) -> Washer:
    """HA core `home_connect`: unique ids `<haId>-<BSH key>`.

    `appliance_type` is the API's type of the appliance, which is on no registry
    entry. It only decides what the integration registers: the event sensors of the
    type, disabled by default, and the program sensors, both even for an appliance
    that reports nothing, here as the locked Home Assistant does or, with
    `minimum_ha`, as Coin-op's minimum does. The operation state comes from what the
    appliance reports; every stand-in has one, so that it is its kind that decides
    whether Quick Start offers it. Each call is a config entry and device of its own.
    """
    object_id = slugify(name)
    ha_id = f"SIEMENS-{object_id.upper()}-0123"
    config_entry, washer = _washer(hass, "home_connect", ha_id, name)

    def add(platform: str, key: str, translation_key: str, **kwargs: Any) -> None:
        _add(
            hass,
            washer,
            config_entry,
            platform,
            key,
            f"{ha_id}-{key}",
            f"{object_id}_{translation_key}",
            translation_key=translation_key,
            **kwargs,
        )

    for key, (translation_key, types) in HOME_CONNECT_EVENT_SENSORS.items():
        if appliance_type in (
            HOME_CONNECT_MINIMUM_HA.get(key, types) if minimum_ha else types
        ):
            add(
                "sensor",
                key,
                translation_key,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )
    for key, (translation_key, types) in HOME_CONNECT_PROGRAM_SENSORS.items():
        if appliance_type in types:
            add("sensor", key, translation_key)
    add("sensor", "BSH.Common.Status.OperationState", "operation_state")
    if appliance_type in HOME_CONNECT_WITH_PROGRAMS:
        add("sensor", "BSH.Common.Status.DoorState", "door")
        add("select", "BSH.Common.Root.SelectedProgram", "selected_program")
        add("select", "BSH.Common.Root.ActiveProgram", "active_program")
    return washer
