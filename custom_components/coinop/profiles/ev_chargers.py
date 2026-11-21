"""Integration Profiles of EV charger integrations.

Each pre-fills the charger's own energy counter as the electricity source, which
Detect again leaves alone like every meter.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from custom_components.coinop.const import DEVICE_TYPE_EV_CHARGER

from .base import (
    Find,
    NoDeviceType,
    always,
    energy_source,
    entity_input,
    found,
    mapping,
)

DEVICE_TYPES = (DEVICE_TYPE_EV_CHARGER,)
KIND = always(DEVICE_TYPE_EV_CHARGER)


def energy_meter(
    find: Find,
    *,
    lifetime: str | None,
    session: str | None,
    session_first: bool = False,
    start: bool = False,
) -> dict[str, Any]:
    """The electricity source: the first of the charger's energy counters that is
    registered and enabled, the lifetime one before the session one.

    A lifetime counter avoids the meter reset Flag a session counter gets when it only
    drops once the next session charges. `session_first` is for an integration whose
    lifetime counter can't be trusted for a Run (one that lags or may never report);
    `start` for one whose unique ids start with the key.
    """
    counters = (session, lifetime) if session_first else (lifetime, session)
    meter = find("sensor", *(counter for counter in counters if counter), start=start)
    return energy_source(meter)


def tesla_wall_connector(find: Find) -> dict[str, Any]:
    """HA core `tesla_wall_connector`: unique ids `<serial>-<key>`.

    Its states are `EVSE_STATE` in its sensor.py; codes it doesn't know are `unknown`.
    """
    status = find("sensor", "-status")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["charging", "charging_reduced"],
                paused=[
                    "connected",
                    "ready",
                    "negotiating",
                    "waiting_car",
                    "charging_finished",
                ],
                finished=["not_connected"],
                fault=["error"],
                ignored=["booting"],
            ),
        ),
        "consumption": energy_meter(
            find, lifetime="-energy_kWh", session="-session_energy_wh"
        ),
    }


def evcc(find: Find) -> dict[str, Any]:
    """HACS `evcc_intg`: unique ids `evcc_intg.<system id>_<loadpoint>_<key>`, from the
    slugified titles of the config entry and the loadpoint.

    Its Status is a binary sensor without "plugged in, not charging", so a session
    that evcc interrupts is several Runs. `charge_total_import` is registered and
    enabled even for a charger without a meter, which never reports it, so the session
    counter comes first.
    """
    status = find("binary_sensor", "_charging")
    return {
        "status": entity_input(status),
        "mapping": found(status, **mapping(running=["on"], finished=["off"])),
        "consumption": energy_meter(
            find,
            lifetime="_charge_total_import",
            session="_charged_energy",
            session_first=True,
        ),
    }


def ocpp(find: Find) -> dict[str, Any]:
    """HACS `ocpp`: unique ids `ocpp.<cpid>[.conn<n>].<metric>.sensor`.

    Its states are OCPP 1.6's connector statuses, which it also reports for OCPP 2.0.1.
    """
    status = find("sensor", ".status_connector.sensor")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["Charging"],
                paused=["Preparing", "SuspendedEV", "SuspendedEVSE", "Finishing"],
                finished=["Available"],
                fault=["Faulted"],
                ignored=["Unavailable", "Reserved"],
            ),
        ),
        "consumption": energy_meter(
            find,
            lifetime=".energy_active_import_register.sensor",
            session=".energy_session.sensor",
        ),
    }


def easee(find: Find) -> dict[str, Any]:
    """HACS `easee`: unique ids `<charger id>_<key>`.

    Its states are `EASEE_STATUS` in its const.py; codes it doesn't know are
    `unknown <code>`.
    """
    status = find("sensor", "_status")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["charging"],
                paused=[
                    "awaiting_start",
                    "completed",
                    "ready_to_charge",
                    "awaiting_authorization",
                    "de_authorizing",
                    # Transitions with the car plugged in: the Run starts at `charging`.
                    "start_charging",
                    "stop_charging",
                    "awaiting_load_balancing",
                    "awaiting_smart_start",
                    "awaiting_scheduled_start",
                    "authenticating",
                    "paused_due_to_equalizer",
                ],
                finished=["disconnected"],
                fault=[
                    "error",
                    "erratic_ev",
                    "error_temperature_too_high",
                    "error_dead_powerboard",
                    "error_overcurrent",
                    "error_pen_fault",
                ],
                # They say nothing about the car.
                ignored=["offline", "searching_for_master"],
            ),
        ),
        "consumption": energy_meter(
            find, lifetime="_lifetime_energy", session="_session_energy"
        ),
    }


def zaptec(find: Find) -> dict[str, Any]:
    """HACS `zaptec`: unique ids `<charger id>_<key>`.

    Its states are the API's `ChargerOperationModes` in lower case; it has no fault
    state. The signed meter value, registered only for a charger that reports it, is
    published about hourly, so it comes after the session counter.
    """
    status = find("sensor", "_charger_operation_mode")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["connected_charging"],
                paused=["connected_requesting", "connected_finished"],
                finished=["disconnected"],
                ignored=["unknown"],
            ),
        ),
        "consumption": energy_meter(
            find,
            lifetime="_signed_meter_value_kwh",
            session="_total_charge_power_session",
            session_first=True,
        ),
    }


def goe_mqtt(find: Find) -> dict[str, Any]:
    """HACS `goecharger_mqtt`: unique ids `<serial>-<platform>-<key>-<attribute or 0>`.

    Its car states are `_CODE_STATES["car"]` in its definitions/sensor.py.
    """
    status = find("sensor", "-sensor-car-car")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["charging"],
                paused=["wait_for_car", "complete"],
                finished=["idle"],
                fault=["error", "unknown_error"],
            ),
        ),
        "consumption": energy_meter(
            find, lifetime="-sensor-eto-0", session="-sensor-wh-0"
        ),
    }


def goe_api2(find: Find) -> dict[str, Any]:
    """HACS `goecharger_api2`: unique ids `goecharger_api2.goe_<serial>_<key>`, or
    `goe_wan_<serial>` in cloud mode.

    Its car states are display texts from `TRANSLATIONS[...]["car"]` in its
    pygoecharger_ha/const.py, in German where HA's language is `de`, else English.
    """
    status = find("sensor", "_car_value")
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["Charging", "Laden"],
                paused=[
                    "Wait for car",
                    "Warte auf Fahrzeug",
                    "Complete",
                    "Abgeschlossen",
                ],
                finished=["Idle", "Inaktiv/Frei"],
                fault=["Error", "Fehler", "Unknown/Error", "Unbekannt/Fehler"],
            ),
        ),
        "consumption": energy_meter(find, lifetime="_eto", session="_wh"),
    }


def wallbox(find: Find) -> dict[str, Any]:
    """HA core `wallbox`: unique ids `<key>-<serial>`.

    Its states are `ChargerStatus` in its const.py, English texts that aren't
    translated. `Disconnected` is both the charger being offline and the car being
    unplugged, so it is ignored: ending the Run there would split a session at a cloud
    dropout, and an unplugged charger reports `Ready` next. Its energy counters are
    all the session's.
    """
    status = find("sensor", "status_description-", start=True)
    return {
        "status": entity_input(status),
        "mapping": found(
            status,
            **mapping(
                running=["Charging"],
                paused=[
                    "Discharging",
                    "Paused",
                    "Scheduled",
                    "Waiting for car demand",
                    "Waiting",
                    "Waiting in queue by Power Sharing",
                    "Waiting in queue by Power Boost",
                    "Waiting in queue by Eco-Smart",
                    "Waiting MID failed",
                    "Waiting MID safety margin exceeded",
                    "Locked, car connected",
                ],
                finished=["Ready", "Locked"],
                fault=["Error"],
                ignored=["Disconnected", "Updating", "Unknown"],
            ),
        ),
        "consumption": energy_meter(
            find, lifetime=None, session="added_energy-", start=True
        ),
    }


def zaptec_kind(
    find: Find, device: dr.DeviceEntry, config_entry: ConfigEntry
) -> str | NoDeviceType:
    """An installation finds its chargers' Status through them, but is none itself."""
    if device.model == "Zaptec Installation":
        return NoDeviceType.NOT_A_DEVICE
    return DEVICE_TYPE_EV_CHARGER
