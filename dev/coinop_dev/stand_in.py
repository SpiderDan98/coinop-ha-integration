"""The shared base of the stand-ins, one minimal custom integration per domain under
`dev/`.

A stand-in's config entry is started with the picked kinds (Device Type keys) of its
domain. Its setup registers each kind's HA devices and entities from the description
its Quick Start Piece names, and sets each entity's state from there. A static
stand-in leaves the states alone afterwards: a contributor sets the Status in HA's
developer tools. One that follows helpers renders the states it `follow`s from them.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT, Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    async_track_template_result,
)
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component

from .scenarios import KINDS, PIECES, QuickStartPiece
from .stand_ins import Registration, register


def registrations(domain: str, kinds: list[str]) -> list[Registration]:
    return [
        piece.registration()
        for kind in kinds
        if isinstance(piece := PIECES[f"{domain}.{kind}"], QuickStartPiece)
    ]


def following(helper: str) -> str:
    """The template of a state that is the helper's."""
    return f"{{{{ states('{helper}') }}}}"


class StandInFlow(ConfigFlow):
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    follow: Callable[[str], Mapping[str, str]] = lambda kind: {},
    platforms: Iterable[Platform] = (),
) -> bool:
    """`follow` gives a kind's templates by entity key; `platforms` are the stand-in's
    own, whose entity objects have the description's unique ids and set their states
    themselves."""
    own = set(platforms)
    for kind in entry.data[KINDS]:
        [registration] = registrations(entry.domain, [kind])
        templates = follow(kind)
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
                if spec.disabled or spec.platform in own:
                    continue
                owner = shape.linked if spec.linked and shape.linked else shape.fields
                attributes = (spec.capabilities or {}) | {
                    ATTR_FRIENDLY_NAME: f"{owner['name']} {key.replace('_', ' ')}"
                }
                if spec.unit:
                    attributes[ATTR_UNIT_OF_MEASUREMENT] = spec.unit
                if template := templates.get(key):
                    _follow(hass, entry, added[key], template, attributes)
                else:
                    hass.states.async_set(added[key], spec.state, attributes)
    await hass.config_entries.async_forward_entry_setups(entry, own)
    return True


def _follow(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entity_id: str,
    template: str,
    attributes: Mapping[str, Any],
) -> None:
    @callback
    def update(
        event: Event[EventStateChangedData] | None, updates: list[TrackTemplateResult]
    ) -> None:
        hass.states.async_set(entity_id, str(updates[-1].result), attributes)

    info = async_track_template_result(
        hass, [TrackTemplate(Template(template, hass), None)], update
    )
    info.async_refresh()
    entry.async_on_unload(info.async_remove)


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry, platforms: Iterable[Platform] = ()
) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, list(platforms)):
        return False
    for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        hass.states.async_remove(entity.entity_id)
    return True
