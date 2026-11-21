"""The shared base of the static stand-ins, one minimal custom integration per domain
under `dev/` that has no helpers of its own.

A stand-in's config entry is started with the picked kinds (Device Type keys) of its
domain. Its setup registers each kind's HA devices and entities from the description
its Quick Start Piece names, and sets each entity's state from there. Nothing updates
the states afterwards: a contributor sets the Status in HA's developer tools.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .scenarios import KINDS, PIECES, StaticPiece
from .stand_ins import Registration, register


def registrations(domain: str, kinds: list[str]) -> list[Registration]:
    return [
        piece.registration()
        for kind in kinds
        if isinstance(piece := PIECES[f"{domain}.{kind}"], StaticPiece)
    ]


class StaticStandInFlow(ConfigFlow):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The entry the first kind's description has, keeping the picked kinds."""
        assert user_input is not None, "only loading a Scenario starts it"
        kinds: list[str] = user_input[KINDS]
        [first, *_] = registrations(self.handler, kinds)
        entry = first.entry
        if unique_id := entry.get("unique_id"):
            await self.async_set_unique_id(unique_id)
        return self.async_create_entry(
            title=entry.get("title") or first.devices[0].fields["name"],
            data=entry.get("data", {}) | {KINDS: kinds},
            options=entry.get("options", {}),
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    for registration in registrations(entry.domain, entry.data[KINDS]):
        # Without its camera or image component, a picture Coin-op asks for raises
        # where it should only be missing.
        for platform in {
            spec.platform
            for shape in registration.devices
            for spec in shape.entities.values()
        }:
            await async_setup_component(hass, platform, {})
        added_devices = register(hass, entry, registration)
        for shape, added in zip(registration.devices, added_devices, strict=True):
            for key, spec in shape.entities.items():
                if spec.disabled:
                    continue
                owner = shape.linked if spec.linked and shape.linked else shape.fields
                attributes = (spec.capabilities or {}) | {
                    ATTR_FRIENDLY_NAME: f"{owner['name']} {key.replace('_', ' ')}"
                }
                if spec.unit:
                    attributes[ATTR_UNIT_OF_MEASUREMENT] = spec.unit
                hass.states.async_set(added[key], spec.state, attributes)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        hass.states.async_remove(entity.entity_id)
    return True
