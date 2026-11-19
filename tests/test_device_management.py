"""After setup: WattBill's own HA device per Device, renaming and removing Devices."""

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from .clock import Clock
from .devices import ENERGY, add_device, add_hub, add_printer
from .test_measured import electricity, set_meter
from .test_persistence import live_runs, restart
from .test_runs import RUNS, TOTAL_COST, set_status, stored_runs, value


def wattbill_device(hass: HomeAssistant, entity_id: str = TOTAL_COST) -> dr.DeviceEntry:
    entity = er.async_get(hass).async_get(entity_id)
    assert entity is not None, entity_id
    assert entity.device_id is not None, entity_id
    device = dr.async_get(hass).async_get(entity.device_id)
    assert isinstance(device, dr.DeviceEntry), entity_id
    return device


async def test_a_devices_entities_sit_on_its_own_ha_device_linked_to_the_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass, "Kobra S1")
    entry = await add_hub(hass)

    await add_device(hass, entry, name="Kobra", printer=printer.id)

    device = wattbill_device(hass)
    assert device.id != printer.id
    assert device.name == "Kobra"
    assert device.via_device_id == printer.id
    assert wattbill_device(hass, "sensor.kobra_runs") == device


async def test_without_a_printer_device_the_ha_device_stands_alone(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    await add_device(hass, entry, name="Kobra")

    device = wattbill_device(hass)
    assert device.name == "Kobra"
    assert device.via_device_id is None


async def rename(hass: HomeAssistant, name: str) -> None:
    dr.async_get(hass).async_update_device(wattbill_device(hass).id, name_by_user=name)
    await hass.async_block_till_done()


async def test_renaming_the_ha_device_renames_the_device(hass: HomeAssistant) -> None:
    entry = await add_hub(hass)
    subentry = await add_device(hass, entry, name="Kobra")

    await rename(hass, "Workshop Kobra")

    assert entry.subentries[subentry.subentry_id].title == "Workshop Kobra"
    assert wattbill_device(hass).name == "Workshop Kobra"


async def test_runs_carry_the_devices_new_name(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, name="Kobra")
    await set_status(hass, "printing")
    await set_status(hass, "finished")
    await set_status(hass, "printing")

    await rename(hass, "Workshop Kobra")
    await set_status(hass, "finished")

    assert [run["device_name"] for run in stored_runs(hass_storage)] == [
        "Workshop Kobra",
        "Workshop Kobra",
    ]


async def remove(
    hass: HomeAssistant, entry: ConfigEntry, device: ConfigSubentry
) -> None:
    assert hass.config_entries.async_remove_subentry(entry, device.subentry_id)
    await hass.async_block_till_done()


async def test_removing_a_device_ends_its_open_run_as_unknown(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, running_power=100, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await remove(hass, entry, kobra)

    [run] = stored_runs(hass_storage)
    assert run["outcome"] == "unknown"
    assert run["ended"] == clock.now().isoformat()
    assert run["line_items"][0]["amount"] == pytest.approx(0.1)
    assert live_runs(hass_storage) == []


async def add_metered(hass: HomeAssistant) -> tuple[ConfigEntry, ConfigSubentry]:
    await set_meter(hass, 10.0)
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, source="energy", meter={"entity_id": ENERGY})
    return entry, kobra


async def test_removing_a_device_finalises_a_run_waiting_for_its_final_report(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry, kobra = await add_metered(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, 10.3)
    await clock.advance(minutes=1)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)

    await remove(hass, entry, kobra)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["finalised"]) == ("completed", True)
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert live_runs(hass_storage) == []


async def test_removing_a_device_does_not_wait_for_the_meters_final_report(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry, kobra = await add_metered(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_meter(hass, 10.3)
    await clock.advance(minutes=1)

    await remove(hass, entry, kobra)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["finalised"]) == ("unknown", True)
    assert run["ended"] == clock.now().isoformat()
    assert electricity(run)["quantity"] == pytest.approx(0.3)
    assert live_runs(hass_storage) == []


async def test_removing_a_device_removes_its_ha_device_and_entities(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, printer=printer.id)
    device_id = wattbill_device(hass).id

    await remove(hass, entry, kobra)

    assert dr.async_get(hass).async_get(device_id) is None
    assert dr.async_get(hass).async_get(printer.id) is not None
    assert er.async_get(hass).async_get(TOTAL_COST) is None
    assert hass.states.get(TOTAL_COST) is None


async def test_a_removed_devices_runs_are_kept_under_its_last_name(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry)
    await set_status(hass, "printing")
    await set_status(hass, "finished")
    await rename(hass, "Workshop Kobra")

    await remove(hass, entry, kobra)
    await restart(hass, entry)

    [run] = stored_runs(hass_storage)
    assert run["device_id"] == kobra.subentry_id
    assert run["device_name"] == "Workshop Kobra"


async def test_re_adding_the_same_printer_creates_a_new_unlinked_device(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    printer = add_printer(hass)
    entry = await add_hub(hass)
    kobra = await add_device(hass, entry, printer=printer.id, price=1)
    await set_status(hass, "printing")
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await remove(hass, entry, kobra)

    again = await add_device(hass, entry, printer=printer.id)

    assert again.subentry_id != kobra.subentry_id
    assert value(hass, RUNS) == 0
    assert value(hass, TOTAL_COST) == 0
    [run] = stored_runs(hass_storage)
    assert run["device_id"] == kobra.subentry_id
