"""WattBill's data is never lost or silently overwritten."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .clock import Clock
from .devices import add_device, add_hub
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value


def wattbill_keys(hass_storage: dict[str, Any]) -> set[str]:
    return {key for key in hass_storage if key.startswith("wattbill.")}


def wattbill_data(hass_storage: dict[str, Any]) -> dict[str, Any]:
    """WattBill's Stores and the config entries, which hold the hub entry."""
    keys = wattbill_keys(hass_storage) | {"core.config_entries"}
    return deepcopy({key: hass_storage.get(key) for key in keys})


async def record_a_run(hass: HomeAssistant, clock: Clock) -> ConfigEntry:
    """A hub with one ended Run and one open Run."""
    entry = await add_hub(hass)
    await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    await set_status(hass, "finished")
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    return entry


async def set_up_again(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


@pytest.mark.parametrize("lost", ["wattbill.catalog", "wattbill.runs", "wattbill.live"])
async def test_a_missing_store_stops_setup_without_writing_and_raises_a_repair_issue(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], lost: str
) -> None:
    entry = await record_a_run(hass, clock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    # As if HA moved a corrupt file aside.
    del hass_storage[lost]
    before = wattbill_data(hass_storage)
    entry_data = dict(entry.data)

    assert not await set_up_again(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert wattbill_data(hass_storage) == before
    assert entry.data == entry_data
    issue = ir.async_get(hass).async_get_issue("wattbill", "data_missing")
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.CRITICAL
    assert issue.translation_placeholders == {"stores": lost}


async def lose_runs(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> ConfigEntry:
    entry = await record_a_run(hass, clock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    del hass_storage["wattbill.runs"]
    assert not await set_up_again(hass, entry)
    return entry


async def start_fix(hass: HomeAssistant) -> Any:
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_init("wattbill", data={"issue_id": "data_missing"})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["restore", "fresh_start"]
    assert result["description_placeholders"] == {"stores": "wattbill.runs"}
    return result


async def test_the_repair_explains_how_to_restore_a_backup_and_changes_nothing(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await lose_runs(hass, clock, hass_storage)
    before = wattbill_data(hass_storage)
    result = await start_fix(hass)
    manager = repairs_flow_manager(hass)
    assert manager is not None

    result = await manager.async_configure(
        result["flow_id"], {"next_step_id": "restore"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "restore"
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert wattbill_data(hass_storage) == before
    assert ir.async_get(hass).async_get_issue("wattbill", "data_missing")


async def test_a_deliberate_fresh_start_starts_the_missing_store_empty(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await lose_runs(hass, clock, hass_storage)
    result = await start_fix(hass)
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_configure(
        result["flow_id"], {"next_step_id": "fresh_start"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "fresh_start"

    result = await manager.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    assert ir.async_get(hass).async_get_issue("wattbill", "data_missing") is None
    assert stored_runs(hass_storage) == []
    # The open Run in the intact live Store is kept.
    assert value(hass, RUNS) == 1
    assert value(hass, TOTAL_COST) > 0

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await set_up_again(hass, entry)


async def test_a_first_setup_starts_with_empty_stores(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert value(hass, RUNS) == 0
    assert hass_storage["wattbill.catalog"]["data"] == {"materials": []}
    assert ir.async_get(hass).async_get_issue("wattbill", "data_missing") is None


@pytest.mark.parametrize(
    "store", ["wattbill.catalog", "wattbill.runs", "wattbill.live"]
)
async def test_data_from_a_newer_major_version_stops_setup_without_writing(
    hass: HomeAssistant, hass_storage: dict[str, Any], store: str
) -> None:
    hass_storage[store] = {
        "version": 2,
        "minor_version": 1,
        "key": store,
        "data": {"runs": [], "written_by": "a newer WattBill"},
    }
    before = wattbill_data(hass_storage)
    entry = MockConfigEntry(domain="wattbill", title="WattBill")
    entry.add_to_hass(hass)

    assert not await set_up_again(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.reason is not None
    assert store in entry.reason
    assert entry.data == {}
    assert wattbill_data(hass_storage) == before


async def test_removing_the_hub_deletes_all_stored_data(
    hass: HomeAssistant,
    clock: Clock,
    hass_storage: dict[str, Any],
    tmp_path: Path,
) -> None:
    hass.config.config_dir = str(tmp_path)
    entry = await record_a_run(hass, clock)
    hass_storage["wattbill.runs.bak"] = {"version": 1, "data": {"runs": []}}
    files = tmp_path / "wattbill"
    (files / "runs").mkdir(parents=True)
    (files / "runs" / "image.webp").write_bytes(b"webp")
    assert wattbill_keys(hass_storage) >= {
        "wattbill.catalog",
        "wattbill.runs",
        "wattbill.live",
    }

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert wattbill_keys(hass_storage) == set()
    assert not files.exists()
