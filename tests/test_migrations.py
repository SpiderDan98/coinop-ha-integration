"""Stored data of every released schema version loads into the current version.

`fixtures/storage/<major>.<minor>/` holds the Store files exactly as that
version wrote them, the hub entry's data (`entry.json`) and the Runs and
catalogue as the current version stores them after migrating (`current.json`). Add a folder for
every released schema version; once released, never change it except
`current.json`. Until then it follows what the code writes.
"""

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .clock import Clock
from .devices import add_device
from .test_persistence import live_runs
from .test_runs import RUNS, set_status, stored_runs, value
from .websocket import PanelClient

FIXTURES = Path(__file__).parent / "fixtures" / "storage"
STORES = ("wattbill.catalog", "wattbill.runs", "wattbill.live")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "version", sorted(folder.name for folder in FIXTURES.iterdir())
)
async def test_stored_data_of_a_released_version_migrates_to_current(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    version: str,
) -> None:
    fixture = FIXTURES / version
    files = {key: read(fixture / key) for key in STORES if (fixture / key).exists()}
    hass_storage.update(files)
    entry = MockConfigEntry(
        domain="wattbill", title="WattBill", data=read(fixture / "entry.json")
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # A new Run makes WattBill write both Stores in the current version.
    await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    await set_status(hass, "finished")

    assert value(hass, RUNS) == 1
    current = read(fixture / "current.json")
    fixture_ids = {run["id"] for run in current["runs"] + current["live"]}
    assert [r for r in stored_runs(hass_storage) if r["id"] in fixture_ids] == current[
        "runs"
    ]
    assert live_runs(hass_storage) == current["live"]
    listed = (await panel.call("wattbill/materials/list"))["materials"]
    assert [
        {key: value for key, value in m.items() if key != "price_per_gram"}
        for m in listed
    ] == current["catalog"]["materials"]
    for key, file in files.items():
        if file["version"] < hass_storage[key]["version"]:
            assert hass_storage[f"{key}.bak"]["data"] == file["data"]
            assert hass_storage[f"{key}.bak"]["version"] == file["version"]
        else:
            assert f"{key}.bak" not in hass_storage


async def test_fields_added_by_a_newer_minor_version_are_kept(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    newer = read(FIXTURES / "1.1" / "wattbill.runs")
    newer["minor_version"] = 99
    [run, _] = newer["data"]["runs"]
    run["customer"] = "Lena"
    run["line_items"][0]["override"] = {"amount": 0.1}
    run["line_items"][0]["segments"][0]["source"] = "sensor.price"
    hass_storage["wattbill.runs"] = newer
    entry = MockConfigEntry(
        domain="wattbill", title="WattBill", data={"stores": ["runs"]}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    await set_status(hass, "finished")

    [kept] = [r for r in stored_runs(hass_storage) if r["id"] == run["id"]]
    assert kept == run
