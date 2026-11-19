"""Measured material usage: a Run's Material Line Items from the Material used input."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from .clock import Clock
from .devices import MAPPING, add_device, add_hub, configure, walk_to_mapping
from .stored import place_materials, stored_material
from .test_lifecycle import start_wattbill, stop_wattbill
from .test_persistence import live_runs
from .test_runs import set_status, stored_runs, value
from .websocket import PanelClient

FILAMENT = "sensor.kobra_filament_used"
MATERIAL_COST = "sensor.kobra_material_cost"
MATERIAL_USED = "sensor.kobra_material_used"
# 1 m of 1.75 mm filament is 2.405 cm³; PLA at 1.24 g/cm³ weighs 2.983 g.
GRAMS_PER_METRE = 2.98255


async def set_usage(hass: HomeAssistant, used: float | str, unit: str = "mm") -> None:
    hass.states.async_set(FILAMENT, str(used), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def add_measuring_device(
    hass: HomeAssistant,
    panel: PanelClient,
    *,
    default: str | None = "pla",
    **inputs: Any,
) -> ConfigEntry:
    """A Device whose Material used input is FILAMENT (in mm), with a default Material."""
    if "material" not in inputs:
        await set_usage(hass, 0)
    entry = await add_hub(hass)
    device = await add_device(hass, entry, **({"material": FILAMENT} | inputs))
    if default:
        await panel.call(
            "wattbill/devices/update_settings",
            device_id=device.subentry_id,
            settings={"default_material": default},
        )
    return entry


def material_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in run["line_items"] if item["kind"] == "material"]


async def walk_to_job(hass: HomeAssistant) -> Any:
    entry = await add_hub(hass)
    result = await configure(hass, await walk_to_mapping(hass, entry), MAPPING)
    assert result["step_id"] == "job"
    return result


async def test_the_material_used_input_is_a_length_or_a_mass(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    grams = entity_registry.async_get_or_create(
        "sensor", "printer", "grams", unit_of_measurement="g"
    )
    hass.states.async_set(grams.entity_id, STATE_UNAVAILABLE)
    hass.states.async_set(FILAMENT, "0", {"unit_of_measurement": "W"})
    result = await walk_to_job(hass)

    refused = await configure(hass, result, {"material_entity_id": FILAMENT})
    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {"material_entity_id": "not_length_or_mass"}

    # The unit comes from the entity registry while the entity is unavailable.
    accepted = await configure(hass, refused, {"material_entity_id": grams.entity_id})
    assert accepted["step_id"] == "images", accepted.get("errors")


async def test_a_material_used_attribute_asks_for_its_unit(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(FILAMENT, "idle", {"length": 1200})
    result = await walk_to_job(hass)

    result = await configure(
        hass,
        result,
        {"material_entity_id": FILAMENT, "material_attribute": "length"},
    )
    assert result["step_id"] == "material_unit"
    refused = await configure(hass, result, {"unit": "pcs"})
    assert refused["errors"] == {"unit": "not_length_or_mass"}
    result = await configure(hass, refused, {"unit": "mm"})

    assert result["step_id"] == "images", result.get("errors")


async def test_the_material_used_input_is_stored_with_the_job(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set(FILAMENT, "12", {"unit_of_measurement": "m"})
    entry = await add_hub(hass)

    device = await add_device(hass, entry, job="sensor.kobra_job", material=FILAMENT)

    assert device.data["job"] == {
        "entity_id": "sensor.kobra_job",
        "attribute": None,
        "material": {"entity_id": FILAMENT, "attribute": None, "unit": "m"},
    }


async def test_a_measured_length_becomes_grams_of_the_default_material(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla", name="Black PLA"))
    await add_measuring_device(hass, panel)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_usage(hass, 1500)
    await clock.advance(minutes=30)
    await set_status(hass, "finished")
    await clock.advance(minutes=1)
    await set_usage(hass, 2000)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert {
        key: item[key]
        for key in ("material_id", "unit", "unit_price", "length", "material")
    } == {
        "material_id": "pla",
        "unit": "g",
        "unit_price": 0.02,
        "length": 2000,
        "material": {
            "name": "Black PLA",
            "type": "PLA",
            "density": 1.24,
            "diameter": 1.75,
            "price_per_gram": 0.02,
        },
    }
    assert item["quantity"] == pytest.approx(2 * GRAMS_PER_METRE)
    assert item["amount"] == pytest.approx(2 * GRAMS_PER_METRE * 0.02)
    assert run["flags"] == []
    assert value(hass, MATERIAL_USED) == pytest.approx(2 * GRAMS_PER_METRE)
    assert value(hass, MATERIAL_COST) == pytest.approx(2 * GRAMS_PER_METRE * 0.02)


async def test_material_usage_is_live_while_the_run_is_open(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_measuring_device(hass, panel)
    await set_status(hass, "printing")

    await set_usage(hass, 1000)

    [run] = (await panel.call("wattbill/runs/list"))["runs"]
    detail = (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]
    [item] = material_items(detail)
    assert item["quantity"] == pytest.approx(GRAMS_PER_METRE)
    assert (item["locked"], item["deletable"]) == (True, False)
    assert value(hass, MATERIAL_USED) == pytest.approx(GRAMS_PER_METRE)


async def test_without_a_report_after_the_end_the_last_value_applies_after_five_minutes(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_measuring_device(hass, panel)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    await set_usage(hass, 3000)
    await clock.advance(minutes=50)

    await set_status(hass, "finished")
    # The printer resets its counter: 0 is no usage.
    await set_usage(hass, 0)
    await clock.advance(minutes=4, seconds=59)
    [waiting] = live_runs(hass_storage)
    assert waiting["finalised"] is False
    assert stored_runs(hass_storage) == []
    await clock.advance(seconds=1)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["length"] == 3000
    assert item["quantity"] == pytest.approx(3 * GRAMS_PER_METRE)


async def test_a_value_from_before_the_run_is_not_its_usage(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """The printer still shows the last job's total when the next one starts."""
    place_materials(hass_storage, stored_material("pla"))
    await set_usage(hass, 4000)
    await add_measuring_device(hass, panel, material=FILAMENT)
    await clock.advance(minutes=1)
    await set_status(hass, "printing")
    await set_usage(hass, 4000)
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["quantity"], item["length"], item["material_id"]) == (
        None,
        None,
        "pla",
    )
    assert run["flags"] == ["usage_missing"]


async def test_a_mass_is_taken_as_grams(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_measuring_device(hass, panel)
    await set_status(hass, "printing")
    await set_usage(hass, 0.0125, "kg")
    await set_status(hass, "finished")
    await clock.advance(minutes=5)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert (item["quantity"], item["length"]) == (pytest.approx(12.5), None)
    assert item["amount"] == pytest.approx(0.25)


async def test_repricing_or_renaming_a_material_never_changes_past_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    await add_measuring_device(hass, panel)
    await set_status(hass, "printing")
    await set_usage(hass, 1000)
    await set_status(hass, "finished")
    await clock.advance(minutes=5)
    [before] = stored_runs(hass_storage)

    await panel.call(
        "wattbill/materials/update",
        material_id="pla",
        material={
            "name": "PLA (new brand)",
            "density": 1.3,
            "price": {"source": "fixed", "pack_price": 40, "pack_size": 1000},
        },
    )

    [after] = stored_runs(hass_storage)
    assert after == before
    assert value(hass, MATERIAL_COST) == pytest.approx(GRAMS_PER_METRE * 0.02)


async def test_usage_reported_while_wattbill_was_stopped_still_counts(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_materials(hass_storage, stored_material("pla"))
    entry = await add_measuring_device(hass, panel)
    await set_status(hass, "printing")
    await set_usage(hass, 1000)
    await clock.advance(hours=1)
    await set_status(hass, "finished")
    await stop_wattbill(hass, entry)

    await clock.advance(minutes=2)
    await set_usage(hass, 1500)
    await start_wattbill(hass, entry)

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert item["length"] == 1500


RESIN = stored_material(
    "resin",
    form="resin",
    type="Standard resin",
    density=1.1,
    diameter=None,
    price={"source": "fixed", "pack_price": 30, "pack_size": 1000, "pack_unit": "ml"},
)


async def test_without_a_material_used_input_the_default_material_waits_for_a_quantity(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """A resin printer reports no usage: the user types the millilitres."""
    place_materials(hass_storage, RESIN)
    await add_measuring_device(hass, panel, default="resin", material=None)
    await set_status(hass, "printing")
    await clock.advance(hours=1)

    await set_status(hass, "finished")

    [run] = stored_runs(hass_storage)
    [item] = material_items(run)
    assert {
        key: item[key]
        for key in ("material_id", "quantity", "unit", "unit_price", "amount")
    } == {
        "material_id": "resin",
        "quantity": None,
        "unit": "ml",
        "unit_price": pytest.approx(0.03),
        "amount": 0,
    }
    assert item["material"]["name"] == "RESIN"
    assert run["flags"] == ["usage_missing"]


@pytest.mark.parametrize(
    ("used", "unit", "quantity", "length"),
    [(2000, "mm", None, 2000), (8, "g", 8, None)],
)
async def test_without_a_default_material_the_measurement_is_kept_at_price_0(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    used: float,
    unit: str,
    quantity: float | None,
    length: float | None,
) -> None:
    """A length can only become grams once the user picks the Material."""
    await add_measuring_device(hass, panel, default=None)
    await set_status(hass, "printing")
    await set_usage(hass, used, unit)
    await set_status(hass, "finished")
    await clock.advance(minutes=5)

    [run] = (await panel.call("wattbill/runs/list"))["runs"]
    detail = (await panel.call("wattbill/runs/get", run_id=run["id"]))["run"]
    [item] = material_items(detail)
    assert {
        key: item[key]
        for key in ("material_id", "material", "quantity", "length", "amount")
    } == {
        "material_id": None,
        "material": None,
        "quantity": quantity,
        "length": length,
        "amount": 0,
    }
    assert detail["flags"] == ["material_missing"]
