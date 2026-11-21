"""Integration Profiles of EV charger integrations.

Each pre-fills the charger's own energy counter as the electricity source, which
Detect again leaves alone like every meter.
"""

from typing import Any

from custom_components.coinop.const import DEVICE_TYPE_EV_CHARGER
from custom_components.coinop.device_config import ConsumptionSource

from .base import Find, always, found, mapping

DEVICE_TYPES = (DEVICE_TYPE_EV_CHARGER,)
KIND = always(DEVICE_TYPE_EV_CHARGER)


def energy_meter(
    find: Find,
    *,
    lifetime: str | None,
    session: str | None,
    session_first: bool = False,
) -> dict[str, Any]:
    """The electricity source: the first of the charger's energy counters that is
    registered and enabled, the lifetime one before the session one.

    A lifetime counter avoids the meter reset Flag a session counter gets when it only
    drops once the next session charges. `session_first` is for an integration whose
    lifetime counter can't be trusted for a Run (one that lags or may never report).
    """
    counters = (session, lifetime) if session_first else (lifetime, session)
    meter = find("sensor", *(counter for counter in counters if counter))
    return found(
        meter, source=ConsumptionSource.ENERGY.value, entity_id=meter, attribute=None
    )


def tesla_wall_connector(find: Find) -> dict[str, Any]:
    """HA core `tesla_wall_connector`: unique ids `<serial>-<key>`.

    Its states are `EVSE_STATE` in its sensor.py; codes it doesn't know are `unknown`.
    """
    status = find("sensor", "-status")
    return {
        "status": found(status, entity_id=status, attribute=None),
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
