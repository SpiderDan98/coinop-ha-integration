"""Loading a Scenario: Coin-op set up from scratch with the picked Pieces."""

from collections.abc import Mapping
import logging
from types import MappingProxyType
from typing import Any

from homeassistant.auth.models import User
from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from custom_components.coinop.const import DOMAIN as COINOP, SUBENTRY_DEVICE
from custom_components.coinop.spoolman import CONF_SPOOLMAN_URL

from . import spoolman
from .pieces import PIECES, DeviceWithHistory
from .presets import PRESETS, SELECTION
from .seed import SHARED, Api, ScenarioError, Seed, async_set

_LOGGER = logging.getLogger(__name__)


async def async_load(
    hass: HomeAssistant, choice: str | Mapping[str, Any], user: User | None
) -> dict[str, Any]:
    """Replace whatever Coin-op holds by a Preset or a selection of Pieces; returns
    the selection loaded."""
    selection = (
        PRESETS[choice].selection
        if isinstance(choice, str)
        else SELECTION(dict(choice))
    )
    pieces, history = selection["pieces"], selection["history"]
    user = user or await hass.auth.async_get_owner()
    if user is None:
        raise ScenarioError("No user to load the Scenario as")
    try:
        filaments = await spoolman.async_fill(hass)
    except ScenarioError as err:
        if selection["spoolman"]:
            raise
        _LOGGER.warning("Left Spoolman as it was: %s", err)
        filaments = {}
    for domain in dict.fromkeys([COINOP, *(p.domain for p in PIECES.values())]):
        for old in hass.config_entries.async_entries(domain):
            await hass.config_entries.async_remove(old.entry_id)
    for piece in PIECES.values():
        for entity_id, value in piece.helpers.items():
            if hass.states.get(entity_id):
                await async_set(hass, entity_id, value)
    entry = await _async_add_hub(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    if selection["spoolman"]:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_SPOOLMAN_URL: spoolman.URL}
        )
    with_history = {
        name: piece
        for name in pieces
        if isinstance(piece := PIECES[name], DeviceWithHistory)
    }
    devices = {}
    for name, piece in with_history.items():
        subentry = ConfigSubentry(
            data=MappingProxyType(dict(piece.device)),
            subentry_type=SUBENTRY_DEVICE,
            title=piece.title,
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, subentry)
        devices[name] = subentry.subentry_id
    await hass.config_entries.async_setup(entry.entry_id)
    seed = Seed(
        hass,
        Api(hass, user),
        entry,
        devices,
        history,
        filaments if selection["spoolman"] else {},
    )
    needs = {need for piece in with_history.values() for need in piece.needs}
    for need, add in SHARED.items():
        if need in needs:
            await add(seed)
    for name in pieces:
        await PIECES[name].fill(seed)
    for name in seed.retired:
        await seed.api.call(
            "coinop/materials/archive", material_id=seed.materials[name]["id"]
        )
    if selection["open_run"]:
        for piece in with_history.values():
            await piece.open_run(seed)
    return selection


async def _async_add_hub(hass: HomeAssistant) -> ConfigEntry:
    """The hub entry through its config flow, without the Add Device that follows."""
    result = await hass.config_entries.flow.async_init(
        COINOP, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    if next_flow := result.get("next_flow"):
        hass.config_entries.subentries.async_abort(next_flow[1])
    entry: ConfigEntry = result["result"]
    return entry
