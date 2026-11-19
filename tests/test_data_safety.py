"""WattBill's data is never lost or silently overwritten."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_runs import RUNS, set_status, value


def wattbill_keys(hass_storage: dict[str, Any]) -> set[str]:
    return {key for key in hass_storage if key.startswith("wattbill.")}


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


@pytest.mark.parametrize("lost", ["wattbill.runs", "wattbill.live"])
async def test_a_missing_store_stops_setup_without_writing_and_raises_a_repair_issue(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any], lost: str
) -> None:
    entry = await record_a_run(hass, clock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    # As if HA moved a corrupt file aside.
    del hass_storage[lost]
    before = deepcopy(hass_storage)

    assert not await set_up_again(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert {key: hass_storage[key] for key in wattbill_keys(hass_storage)} == {
        key: before[key] for key in wattbill_keys(before)
    }
    assert hass_storage["core.config_entries"] == before["core.config_entries"]
    issue = ir.async_get(hass).async_get_issue("wattbill", "data_missing")
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.CRITICAL
    assert issue.translation_placeholders == {"stores": lost}


async def test_a_first_setup_starts_with_empty_stores(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert value(hass, RUNS) == 0
    assert ir.async_get(hass).async_get_issue("wattbill", "data_missing") is None


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
    assert wattbill_keys(hass_storage) >= {"wattbill.runs", "wattbill.live"}

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert wattbill_keys(hass_storage) == set()
    assert not files.exists()
