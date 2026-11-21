"""How the EV charger integrations register a charger.

Each takes `disabled` (keys of entities registered disabled) and `missing` (keys of
entities not registered at all). Their states are those of a charger without a car.
"""

from . import EntityShape, HaDeviceShape, Registration

# HA core `tesla_wall_connector`'s entities by key: platform, object id, the unit HA
# shows (both energy counters are native Wh, suggested kWh) and a state.
WALL_CONNECTOR_ENTITIES = {
    "status": ("sensor", "status", None, "not_connected"),
    "energy_kWh": ("sensor", "energy", "kWh", "1234.5"),
    "session_energy_wh": ("sensor", "session_energy", "kWh", "0"),
    "evse_state": ("sensor", "state_code", None, "1"),
    "vehicle_connected": ("binary_sensor", "vehicle_connected", None, "off"),
    "contactor_closed": ("binary_sensor", "contactor_closed", None, "off"),
}


def wall_connector(
    *,
    disabled: tuple[str, ...] = ("evse_state",),
    missing: tuple[str, ...] = (),
    serial: str = "PGT21234567890",
) -> Registration:
    """HA core `tesla_wall_connector`: one HA device per Wall Connector, unique ids
    `<serial>-<key>`; the raw state code is disabled by default."""
    return Registration(
        "tesla_wall_connector",
        (
            HaDeviceShape(
                {
                    "identifiers": {("tesla_wall_connector", serial)},
                    "manufacturer": "Tesla",
                    "model": "Wall Connector",
                    "name": "Tesla Wall Connector",
                },
                {
                    key: EntityShape(
                        platform,
                        f"{serial}-{key}",
                        state=state,
                        unit=unit,
                        disabled=key in disabled,
                        object_id=f"Tesla Wall Connector {object_id}",
                    )
                    for key, (
                        platform,
                        object_id,
                        unit,
                        state,
                    ) in WALL_CONNECTOR_ENTITIES.items()
                    if key not in missing
                },
            ),
        ),
    )


# HACS `evcc_intg`'s entities of a loadpoint by key: platform, unit and a state.
EVCC_LOADPOINT_ENTITIES = {
    "charging": ("binary_sensor", None, "off"),
    "connected": ("binary_sensor", None, "off"),
    "charge_total_import": ("sensor", "kWh", "2345.6"),
    "charged_energy": ("sensor", "kWh", "0"),
    "session_energy": ("sensor", "kWh", "0"),
    "session_price": ("sensor", "EUR", "0"),
}


def evcc_site(
    loadpoints: tuple[str, ...] = ("garage",),
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    system_id: str = "evcc",
) -> Registration:
    """HACS `evcc_intg`: unique ids `evcc_intg.<system id>_<loadpoint>_<key>`, from the
    slugified titles of the config entry and the loadpoint.

    A vehicle is an HA device of its own, then comes the site's. With one loadpoint
    its entities are the site's; with several, each loadpoint has an HA device of its
    own after the site's, not linked to it.
    """

    def loadpoint(name: str) -> dict[str, EntityShape]:
        return {
            key: EntityShape(
                platform,
                f"evcc_intg.{system_id}_{name}_{key}",
                state=state,
                unit=unit,
                disabled=key in disabled,
                object_id=f"{system_id} {name} {key}",
            )
            for key, (platform, unit, state) in EVCC_LOADPOINT_ENTITIES.items()
            if key not in missing
        }

    vehicle = HaDeviceShape(
        {
            "identifiers": {("evcc_intg", "did_evcc_local_tesla")},
            "name": f"evcc - Vehicle Tesla [{system_id}]",
        },
        {
            "soc": EntityShape(
                "sensor", f"evcc_intg.{system_id}_tesla_soc", state="80", unit="%"
            )
        },
    )
    site = HaDeviceShape(
        {
            "identifiers": {("evcc_intg", "did_evcc_local")},
            "name": f"evcc ☀️🚘 Solar Charging [{system_id}]",
        },
        {
            "grid_power": EntityShape(
                "sensor", f"evcc_intg.{system_id}_grid_power", state="350", unit="W"
            )
        }
        | (loadpoint(*loadpoints) if len(loadpoints) == 1 else {}),
    )
    own = (
        ()
        if len(loadpoints) == 1
        else tuple(
            HaDeviceShape(
                {
                    "identifiers": {("evcc_intg", f"did_evcc_local_{name}")},
                    "name": f"evcc - Loadpoint {name.title()} [{system_id}]",
                },
                loadpoint(name),
            )
            for name in loadpoints
        )
    )
    return Registration("evcc_intg", (vehicle, site, *own), entry={"title": system_id})


# HACS `ocpp`'s metrics (dots as underscores, lower case), their units and a state.
OCPP_CONNECTOR_METRICS = {
    "status_connector": (None, "Available"),
    "energy_active_import_register": ("kWh", "3456.7"),
    "energy_session": ("kWh", "0"),
    "energy_meter_start": ("kWh", "3456.7"),
}
OCPP_CHARGER_METRICS = {
    "status": (None, "Available"),
    "heartbeat": (None, "2026-05-01T09:30:00+00:00"),
}


def charge_point(
    *,
    connectors: int = 1,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    cpid: str = "charger",
) -> Registration:
    """HACS `ocpp`: unique ids `ocpp.<cpid>[.conn<n>].<metric>.sensor`.

    With one connector every sensor is the charger's HA device's, without `.conn<n>`;
    with several, each connector is an HA device linked to the charger's, after it,
    and holds its own sensors. `disabled` and `missing` apply to every connector.
    """

    def sensors(
        metrics: dict[str, tuple[str | None, str]], scope: str
    ) -> dict[str, EntityShape]:
        return {
            key: EntityShape(
                "sensor",
                f"ocpp.{scope}.{key}.sensor",
                state=state,
                unit=unit,
                disabled=key in disabled,
                object_id=f"{scope} {key}",
            )
            for key, (unit, state) in metrics.items()
            if key not in missing
        }

    flat = OCPP_CONNECTOR_METRICS if connectors == 1 else {}
    charger = HaDeviceShape(
        {"identifiers": {("ocpp", cpid)}, "name": cpid},
        sensors({**OCPP_CHARGER_METRICS, **flat}, cpid),
    )
    own = (
        ()
        if connectors == 1
        else tuple(
            HaDeviceShape(
                {
                    "identifiers": {("ocpp", f"{cpid}-conn{n}")},
                    "name": f"{cpid} Connector {n}",
                },
                sensors(OCPP_CONNECTOR_METRICS, f"{cpid}.conn{n}"),
                via=0,
            )
            for n in range(1, connectors + 1)
        )
    )
    return Registration("ocpp", (charger, *own), entry={"title": cpid})


def _charger(
    entities: dict[str, tuple[str, str, str | None, str]],
    *,
    disabled: tuple[str, ...],
    missing: tuple[str, ...],
    via: int | None = None,
    **fields: object,
) -> HaDeviceShape:
    """A charger's HA device with `entities` by key: platform, unique id, unit and
    state."""
    return HaDeviceShape(
        fields,
        {
            key: EntityShape(
                platform, unique_id, state=state, unit=unit, disabled=key in disabled
            )
            for key, (platform, unique_id, unit, state) in entities.items()
            if key not in missing
        },
        via=via,
    )


def easee(
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    charger_id: str = "EH123456",
) -> Registration:
    """HACS `easee`: one HA device per charger, unique ids `<charger id>_<key>`."""
    keys = {
        "status": ("sensor", None, "disconnected"),
        "lifetime_energy": ("sensor", "kWh", "4567.8"),
        "session_energy": ("sensor", "kWh", "0"),
        "cost_day": ("sensor", "EUR", "0"),
        "smart_charging": ("binary_sensor", None, "off"),
    }
    return Registration(
        "easee",
        (
            _charger(
                {
                    key: (platform, f"{charger_id}_{key}", unit, state)
                    for key, (platform, unit, state) in keys.items()
                },
                disabled=disabled,
                missing=missing,
                identifiers={("easee", charger_id)},
                manufacturer="Easee",
                model="Home",
                name="Garage",
            ),
        ),
    )


def zaptec(
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    charger_id: str = "0d1c3f5e-charger",
) -> Registration:
    """HACS `zaptec`: an HA device per installation and per charger, the charger's
    linked to its installation's and after it, unique ids `<id>_<key>`.

    `signed_meter_value_kwh` is only registered for a charger that reports it.
    """
    installation_id = "7a9b2c4d-installation"
    installation = HaDeviceShape(
        {
            "identifiers": {("zaptec", installation_id)},
            "manufacturer": "Zaptec",
            "model": "Zaptec Installation",
            "name": "Home",
        },
        {
            key: EntityShape(
                "sensor", f"{installation_id}_{key}", state=state, unit="A"
            )
            for key, state in (
                ("max_current", "32"),
                ("available_current_phase1", "32"),
            )
        },
    )
    keys = {
        "charger_operation_mode": (None, "disconnected"),
        "signed_meter_value_kwh": ("kWh", "5678.9"),
        "total_charge_power_session": ("kWh", "0"),
        "total_charge_power": ("W", "0"),
    }
    charger = _charger(
        {
            key: ("sensor", f"{charger_id}_{key}", unit, state)
            for key, (unit, state) in keys.items()
        },
        disabled=disabled,
        missing=missing,
        via=0,
        identifiers={("zaptec", charger_id)},
        manufacturer="Zaptec",
        model="Zaptec Go",
        name="Driveway",
    )
    return Registration("zaptec", (installation, charger))


def goe_mqtt(
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    serial: str = "012345",
) -> Registration:
    """HACS `goecharger_mqtt`: one HA device per charger, unique ids
    `<serial>-<platform>-<key>-<attribute or 0>`; both energy counters are in Wh."""
    return Registration(
        "goecharger_mqtt",
        (
            _charger(
                {
                    "car": ("sensor", f"{serial}-sensor-car-car", None, "idle"),
                    "eto": ("sensor", f"{serial}-sensor-eto-0", "Wh", "6789000"),
                    "wh": ("sensor", f"{serial}-sensor-wh-0", "Wh", "0"),
                    "etop": ("sensor", f"{serial}-sensor-etop-0", "Wh", "0"),
                    "car_connected": (
                        "binary_sensor",
                        f"{serial}-binary_sensor-car-1",
                        None,
                        "off",
                    ),
                },
                disabled=disabled,
                missing=missing,
                identifiers={("goecharger_mqtt", serial)},
                manufacturer="go-e",
                model="go-eCharger",
                name="go-eCharger",
            ),
        ),
    )


def goe_api2(
    *,
    disabled: tuple[str, ...] = ("car",),
    missing: tuple[str, ...] = (),
    serial: str = "012345",
) -> Registration:
    """HACS `goecharger_api2`: one HA device per charger, unique ids
    `goecharger_api2.goe_<serial>_<key>`. The raw car state `car` is disabled by
    default; both energy counters are native Wh, shown in kWh."""
    keys = {
        "car_value": (None, "Idle"),
        "car": (None, "1"),
        "eto": ("kWh", "6789.0"),
        "wh": ("kWh", "0"),
        "cus_value": (None, "Unlocked"),
    }
    return Registration(
        "goecharger_api2",
        (
            _charger(
                {
                    key: ("sensor", f"goecharger_api2.goe_{serial}_{key}", unit, state)
                    for key, (unit, state) in keys.items()
                },
                disabled=disabled,
                missing=missing,
                identifiers={("goecharger_api2", serial)},
                manufacturer="go-e",
                model="Gemini",
                name="go-e Charger",
            ),
        ),
    )


def wallbox(
    *,
    disabled: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    serial: str = "123456",
) -> Registration:
    """HA core `wallbox`: one HA device per charger, unique ids `<key>-<serial>`.

    Every energy counter is the session's: Wallbox has no lifetime one.
    """
    keys = {
        "status_description": ("sensor", None, "Ready"),
        "added_energy": ("sensor", "kWh", "0"),
        "added_green_energy": ("sensor", "kWh", "0"),
        "added_grid_energy": ("sensor", "kWh", "0"),
        "added_range": ("sensor", "km", "0"),
        "charging_power": ("sensor", "kW", "0"),
        "cost": ("sensor", "EUR", "0"),
        "energy_price": ("sensor", "EUR/kWh", "0.3"),
        "depot_price": ("sensor", "EUR/kWh", "0.3"),
        "locked": ("lock", None, "locked"),
        "paused": ("switch", None, "off"),
    }
    return Registration(
        "wallbox",
        (
            _charger(
                {
                    key: (platform, f"{key}-{serial}", unit, state)
                    for key, (platform, unit, state) in keys.items()
                },
                disabled=disabled,
                missing=missing,
                identifiers={("wallbox", serial)},
                manufacturer="Wallbox",
                model="PLP1",
                name="Wallbox Garage",
            ),
        ),
    )
