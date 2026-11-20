"""Coin-op's data lands in Home Assistant backups and comes back as a whole."""

from copy import deepcopy
from typing import Any

from homeassistant.components.backup import async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.coinop.const import DOMAIN

from .clock import Clock
from .devices import add_device, add_hub
from .test_persistence import live_runs
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value


async def back_up(hass: HomeAssistant) -> None:
    """What Home Assistant does right before it writes a backup."""
    manager = async_get_manager(hass)
    await manager.async_pre_backup_actions()
    await manager.async_post_backup_actions()


async def test_a_backup_first_writes_pending_changes_of_open_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    assert await async_setup_component(hass, "backup", {})
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=60)
    await set_status(hass, "printing")
    await clock.advance(seconds=30)
    assert live_runs(hass_storage) == []

    await back_up(hass)

    [run] = live_runs(hass_storage)
    assert run["ended"] is None


async def test_a_restore_rolls_coinop_back_and_reconciles_the_open_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    assert await async_setup_component(hass, "backup", {})
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await back_up(hass)
    backup = {k: deepcopy(v) for k, v in hass_storage.items() if k.startswith(DOMAIN)}
    [open_run] = live_runs(hass_storage)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    for _ in range(2):
        await set_status(hass, "printing")
        await clock.advance(hours=1)
        await set_status(hass, "finished")
    assert value(hass, RUNS) == 4

    # Restoring replaces Coin-op's files and restarts Home Assistant, by which
    # time the printer is idle.
    assert await hass.config_entries.async_unload(entry.entry_id)
    for key in [k for k in hass_storage if k.startswith(DOMAIN)]:
        del hass_storage[key]
    hass_storage.update(backup)
    await set_status(hass, "idle")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    [first, reconciled] = stored_runs(hass_storage)
    assert first == backup["coinop.runs"]["data"]["runs"][0]
    assert reconciled["id"] == open_run["id"]
    assert reconciled["outcome"] == "unknown"
    assert live_runs(hass_storage) == []
    assert value(hass, RUNS) == 2
    assert value(hass, TOTAL_COST) == pytest.approx(
        sum(item["amount"] for run in (first, reconciled) for item in run["line_items"])
    )
