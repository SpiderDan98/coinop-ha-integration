"""Registry entries shaped like HA core `smartthings` registers a Samsung device.

Unique ids, components and which entities each appliance has follow the
integration's source and its test snapshots as of Home Assistant 2026.5.
"""

from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .registry import HaDevice, add_ha_device, entity

ENERGY_METERS = {
    "energy": "powerConsumptionReport_powerConsumption_energy_meter",
    "energy_difference": "powerConsumptionReport_powerConsumption_deltaEnergy_meter",
    "energy_saved": "powerConsumptionReport_powerConsumption_energySaved_meter",
    "power_energy": "powerConsumptionReport_powerConsumption_powerEnergy_meter",
}
POWER_METER = {"power": "powerConsumptionReport_powerConsumption_power_meter"}


def _operating_state(capability: str, job_state: str) -> dict[str, str]:
    return {
        "machine_state": f"{capability}_machineState_machineState",
        "job_state": f"{capability}_{job_state}_{job_state}",
        "completion_time": f"{capability}_completionTime_completionTime",
    }


# By kind: the sensors of its `main` component, by entity key.
SMARTTHINGS_APPLIANCES = {
    "washer": _operating_state("washerOperatingState", "washerJobState"),
    "dryer": _operating_state("dryerOperatingState", "dryerJobState"),
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
STEAM_CLOSET_ENTITIES = {
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


def add_smartthings(
    hass: HomeAssistant,
    kind: str = "washer",
    *,
    name: str = "Washer",
    device_id: str = "f984b91d-f250-9d42-3436-33f09a422a47",
    energy: bool = True,
    component: str | None = None,
    disabled: tuple[str, ...] = (),
) -> HaDevice:
    """HA core `smartthings`: every device of an account on one config entry, unique
    ids `<device id>_<component>_<capability>_<attribute>_<key>`.

    `energy` is whether the device reports energy in its power consumption report,
    which is when the integration registers the energy meters. `component` adds
    that component's machine state sensor (`sub`, `cavity-01`); `disabled` are keys
    of entities the user disabled. A second device needs its own `device_id`.
    """
    config_entry = next(
        iter(hass.config_entries.async_entries("smartthings")), "smartthings"
    )
    object_id = slugify(name)
    sensors = SMARTTHINGS_APPLIANCES[kind] | (
        ENERGY_METERS | POWER_METER if energy else {}
    )
    entities = {
        key: entity(
            "sensor",
            f"{device_id}_main_{unique_id}",
            unit="kWh" if key in ENERGY_METERS else "W" if key in POWER_METER else None,
            object_id=f"{object_id}_{key}",
            disabled=key in disabled,
        )
        for key, unique_id in sensors.items()
    }
    if component is not None:
        suffix, capability = SMARTTHINGS_COMPONENTS[component]
        # Registered first, so that only its component tells it from the main one.
        entities = {
            f"{suffix}_machine_state": entity(
                "sensor",
                f"{device_id}_{component}_{capability}_machineState_machineState",
                object_id=f"{object_id}_{suffix}_machine_state",
            )
        } | entities
    if kind == "steam_closet":
        entities |= {
            key: entity(
                platform,
                f"{device_id}_main_{unique_id}",
                object_id=f"{object_id}_{key}",
            )
            for key, (platform, unique_id) in STEAM_CLOSET_ENTITIES.items()
        }
    return add_ha_device(
        hass,
        config_entry,
        entities,
        identifiers={("smartthings", device_id)},
        manufacturer="Samsung Electronics",
        name=name,
    )
