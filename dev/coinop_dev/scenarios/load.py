"""Loading a Scenario: Coin-op set up from scratch with the picked Pieces."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from homeassistant.auth.models import User
from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from custom_components.coinop.const import DOMAIN as COINOP, SUBENTRY_DEVICE

from .pieces import PIECES, DeviceWithHistory, QuickStartPiece, ordered
from .presets import PRESETS
from .seed import SHARED, Api, ScenarioError, Seed, async_set


async def async_load(
    hass: HomeAssistant, choice: str | Mapping[str, Any], user: User | None
) -> dict[str, Any]:
    """Replace whatever Coin-op holds by a Preset or a selection of Pieces; returns
    the selection loaded."""
    if isinstance(choice, str):
        choice = PRESETS[choice].selection
    pieces = ordered(choice["pieces"])
    history, open_run = choice.get("history", "short"), choice.get("open_run", False)
    user = user or await hass.auth.async_get_owner()
    if user is None:
        raise ScenarioError("No user to load the Scenario as")
    stand_ins = {p.domain for p in PIECES.values() if isinstance(p, QuickStartPiece)}
    for domain in (COINOP, *stand_ins):
        for old in hass.config_entries.async_entries(domain):
            await hass.config_entries.async_remove(old.entry_id)
    for piece in PIECES.values():
        for entity_id, value in piece.helpers.items():
            if hass.states.get(entity_id):
                await async_set(hass, entity_id, value)
    entry = await _async_add_hub(hass)
    await hass.config_entries.async_unload(entry.entry_id)
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
    seed = Seed(hass, Api(hass, user), entry, devices)
    needs = {need for piece in with_history.values() for need in piece.needs}
    for need, add in SHARED.items():
        if need in needs:
            await add(seed)
    for piece in (PIECES[name] for name in pieces):
        if isinstance(piece, DeviceWithHistory):
            await piece.fill(seed, history)
        else:
            await piece.fill(seed)
    for name in seed.retired:
        await seed.api.call(
            "coinop/materials/archive", material_id=seed.materials[name]["id"]
        )
    if open_run:
        for piece in with_history.values():
            await piece.open_run(seed)
    return {"pieces": pieces, "history": history, "open_run": open_run}


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
