"""Registers HA devices the way an integration does, for an Integration Profile's
fixture: from the integration's `Registration` in `dev/coinop_dev/stand_ins`, which
the dev container's stand-ins register from too."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Concatenate

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from dev.coinop_dev.stand_ins import Registration, appliances, ev_chargers, printers


@dataclass
class HaDevice:
    device: dr.DeviceEntry
    # A second HA device linked to `device` with `via_device_id`, such as an ACE unit.
    linked: dr.DeviceEntry | None
    # Entity ids by the integration's entity key.
    entities: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def add_ha_devices(hass: HomeAssistant, registration: Registration) -> list[HaDevice]:
    """The registration's config entry (the account's, if the domain has one already
    and its integration keeps an account on one), HA devices and entities."""
    domain = registration.domain
    shared = hass.config_entries.async_entries(domain) if registration.account else []
    if shared:
        entry = shared[0]
    else:
        entry = MockConfigEntry(domain=domain, **registration.entry)
        entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    entities = er.async_get(hass)

    def create(fields: dict[str, Any], parent: dr.DeviceEntry | None) -> dr.DeviceEntry:
        created = devices.async_get_or_create(config_entry_id=entry.entry_id, **fields)
        if parent is None:
            return created
        # HA 2026.5 has no `via_device_id` on create and later releases refuse `via_device`.
        updated = devices.async_update_device(created.id, via_device_id=parent.id)
        assert updated is not None
        return updated

    added: list[HaDevice] = []
    for shape in registration.of_entry(entry.entry_id).devices:
        device = create(
            shape.fields, None if shape.via is None else added[shape.via].device
        )
        linked = None if shape.linked is None else create(shape.linked, device)
        assert linked or not any(spec.linked for spec in shape.entities.values()), (
            "a linked entity needs a linked HA device"
        )
        ids = {
            key: entities.async_get_or_create(
                spec.platform,
                domain,
                spec.unique_id,
                config_entry=entry,
                device_id=(linked if spec.linked and linked else device).id,
                suggested_object_id=shape.suggested_object_id(key),
                unit_of_measurement=spec.unit,
                capabilities=spec.capabilities,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION
                if spec.disabled
                else None,
            ).entity_id
            for key, spec in shape.entities.items()
        }
        added.append(HaDevice(device, linked, ids))
    return added


def first(devices: list[HaDevice]) -> HaDevice:
    return devices[0]


def adding[**P, R](
    describe: Callable[P, Registration], pick: Callable[[list[HaDevice]], R]
) -> Callable[Concatenate[HomeAssistant, P], R]:
    """`describe` as a fixture: registers what it describes and returns `pick` of the
    HA devices."""

    def add(hass: HomeAssistant, /, *args: P.args, **kwargs: P.kwargs) -> R:
        return pick(add_ha_devices(hass, describe(*args, **kwargs)))

    return add


add_anycubic_local = adding(printers.anycubic_local, first)
add_anycubic_cloud = adding(printers.anycubic_cloud, first)
add_bambu_lab = adding(printers.bambu_lab, first)
add_prusalink = adding(printers.prusalink, first)
add_octoprint = adding(printers.octoprint, first)
add_creality = adding(printers.creality, first)
add_elegoo = adding(printers.elegoo, first)
add_moonraker = adding(printers.moonraker, first)
add_washdata = adding(appliances.washdata, first)
add_miele = adding(appliances.miele, first)
add_home_connect = adding(appliances.home_connect, first)
add_home_connect_local = adding(appliances.home_connect_local, first)
add_home_connect_alt = adding(appliances.home_connect_alt, first)
add_lg_thinq = adding(appliances.lg_thinq, first)
add_smartthings = adding(appliances.smartthings, first)
add_wall_connector = adding(ev_chargers.wall_connector, first)
# Each loadpoint's HA device, which with one loadpoint is the site's.
add_evcc_site = adding(
    ev_chargers.evcc_site, lambda devices: devices[2:] or devices[1:]
)
# The charger's HA device, then each connector's.
add_charge_point = adding(ev_chargers.charge_point, lambda devices: devices)
add_easee = adding(ev_chargers.easee, first)
# The charger's HA device, not its installation's.
add_zaptec = adding(ev_chargers.zaptec, lambda devices: devices[1])
add_goe_mqtt = adding(ev_chargers.goe_mqtt, first)
add_goe_api2 = adding(ev_chargers.goe_api2, first)
add_wallbox = adding(ev_chargers.wallbox, first)
