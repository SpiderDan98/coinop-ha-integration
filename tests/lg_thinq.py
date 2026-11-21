"""Registry entries shaped like HA core `lg_thinq` registers an LG appliance.

Unique ids, models and identifiers follow its entity.py, coordinator.py and sensor.py
as Home Assistant 2026.5 has them, and thinqconnect 1.0.12's device profiles.
"""

from homeassistant.core import HomeAssistant

from .registry import HaDevice, add_ha_device, entity

# The sensors the integration registers by its device type, as `<location>_<key>`
# where the property has a location, and `<key>` where it hasn't.
LG_THINQ_SENSORS = {
    "DEVICE_WASHER": ("main_current_state", "main_cycle_count", "main_remain_time"),
    "DEVICE_WASHCOMBO_MAIN": ("current_state", "cycle_count", "remain_time"),
    "DEVICE_WASHCOMBO_MINI": ("current_state", "cycle_count", "remain_time"),
    "DEVICE_WASHTOWER_WASHER": ("main_current_state", "main_remain_time"),
    "DEVICE_DRYER": ("current_state", "cycle_count", "remain_time"),
    "DEVICE_WASHTOWER_DRYER": ("current_state", "remain_time"),
    "DEVICE_DISH_WASHER": (
        "current_state",
        "current_dish_washing_course",
        "rinse_level",
        "softening_level",
        "remain_time",
    ),
    "DEVICE_OVEN": ("oven_current_state", "oven_target_temperature"),
    "DEVICE_MICROWAVE_OVEN": ("current_state",),
    "DEVICE_STYLER": ("current_state", "remain_time"),
    "DEVICE_AIR_CONDITIONER": ("pm1", "pm2", "humidity"),
    "DEVICE_REFRIGERATOR": ("fridge_water_filter_info_used_time",),
    # Two Status sensors on one HA device, the second half first: a TWINWash's mini
    # washer, a double oven's lower cavity.
    "TWINWASH": ("mini_current_state", "main_current_state", "main_remain_time"),
    "DOUBLE_OVEN": (
        "lower_current_state",
        "upper_current_state",
        "upper_target_temperature",
        "lower_target_temperature",
    ),
}
DEVICE_TYPES = {"TWINWASH": "DEVICE_WASHER", "DOUBLE_OVEN": "DEVICE_OVEN"}
# Its energy sensors (`ENERGY_USAGE_SENSORS`), which count per day and month.
ENERGY_USAGE = ("yesterday", "this_month", "last_month")


def add_lg_thinq(
    hass: HomeAssistant,
    appliance: str = "DEVICE_WASHER",
    *,
    name: str = "Washer",
    device_id: str = "MW2-0B530EFD-1ADF-4F54-A2C3-46C37F94C689",
    sub_id: str | None = None,
) -> HaDevice:
    """HA core `lg_thinq`: every appliance of an account on one config entry, unique
    ids `<device id>_<property>`; a second appliance needs its own `device_id`.

    `appliance` is a ThinQ device type, written into the HA device's model, or one of
    the combined units above. `sub_id` is one half of a `DEVICE_WASHTOWER`, which the
    integration registers as an HA device of its own: `washer` or `dryer`.
    """
    unique_id = f"{device_id}_{sub_id}" if sub_id else device_id
    sensors = (
        (f"{sub_id}_current_state", f"{sub_id}_remain_time")
        if sub_id
        else LG_THINQ_SENSORS[appliance]
    )
    entities = {key: entity("sensor", f"{unique_id}_{key}") for key in sensors} | {
        f"energy_{key}": entity("sensor", f"{unique_id}_energyUsage_{key}", unit="kWh")
        for key in ENERGY_USAGE
    }
    config_entry = next(iter(hass.config_entries.async_entries("lg_thinq")), "lg_thinq")
    return add_ha_device(
        hass,
        config_entry,
        entities,
        identifiers={("lg_thinq", unique_id)},
        manufacturer="LGE",
        model=f"F4V5RYP0W ({DEVICE_TYPES.get(appliance, appliance)})",
        name=f"{name} {sub_id}" if sub_id else name,
    )
