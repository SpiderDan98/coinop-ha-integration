"""How each integration with an Integration Profile registers its HA devices.

Described once, for the tests' fixtures and the dev container's stand-ins alike: each
group's integrations in its own module (`printers`, `appliances`, `ev_chargers`), one
function per integration that returns its `Registration`. Unique ids, units and which
entities are registered follow each integration's source.
"""

from dataclasses import KW_ONLY, dataclass, field, replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

# Stands in for the config entry's id, which only exists once the entry does.
ENTRY_ID = "<entry_id>"


@dataclass(frozen=True)
class EntityShape:
    platform: str
    unique_id: str
    _: KW_ONLY
    # What a stand-in shows, such as an idle status; the tests leave states alone.
    state: str
    unit: str | None = None
    capabilities: dict[str, Any] | None = None
    disabled: bool = False
    # On the HA device's linked one rather than on the HA device itself.
    linked: bool = False
    # Defaults to its HA device's name and its key.
    object_id: str | None = None


@dataclass(frozen=True)
class HaDeviceShape:
    # The device registry's fields: identifiers, name, manufacturer, model, ...
    fields: dict[str, Any]
    entities: dict[str, EntityShape]
    # A second HA device linked to this one with `via_device_id`, such as an ACE unit.
    linked: dict[str, Any] | None = None
    # The index of an HA device before it that it is linked to, such as a charge
    # point's for one of its connectors.
    via: int | None = None

    def suggested_object_id(self, key: str) -> str:
        entity = self.entities[key]
        owner = self.linked if entity.linked and self.linked else self.fields
        return slugify(entity.object_id or f"{owner['name']} {key}")


@dataclass(frozen=True)
class Registration:
    domain: str
    devices: tuple[HaDeviceShape, ...]
    # The config entry's fields: title, data, options, version, unique_id, ...
    entry: dict[str, Any] = field(default_factory=dict)
    # Every HA device of an account goes on the domain's one config entry.
    account: bool = False

    def of_entry(self, entry_id: str) -> Registration:
        """With `ENTRY_ID` replaced by the config entry's id."""

        def fill(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace(ENTRY_ID, entry_id)
            if isinstance(value, (tuple, set)):
                return type(value)(fill(item) for item in value)
            if isinstance(value, dict):
                return {key: fill(item) for key, item in value.items()}
            return value

        return replace(
            self,
            devices=tuple(
                replace(
                    device,
                    fields=fill(device.fields),
                    linked=fill(device.linked),
                    entities={
                        key: replace(entity, unique_id=fill(entity.unique_id))
                        for key, entity in device.entities.items()
                    },
                )
                for device in self.devices
            ),
        )


@dataclass
class HaDevice:
    device: dr.DeviceEntry
    # A second HA device linked to `device` with `via_device_id`, such as an ACE unit.
    linked: dr.DeviceEntry | None
    # Entity ids by the integration's entity key.
    entities: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.entities[key]


def register(
    hass: HomeAssistant, entry: ConfigEntry, registration: Registration
) -> list[HaDevice]:
    """The registration's HA devices and entities, on `entry`, in the registries."""
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
                registration.domain,
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
