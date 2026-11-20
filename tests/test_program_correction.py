"""Correcting a Run's Program re-applies the new Program's defaults (ADR 0002)."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_hub, add_washing_machine
from .stored import place_materials
from .test_doses import DOSES, LIQUID, PODS, SCALE, WHITENER, set_scale
from .test_manual_runs import create
from .test_programs import WASHER_PROGRAM, set_program
from .test_runs import stored_runs, value
from .test_washing_machines import set_washer
from .test_water import set_water
from .websocket import PanelClient

# 0.30 per kWh, 0.004 per L; 0.006 per ml of liquid, 0.004 per g of whitener.
ROWS = {
    "default": {"doses": {"dose-liquid": 75}, "kwh": 0.8, "litres": 40},
    "programs": {
        "Cotton 40°": {"doses": {"dose-liquid": 60}, "kwh": 0.6, "litres": 50},
        "White 60°": {
            "doses": {"dose-liquid": 70, "dose-whitener": 20},
            "kwh": 1.4,
            "litres": 55,
        },
    },
}


async def add_washer(
    hass: HomeAssistant, hass_storage: dict[str, Any], water: str = "per_program"
) -> ConfigSubentry:
    """A washing machine with electricity per Program, a Program input and the
    laundry Materials."""
    hass.config.currency = "EUR"
    place_materials(hass_storage, LIQUID, PODS, WHITENER)
    await set_washer(hass, "off")
    await set_program(hass, "unknown")
    return await add_washing_machine(
        hass,
        await add_hub(hass),
        program={"entity_id": WASHER_PROGRAM},
        source="per_program",
        water=water,
    )


@pytest.fixture
async def washer(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> ConfigSubentry:
    """Water per Program too."""
    return await add_washer(hass, hass_storage)


async def set_rows(
    panel: PanelClient, washer: ConfigSubentry, rows: dict[str, Any] = ROWS
) -> None:
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES, "program_defaults": rows},
    )


async def washed(
    hass: HomeAssistant, clock: Clock, program: str, outcome: str = "finished"
) -> None:
    await set_program(hass, program)
    await set_washer(hass, "running")
    await clock.advance(minutes=90)
    await set_washer(hass, outcome)


async def correct(panel: PanelClient, run_id: str, program: str | None) -> Any:
    result = await panel.call("coinop/runs/update", run_id=run_id, program=program)
    return result["run"]


def costs(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Each Line Item's kind (or Dose), where it came from, quantity and amount."""
    return [
        (
            item.get("dose_id") or item["kind"],
            item.get("dose_source") or item["method"],
            item["quantity"],
            item["amount"],
        )
        for item in run["line_items"]
    ]


async def test_correcting_an_ended_runs_program_re_applies_its_defaults(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "Cotton 40°")
    [run] = stored_runs(hass_storage)

    corrected = await correct(panel, run["id"], "White 60°")

    expected = [
        ("electricity", "program_default", pytest.approx(1.4), pytest.approx(0.42)),
        ("water", "program_default", pytest.approx(55), pytest.approx(0.22)),
        ("dose-liquid", "program_default", 70, pytest.approx(0.42)),
        ("dose-whitener", "program_default", 20, pytest.approx(0.08)),
    ]
    assert costs(corrected) == expected
    [run] = stored_runs(hass_storage)
    assert (run["program"], costs(run)) == ("White 60°", expected)


async def test_measured_water_and_an_overridden_dose_stay_as_they_were(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await set_water(hass, 1000)
    washer = await add_washer(hass, hass_storage, water="meter")
    await set_rows(panel, washer)
    await set_program(hass, "Cotton 40°")
    await set_washer(hass, "running")
    await set_water(hass, 1000)
    await clock.advance(minutes=90)
    await set_water(hass, 1048)
    await set_washer(hass, "finished")
    await set_water(hass, 1048)
    [run] = stored_runs(hass_storage)
    liquid = next(i for i in run["line_items"] if i.get("dose_id") == "dose-liquid")
    await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=liquid["id"],
        quantity=100,
    )

    corrected = await correct(panel, run["id"], "White 60°")

    assert costs(corrected) == [
        ("electricity", "program_default", pytest.approx(1.4), pytest.approx(0.42)),
        ("water", "measured", pytest.approx(48), pytest.approx(0.19)),
        ("dose-liquid", "program_default", 100, pytest.approx(0.6)),
        ("dose-whitener", "program_default", 20, pytest.approx(0.08)),
    ]


async def test_a_dose_the_new_program_leaves_empty_loses_its_line_item(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "White 60°")
    [run] = stored_runs(hass_storage)

    corrected = await correct(panel, run["id"], None)

    assert (corrected["program"], costs(corrected)) == (
        None,
        [
            ("electricity", "program_default", pytest.approx(0.8), pytest.approx(0.24)),
            ("water", "program_default", pytest.approx(40), pytest.approx(0.16)),
            ("dose-liquid", "default_row", 75, pytest.approx(0.45)),
        ],
    )


async def test_a_dose_measured_by_its_stock_input_stays(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 1000)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "doses": [*DOSES[:2], DOSES[2] | {"stock": {"entity_id": SCALE}}],
            "program_defaults": ROWS,
        },
    )
    await set_program(hass, "White 60°")
    await set_washer(hass, "running")
    await set_scale(hass, 1000)
    await clock.advance(minutes=90)
    await set_scale(hass, 985)
    await set_washer(hass, "finished")
    await set_scale(hass, 985)
    [run] = stored_runs(hass_storage)

    corrected = await correct(panel, run["id"], "Cotton 40°")

    assert costs(corrected)[2:] == [
        ("dose-liquid", "program_default", 60, pytest.approx(0.36)),
        ("dose-whitener", "stock_input", 15, pytest.approx(0.06)),
    ]


async def test_sensor_totals_follow_the_correction(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "Cotton 40°")
    assert value(hass, "sensor.washer_total_cost") == pytest.approx(0.18 + 0.2 + 0.36)
    [run] = stored_runs(hass_storage)

    await correct(panel, run["id"], "White 60°")

    assert value(hass, "sensor.washer_total_cost") == pytest.approx(
        0.42 + 0.22 + 0.42 + 0.08
    )
    assert value(hass, "sensor.washer_energy_in_runs") == pytest.approx(1.4)
    assert value(hass, "sensor.washer_water_in_runs") == pytest.approx(55)


async def test_saving_the_same_program_re_applies_nothing(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "Cotton 40°")
    [run] = stored_runs(hass_storage)
    before = costs(run)
    await set_rows(panel, washer, {"default": {"doses": {}}})

    corrected = await correct(panel, run["id"], " Cotton 40° ")

    assert costs(corrected) == [
        (kind, source, quantity, pytest.approx(amount))
        for kind, source, quantity, amount in before
    ]


async def test_a_new_program_without_kwh_leaves_electricity_empty_and_flagged(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(
        panel,
        washer,
        {
            "default": {"doses": {}},
            "programs": {
                "Cotton 40°": {"doses": {}, "kwh": 0.6, "litres": 50},
                "Wool": {"doses": {}, "litres": 45},
            },
        },
    )
    await washed(hass, clock, "Cotton 40°")
    [run] = stored_runs(hass_storage)

    corrected = await correct(panel, run["id"], "Wool")

    assert costs(corrected) == [
        ("electricity", "program_default", None, 0.0),
        ("water", "program_default", pytest.approx(45), pytest.approx(0.18)),
    ]
    assert corrected["flags"] == ["default_missing"]


async def test_correcting_an_open_runs_program_applies_its_defaults_at_once(
    hass: HomeAssistant, clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer)
    await set_program(hass, "Cotton 40°")
    await set_washer(hass, "running")
    await clock.advance(minutes=10)
    [running] = (await panel.call("coinop/runs/list"))["runs"]

    corrected = await correct(panel, running["id"], "White 60°")

    assert (corrected["name"], corrected["total"]) == (
        "White 60°",
        pytest.approx(0.42 + 0.22 + 0.42 + 0.08),
    )


async def test_correcting_a_manual_runs_program_re_applies_its_defaults(
    clock: Clock, washer: ConfigSubentry, panel: PanelClient
) -> None:
    await set_rows(panel, washer)
    await clock.advance(hours=3)
    run = await create(panel, washer.subentry_id, program="Cotton 40°")

    corrected = await correct(panel, run["id"], "White 60°")

    assert costs(corrected) == [
        ("electricity", "program_default", pytest.approx(1.4), pytest.approx(0.42)),
        ("water", "program_default", pytest.approx(55), pytest.approx(0.22)),
        ("dose-liquid", "program_default", 70, pytest.approx(0.42)),
        ("dose-whitener", "program_default", 20, pytest.approx(0.08)),
    ]


async def weigh_whitener(panel: PanelClient, washer: ConfigSubentry) -> None:
    await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "doses": [*DOSES[:2], DOSES[2] | {"stock": {"entity_id": SCALE}}],
            "program_defaults": ROWS,
        },
    )


async def test_a_stocked_dose_without_a_reading_takes_the_new_programs_amount(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, STATE_UNAVAILABLE)
    await weigh_whitener(panel, washer)
    await washed(hass, clock, "Cotton 40°")
    await clock.advance(minutes=5)
    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["stock_input_unavailable"]

    corrected = await correct(panel, run["id"], "White 60°")

    assert costs(corrected)[2:] == [
        ("dose-liquid", "program_default", 70, pytest.approx(0.42)),
        ("dose-whitener", "program_default", 20, pytest.approx(0.08)),
    ]


async def test_a_stocked_dose_that_measured_nothing_used_stays_without_one(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 1000)
    await weigh_whitener(panel, washer)
    await set_program(hass, "Cotton 40°")
    await set_washer(hass, "running")
    await set_scale(hass, 1000)
    await clock.advance(minutes=90)
    await set_washer(hass, "finished")
    await set_scale(hass, 1000)
    [run] = stored_runs(hass_storage)

    corrected = await correct(panel, run["id"], "White 60°")

    assert costs(corrected)[2:] == [
        ("dose-liquid", "program_default", 70, pytest.approx(0.42)),
    ]


async def test_a_dose_whose_material_the_user_changed_stays_as_they_left_it(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "Cotton 40°")
    [run] = stored_runs(hass_storage)
    liquid = next(i for i in run["line_items"] if i.get("dose_id") == "dose-liquid")
    changed = await panel.call(
        "coinop/line_items/update",
        run_id=run["id"],
        line_item_id=liquid["id"],
        material_id="whitener",
    )
    before = next(i for i in changed["run"]["line_items"] if i["id"] == liquid["id"])

    corrected = await correct(panel, run["id"], "White 60°")

    after = next(i for i in corrected["line_items"] if i["id"] == liquid["id"])
    assert after == before
    assert (after["material_id"], after["quantity"]) == ("whitener", 60)


async def test_a_flag_marked_as_checked_is_not_raised_again(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer)
    await washed(hass, clock, "Cotton 40°", outcome="cancelled")
    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["ended_early_defaults"]
    await panel.call(
        "coinop/runs/clear_flag", run_id=run["id"], flag="ended_early_defaults"
    )

    corrected = await correct(panel, run["id"], "White 60°")

    assert corrected["flags"] == []


async def test_a_correction_raises_a_flag_it_newly_calls_for(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_rows(panel, washer, ROWS | {"default": {"doses": {}}})
    await washed(hass, clock, "Unlisted", outcome="cancelled")
    [run] = stored_runs(hass_storage)
    assert run["flags"] == ["default_missing"]
    await panel.call("coinop/runs/clear_flag", run_id=run["id"], flag="default_missing")

    corrected = await correct(panel, run["id"], "White 60°")

    assert corrected["flags"] == ["ended_early_defaults"]
