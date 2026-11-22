"""The subentry data of each Device with history, as Add Device writes it."""

from typing import Any

from custom_components.coinop.device_config import stored_capabilities

from .data import PRINTERS


def printer(key: str) -> dict[str, Any]:
    """The printer's subentry data, as Add Device writes it."""
    return {
        "device_type": "3d_printer",
        "printer_device_id": None,
        "status": {"entity_id": f"input_select.{key}_status", "attribute": None},
        "mapping": {
            "running": ["printing"],
            "paused": ["paused"],
            "finished": ["finished"],
            "cancelled": ["cancelled"],
            "ended": [],
            "fault": ["error"],
            "ignored": ["idle"],
        },
        "job": {
            "entity_id": f"input_text.{key}_job",
            "attribute": None,
            "material": None,
            "slots": [],
            "colour_attribute": None,
            "loaded_slot": None,
        },
        "images": {"thumbnail": None, "camera": None, "snapshot": False},
        "progress": {
            "remaining_time": f"input_number.{key}_time_left",
            "progress": f"input_number.{key}_progress",
            "expected_energy": None,
        },
        "consumption": {
            "source": "estimate",
            "running_power": PRINTERS[key],
            "paused_power": 15.0,
        },
        "price": {"source": "fixed", "value": 0.32},
    }


def appliance(
    device_type: str, key: str, *, metered: bool = True, water: str | None = "meter"
) -> dict[str, Any]:
    """An appliance's subentry data on the helpers named `key`: an energy meter
    unless `metered` is false (then electricity per Program), and water from a
    meter, per Program or, with None, none, as its Device Type has no water."""
    data: dict[str, Any] = {
        "device_type": device_type,
        "printer_device_id": None,
        "status": {"entity_id": f"input_select.{key}_status", "attribute": None},
        "mapping": {
            "running": ["running"],
            "paused": ["paused"],
            "finished": ["finished"],
            "cancelled": ["cancelled"],
            "ended": [],
            "fault": [],
            "ignored": ["off"],
        },
        "program": {"entity_id": f"input_select.{key}_program", "attribute": None},
        "consumption": {
            "source": "energy",
            "entity_id": f"input_number.{key}_energy",
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        }
        if metered
        else {"source": "per_program"},
        "price": {"source": "fixed", "value": 0.32},
    }
    if water == "meter":
        data["water"] = {
            "source": "meter",
            "entity_id": f"input_number.{key}_water",
            "attribute": None,
            "unit": "L",
            "factor": None,
        }
    elif water:
        data["water"] = {"source": water}
    if water:
        # Per m³, wastewater included.
        data["water_price"] = {"source": "fixed", "value": 4.2}
    return data


def charger() -> dict[str, Any]:
    """A charger on its session energy sensor, which counts each session from 0;
    a car left plugged in once full is Paused."""
    return {
        "device_type": "ev_charger",
        "printer_device_id": None,
        "status": {
            "entity_id": "input_select.carport_charger_status",
            "attribute": None,
        },
        "mapping": {
            "running": ["charging"],
            "paused": ["connected"],
            "finished": ["disconnected"],
            "cancelled": [],
            "ended": [],
            "fault": ["error"],
            "ignored": [],
        },
        "consumption": {
            "source": "energy",
            "entity_id": "input_number.carport_charger_session",
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.32},
    }


def mower() -> dict[str, Any]:
    """A mower on its charging station's plug: charging after mowing is Paused."""
    return {
        "device_type": "robotic_mower",
        "printer_device_id": None,
        "status": {
            "entity_id": "input_select.robotic_mower_status",
            "attribute": None,
        },
        "mapping": {
            "running": ["mowing", "returning"],
            "paused": ["charging"],
            "finished": ["parked"],
            "cancelled": [],
            "ended": [],
            "fault": ["error"],
            "ignored": [],
        },
        "consumption": {
            "source": "energy",
            "entity_id": "input_number.robotic_mower_station_energy",
            "attribute": None,
            "unit": "kWh",
            "factor": None,
        },
        "price": {"source": "fixed", "value": 0.32},
    }


def garden_valve() -> dict[str, Any]:
    """A battery-driven valve: an Other Device that has water and no electricity."""
    return {
        "device_type": "other",
        "type_name": "Irrigation",
        "capabilities": stored_capabilities(["water"]),
        "printer_device_id": None,
        "status": {"entity_id": "input_select.irrigation_status", "attribute": None},
        "mapping": {
            "running": ["watering"],
            "paused": [],
            "finished": ["off"],
            "cancelled": [],
            "ended": [],
            "fault": [],
            "ignored": [],
        },
        "consumption": {"source": "none"},
        "water": {
            "source": "meter",
            "entity_id": "input_number.irrigation_water",
            "attribute": None,
            "unit": "L",
            "factor": None,
        },
        # Per m³; garden water is billed without wastewater.
        "water_price": {"source": "fixed", "value": 2.1},
    }
