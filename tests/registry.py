"""Registers HA devices the way an integration does, for an Integration Profile's
fixture: from the integration's `Registration` in `dev/coinop_dev/stand_ins`, which
the dev container's stand-ins register from too."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Concatenate

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

from dev.coinop_dev.stand_ins import Registration, printers


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


def entity(
    platform: str,
    unique_id: str,
    *,
    unit: str | None = None,
    capabilities: dict[str, Any] | None = None,
    disabled: bool = False,
    linked: bool = False,
    object_id: str | None = None,
) -> dict[str, Any]:
    """An entity of `add_ha_device`: `linked` puts it on the linked HA device, and its
    object id defaults to its HA device's name and its key."""
    return {
        "platform": platform,
        "unique_id": unique_id,
        "unit": unit,
        "capabilities": capabilities,
        "disabled": disabled,
        "linked": linked,
        "object_id": object_id,
    }


def add_ha_device(
    hass: HomeAssistant,
    config_entry: str | ConfigEntry,
    entities: dict[str, dict[str, Any]],
    *,
    linked: dict[str, Any] | None = None,
    via: dr.DeviceEntry | None = None,
    **device: Any,
) -> HaDevice:
    """An HA device of `config_entry` (a domain gets a config entry of its own, an
    entry is used as it is) with `entities` by key, made with `entity`.

    `device` and `linked` are the HA devices' registry fields; their identifiers
    default to the domain and the name. `via` is an HA device the new one is linked
    to, such as a charge point's for one of its connectors.
    """
    if isinstance(config_entry, str):
        mock_entry = MockConfigEntry(domain=config_entry)
        mock_entry.add_to_hass(hass)
    entry = mock_entry if isinstance(config_entry, str) else config_entry
    domain = entry.domain
    devices = dr.async_get(hass)

    def create(fields: dict[str, Any], parent: dr.DeviceEntry | None) -> dr.DeviceEntry:
        created = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            **{"identifiers": {(domain, fields["name"])}} | fields,
        )
        if parent is None:
            return created
        # HA 2026.5 has no `via_device_id` on create and later releases refuse `via_device`.
        updated = devices.async_update_device(created.id, via_device_id=parent.id)
        assert updated is not None
        return updated

    ha_device = create(device, via)
    second = None if linked is None else create(linked, ha_device)

    def owner(spec: dict[str, Any]) -> dr.DeviceEntry:
        if not spec["linked"]:
            return ha_device
        assert second is not None, "a linked entity needs a linked HA device"
        return second

    registry = er.async_get(hass)
    ids = {
        key: registry.async_get_or_create(
            spec["platform"],
            domain,
            spec["unique_id"],
            config_entry=entry,
            device_id=owner(spec).id,
            suggested_object_id=slugify(
                spec["object_id"] or f"{owner(spec).name} {key}"
            ),
            unit_of_measurement=spec["unit"],
            capabilities=spec["capabilities"],
            disabled_by=er.RegistryEntryDisabler.INTEGRATION
            if spec["disabled"]
            else None,
        ).entity_id
        for key, spec in entities.items()
    }
    return HaDevice(ha_device, second, ids)
