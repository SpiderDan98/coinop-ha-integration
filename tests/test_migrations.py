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

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .clock import Clock
from .devices import ENERGY, add_device, add_hub
from .stored import place_runs, stored_run
from .test_dynamic_price import PRICE_ENTITY, segments, set_price
from .test_lifecycle import at, start_coinop, stop_coinop
from .test_measured import electricity, set_meter
from .test_persistence import live_runs
from .test_runs import NO_MATERIAL, RUNS, set_status, stored_runs, value
from .websocket import PanelClient

FIXTURES = Path(__file__).parent / "fixtures" / "storage"
# The hub entry with its Device subentries as each config entry version stored it.
ENTRIES = Path(__file__).parent / "fixtures" / "config_entry"
STORES = ("coinop.catalog", "coinop.runs", "coinop.live")
UNUSED_PROGRESS = {
    "progress": {"remaining_time": None, "progress": None, "expected_energy": None}
}


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
        domain="coinop", title="Coin-op", data=read(fixture / "entry.json")
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # A new Run makes Coin-op write both Stores in the current version.
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
    listed = (await panel.call("coinop/materials/list"))["materials"]
    assert [
        {
            key: value
            for key, value in m.items()
            if key not in ("price_per_gram", "price_per_piece")
        }
        for m in listed
    ] == current["catalog"]["materials"]
    await panel.subscribe("coinop/catalog/subscribe")
    catalog = await panel.event()
    assert catalog["tags"] == current["catalog"]["tags"]
    assert catalog["templates"] == current["catalog"]["templates"]
    for key, file in files.items():
        if file["version"] < hass_storage[key]["version"]:
            assert hass_storage[f"{key}.bak"]["data"] == file["data"]
            assert hass_storage[f"{key}.bak"]["version"] == file["version"]
        else:
            assert f"{key}.bak" not in hass_storage


async def test_fields_added_by_a_newer_minor_version_are_kept(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    newer = read(FIXTURES / "1.1" / "coinop.runs")
    newer["minor_version"] = 99
    [run, _] = newer["data"]["runs"]
    run["customer"] = "Lena"
    run["line_items"][0]["override"] = {"amount": 0.1}
    run["line_items"][0]["segments"][0]["source"] = "sensor.price"
    hass_storage["coinop.runs"] = newer
    entry = MockConfigEntry(domain="coinop", title="Coin-op", data={"stores": ["runs"]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await add_device(hass, entry)
    await set_status(hass, "printing")
    await clock.advance(minutes=5)
    await set_status(hass, "finished")

    [kept] = [r for r in stored_runs(hass_storage) if r["id"] == run["id"]]
    assert kept == run


def store_file(key: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": 1, "minor_version": 1, "key": key, "data": {"runs": runs}}


def open_metered_run(device: ConfigSubentry) -> dict[str, Any]:
    """An open Run on an energy meter and a price entity, as version 1.1 stored it."""
    return {
        "id": "01KF0000000000000000000004",
        "device_id": device.subentry_id,
        "device_name": device.title,
        "name": None,
        "job_name": None,
        "started": at(minutes=-30),
        "last_seen": at(minutes=-1),
        "ended": None,
        "outcome": None,
        "end_reconstructed": False,
        "finalised": False,
        "pauses": [],
        "flags": [],
        "part_count": 1,
        "note": None,
        "tags": [],
        "consumption": dict(device.data["consumption"]),
        "readings": [[at(minutes=-30), 10.0], [at(minutes=-10), 10.2]],
        "cost_source": dict(device.data["price"]),
        "prices": [[at(minutes=-30), 0.2], [at(minutes=-15), 0.4]],
        "average_powers": [[at(minutes=-30), None, None]],
        "usage": None,
        "loaded_slots": [],
        "line_items": [
            {
                "id": "01KF0000000000000000000I04",
                "kind": "electricity",
                "label": None,
                "material_id": None,
                "material": None,
                "measured": False,
                "length": None,
                "slots": [],
                "share": None,
                "template_id": None,
                "basis": None,
                "quantity": 0.2225,
                "unit": "kWh",
                "unit_price": 0.08,
                "amount": 0.08,
                "method": "measured",
                "segments": [
                    {
                        "start": at(minutes=-30),
                        "end": at(minutes=-15),
                        "kwh": 0.15,
                        "unit_price": 0.2,
                    },
                    {
                        "start": at(minutes=-15),
                        "end": at(minutes=-1),
                        "kwh": 0.0725,
                        "unit_price": 0.4,
                    },
                ],
                "computed": None,
            }
        ],
        "images": [],
        "cover_id": None,
    }


async def test_an_open_metered_run_of_1_1_resumes_and_finalises_alike(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.25)
    await set_price(hass, 0.4)
    entry = await add_hub(hass)
    device = await add_device(
        hass, entry, source="energy", meter={"entity_id": ENERGY}, price=PRICE_ENTITY
    )
    await set_status(hass, "printing")
    await stop_coinop(hass, entry)
    hass_storage["coinop.runs"] = store_file("coinop.runs", [])
    hass_storage["coinop.live"] = store_file("coinop.live", [open_metered_run(device)])

    await start_coinop(hass, entry)
    await clock.advance(minutes=30)
    await set_meter(hass, 10.6)
    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    assert run["id"] == "01KF0000000000000000000004"
    assert electricity(run)["quantity"] == pytest.approx(0.6)
    assert electricity(run)["amount"] == pytest.approx(0.15 * 0.2 + 0.45 * 0.4)
    assert segments(run) == [
        (at(minutes=-30), at(minutes=-15), 0.15, 0.2),
        (at(minutes=-15), at(minutes=30), 0.45, 0.4),
    ]
    assert run["flags"] == NO_MATERIAL


async def test_devices_stored_before_device_types_become_3d_printers(
    hass: HomeAssistant, panel: PanelClient
) -> None:
    stored = read(ENTRIES / "1.1.json")
    entry = MockConfigEntry(
        domain="coinop",
        title="Coin-op",
        version=stored["version"],
        minor_version=stored["minor_version"],
        data=stored["data"],
        options=stored["options"],
        subentries_data=stored["subentries"],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert [
        (s.subentry_id, s.subentry_type, s.title, s.unique_id, dict(s.data))
        for s in entry.subentries.values()
    ] == [
        (
            s["subentry_id"],
            s["subentry_type"],
            s["title"],
            s["unique_id"],
            s["data"] | {"device_type": "3d_printer"} | UNUSED_PROGRESS,
        )
        for s in stored["subentries"]
    ]
    assert entry.options == stored["options"]
    listed = (await panel.call("coinop/devices/list"))["devices"]
    assert [d["type"] for d in listed] == ["3d_printer", "3d_printer"]


async def test_devices_stored_before_the_progress_section_load_with_it_unused(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    stored = read(ENTRIES / "1.2.json")
    final = stored_run("final")
    place_runs(hass_storage, final, stored_run("open", ended=False))
    entry = MockConfigEntry(
        domain="coinop",
        title="Coin-op",
        version=stored["version"],
        minor_version=stored["minor_version"],
        data=stored["data"],
        options=stored["options"],
        subentries_data=stored["subentries"],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert [dict(s.data) for s in entry.subentries.values()] == [
        s["data"] | UNUSED_PROGRESS for s in stored["subentries"]
    ]
    [item] = (await panel.call("coinop/runs/get", run_id="final"))["run"]["line_items"]
    assert (item["quantity"], item["unit_price"]) == (0.24, 0.30)
    [kept] = stored_runs(hass_storage)
    assert kept["line_items"] == final["line_items"]
