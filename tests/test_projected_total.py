"""Projected Total: an open Run's cost so far plus the rest still to come."""

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
import pytest

from .clock import Clock
from .devices import ENERGY, add_device, add_hub
from .test_ev_chargers import add_charger, set_charger, set_session
from .stored import place_materials, stored_material
from .test_material_usage import GRAMS_PER_METRE, add_measuring_device, set_usage
from .test_measured import set_meter
from .test_program_consumption import set_rows
from .test_runs import set_status, stored_runs
from .test_templates import WEAR, add_template, create
from .test_water import set_water
from .washing import add_washer, set_energy, set_program, set_washer
from .websocket import PanelClient

REMAINING = "sensor.kobra_time_remaining"
PROGRESS = "sensor.kobra_progress"
PROJECTED = "sensor.kobra_projected_run_cost"


async def set_remaining(hass: HomeAssistant, minutes: float | str) -> None:
    hass.states.async_set(REMAINING, str(minutes), {"unit_of_measurement": "min"})
    await hass.async_block_till_done()


def projected(hass: HomeAssistant, entity_id: str = PROJECTED) -> State:
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def add_metered_printer(hass: HomeAssistant, **options: Any) -> None:
    await set_meter(hass, 10.0)
    entry = await add_hub(hass)
    await add_device(
        hass,
        entry,
        source="energy",
        meter={"entity_id": ENERGY},
        price=0.30,
        remaining_time=REMAINING,
        **options,
    )


async def preheat_then_print(hass: HomeAssistant, clock: Clock) -> None:
    """40 minutes at 600 W heating up, then 40 at 150 W: 0.5 kWh so far."""
    await set_status(hass, "printing")
    for kwh in (0.1, 0.2, 0.3, 0.4, 0.425, 0.45, 0.475, 0.5):
        await clock.advance(minutes=10)
        await set_meter(hass, 10.0 + kwh)


async def test_a_metered_run_projects_its_rest_from_the_last_half_hours_power(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_metered_printer(hass)
    assert projected(hass).state == STATE_UNKNOWN

    await preheat_then_print(hass, clock)
    await set_remaining(hass, 120)

    # 0.15 so far, and 2 h at 150 W: 0.3 kWh at 0.30, not the preheat's average.
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.24)
    assert state.attributes["ends_at"] == clock.now() + timedelta(hours=2)
    assert state.attributes["unit_of_measurement"] == "EUR"
    assert state.attributes["device_class"] == "monetary"


async def test_a_preheat_in_the_last_half_hour_still_counts(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_metered_printer(hass)
    await set_status(hass, "printing")
    await clock.advance(minutes=20)
    await set_meter(hass, 10.2)
    await set_remaining(hass, 60)

    # Less than half an hour ran: its own 600 W, for 1 h at 0.30.
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.18)


async def test_a_device_on_average_powers_projects_its_running_power(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass, entry, running_power=200, price=0.30, remaining_time=REMAINING
    )
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_remaining(hass, 90)

    # 0.03 so far, and 1.5 h at 200 W.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)


async def test_running_hours_line_items_add_their_rate_over_the_time_left(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, source="none", remaining_time=REMAINING)
    await set_status(hass, "printing")
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    await add_template(panel, run["id"], await create(panel, **WEAR))
    await clock.advance(hours=1)
    await set_remaining(hass, 120)

    # 1 h of wear at 0.15 so far, 2 h to come.
    assert float(projected(hass).state) == pytest.approx(0.15 + 0.30)


async def test_without_a_time_left_or_anything_to_project_there_is_no_value(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, source="none", remaining_time=REMAINING)
    await set_status(hass, "printing")
    await clock.advance(minutes=10)
    assert projected(hass).state == STATE_UNKNOWN

    await set_remaining(hass, 30)
    assert projected(hass).state == STATE_UNKNOWN
    assert "ends_at" not in projected(hass).attributes


async def test_the_projection_follows_the_time_left_and_ends_with_the_run(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> None:
    entry = await add_hub(hass)
    await add_device(
        hass, entry, running_power=200, price=0.30, remaining_time=REMAINING
    )
    await set_remaining(hass, STATE_UNKNOWN)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    assert projected(hass).state == STATE_UNKNOWN

    await set_remaining(hass, 30)
    assert float(projected(hass).state) == pytest.approx(0.06)
    await clock.advance(minutes=30)
    await set_remaining(hass, 0)
    assert float(projected(hass).state) == pytest.approx(0.06)

    await set_status(hass, "finished")
    assert projected(hass).state == STATE_UNKNOWN
    assert "ends_at" not in projected(hass).attributes
    [run] = stored_runs(hass_storage)
    assert not any("project" in key for key in run)


async def test_the_panel_gets_the_projected_total_its_end_and_what_it_includes(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_metered_printer(hass)
    await preheat_then_print(hass, clock)
    await set_remaining(hass, 120)
    ends = (clock.now() + timedelta(hours=2)).isoformat()

    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    assert (summary["projected_total"], summary["projected_end"]) == (0.24, ends)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert (run["projected_total"], run["projected_end"]) == (0.24, ends)
    assert run["projected_parts"] == ["electricity"]

    await add_template(panel, run["id"], await create(panel, **WEAR))
    await clock.advance(minutes=1)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_parts"] == ["electricity", "running_hours"]

    await set_status(hass, "finished")
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert (run["projected_total"], run["projected_end"]) == (None, None)
    assert run["projected_parts"] == []
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    assert (summary["projected_total"], summary["projected_end"]) == (None, None)


async def add_timed_printer(
    hass: HomeAssistant, remaining_time: str | None = None, progress: str | None = None
) -> None:
    """200 W on average powers, none while paused, at 0.30 per kWh: 0.06 an hour."""
    entry = await add_hub(hass)
    await add_device(
        hass,
        entry,
        running_power=200,
        paused_power=0,
        price=0.30,
        remaining_time=remaining_time,
        progress=progress,
    )


@pytest.mark.parametrize(
    ("value", "unit"),
    [("1.5", "h"), ("90", "min"), ("5400", "s"), ("5400000", "ms"), ("90", None)],
)
async def test_a_remaining_time_counts_in_the_unit_it_reports(
    hass: HomeAssistant, clock: Clock, value: str, unit: str | None
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    attributes = {"unit_of_measurement": unit} if unit else {}
    hass.states.async_set(REMAINING, value, attributes)
    await hass.async_block_till_done()

    # 0.03 so far, and 1.5 h at 200 W.
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.03 + 0.09)
    assert state.attributes["ends_at"] == clock.now() + timedelta(minutes=90)


async def test_a_finish_timestamp_leaves_the_time_until_it(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    finish = clock.now() + timedelta(hours=1)
    hass.states.async_set(REMAINING, finish.isoformat(), {"device_class": "timestamp"})
    await hass.async_block_till_done()

    state = projected(hass)
    assert float(state.state) == pytest.approx(0.03 + 0.06)
    assert state.attributes["ends_at"] == finish

    await clock.advance(minutes=30)
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.06 + 0.03)
    assert state.attributes["ends_at"] == finish

    await clock.advance(minutes=40)
    # Past its finish, the rest is nothing more.
    assert float(projected(hass).state) == pytest.approx(0.10)


async def set_progress(hass: HomeAssistant, percent: float | str) -> None:
    hass.states.async_set(PROGRESS, str(percent), {"unit_of_measurement": "%"})
    await hass.async_block_till_done()


async def test_with_only_progress_the_time_left_follows_the_running_time(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, progress=PROGRESS)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_progress(hass, 4)
    assert projected(hass).state == STATE_UNKNOWN

    await set_progress(hass, 5)
    # 30 minutes for 5 %: 570 more for the other 95, at 200 W.
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.03 + 0.57)
    assert state.attributes["ends_at"] == clock.now() + timedelta(minutes=570)

    await clock.advance(minutes=30)
    await set_progress(hass, 50)
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.06)


async def test_a_remaining_time_comes_before_the_progress(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING, progress=PROGRESS)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_progress(hass, 25)
    await set_remaining(hass, STATE_UNKNOWN)
    # Without a remaining time, 30 minutes for 25 %: 90 more.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)

    await set_remaining(hass, 30)
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.03)


@pytest.mark.parametrize("dropped", ["0", STATE_UNKNOWN])
async def test_a_pause_holds_the_time_left_from_before_it(
    hass: HomeAssistant, clock: Clock, dropped: str
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    await set_status(hass, "printing")
    await set_remaining(hass, 90)
    await clock.advance(minutes=30)
    await set_remaining(hass, 60)
    await clock.advance(seconds=10)

    await set_status(hass, "paused")
    await set_remaining(hass, dropped)
    await clock.advance(minutes=20)
    state = projected(hass)
    assert float(state.state) == pytest.approx(0.03 + 0.06)
    assert state.attributes["ends_at"] == clock.now() + timedelta(minutes=60)

    await set_status(hass, "printing")
    await set_remaining(hass, 50)
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.05)


async def test_a_time_left_dropped_right_before_the_pause_is_still_held(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    await set_status(hass, "printing")
    await set_remaining(hass, 90)
    await clock.advance(minutes=30)

    # The integration wrote its time left a moment before its Status.
    await set_remaining(hass, 0)
    await set_status(hass, "paused")
    await set_remaining(hass, STATE_UNKNOWN)

    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)


async def test_a_held_finish_time_leaves_the_time_from_the_pauses_start(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, remaining_time=REMAINING)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    finish = clock.now() + timedelta(hours=1)
    hass.states.async_set(REMAINING, finish.isoformat(), {"device_class": "timestamp"})
    await clock.advance(minutes=10)

    await set_status(hass, "paused")
    await set_remaining(hass, STATE_UNKNOWN)
    await clock.advance(minutes=20)

    state = projected(hass)
    assert float(state.state) == pytest.approx(0.04 + 0.05)
    assert state.attributes["ends_at"] == clock.now() + timedelta(minutes=50)


async def test_a_pause_holds_the_time_left_from_the_progress(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_timed_printer(hass, progress=PROGRESS)
    await set_status(hass, "printing")
    await clock.advance(minutes=29)
    await set_progress(hass, 25)
    await clock.advance(minutes=1)

    await set_status(hass, "paused")
    await set_progress(hass, 0)
    await clock.advance(minutes=20)

    # 30 minutes for 25 %, the pause not counted: 90 more.
    assert float(projected(hass).state) == pytest.approx(0.03 + 0.09)

    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_progress(hass, 50)
    assert float(projected(hass).state) == pytest.approx(0.06 + 0.06)


TO_CHARGE = "sensor.wallbox_energy_to_charge"
CHARGER_PROJECTED = "sensor.wallbox_projected_run_cost"
STILL_TO_COME = {"expected_energy": TO_CHARGE, "expected_energy_form": "remaining"}
SESSION_TOTAL = {"expected_energy": TO_CHARGE, "expected_energy_form": "total"}


async def set_expected(
    hass: HomeAssistant, value: float | str, unit: str = "kWh"
) -> None:
    hass.states.async_set(TO_CHARGE, str(value), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def test_energy_still_to_come_projects_without_a_time_left(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_expected(hass, 20)
    await add_charger(hass, expected_energy=STILL_TO_COME)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, 5)
    await set_expected(hass, 15)

    # 5 kWh so far and 15 to come, at 0.30.
    state = projected(hass, CHARGER_PROJECTED)
    assert float(state.state) == pytest.approx(1.50 + 4.50)
    assert state.attributes["ends_at"] is None
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    assert (summary["projected_total"], summary["projected_end"]) == (6.0, None)
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_parts"] == ["electricity"]

    await set_expected(hass, 2500, "Wh")
    assert float(projected(hass, CHARGER_PROJECTED).state) == pytest.approx(1.50 + 0.75)


async def test_the_runs_total_energy_leaves_what_was_measured_and_comes_first(
    hass: HomeAssistant, clock: Clock
) -> None:
    await set_expected(hass, STATE_UNKNOWN)
    await add_charger(hass, remaining_time=REMAINING, expected_energy=SESSION_TOTAL)
    await set_charger(hass, "charging")
    await clock.advance(hours=1)
    await set_session(hass, 5)
    await set_remaining(hass, 60)
    # Without the total: 5 kW for the hour left.
    assert float(projected(hass, CHARGER_PROJECTED).state) == pytest.approx(3.00)

    await set_expected(hass, 12)
    # 5 kWh so far and the 7 the total leaves, not 5 kW for the hour left.
    state = projected(hass, CHARGER_PROJECTED)
    assert float(state.state) == pytest.approx(1.50 + 2.10)
    assert state.attributes["ends_at"] == clock.now() + timedelta(hours=1)

    await set_expected(hass, 4)
    assert float(projected(hass, CHARGER_PROJECTED).state) == pytest.approx(1.50)


WASHER_REMAINING = "sensor.washer_time_left"
WASHER_PROJECTED = "sensor.washer_projected_run_cost"


async def heat_up(hass: HomeAssistant, clock: Clock, program: str, kwh: float) -> None:
    """A load of `program` that drew `kwh` in its first 20 minutes, an hour to go."""
    await set_program(hass, program)
    await set_washer(hass, "running")
    await clock.advance(minutes=20)
    await set_energy(hass, 100 + kwh)
    hass.states.async_set(WASHER_REMAINING, "60", {"unit_of_measurement": "min"})
    await hass.async_block_till_done()


async def test_a_metered_appliance_projects_what_its_programs_default_leaves(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    washer = await add_washer(hass, remaining_time=WASHER_REMAINING)
    await set_rows(panel, washer)
    await heat_up(hass, clock, "Cotton 60°", 0.9)

    # 0.9 kWh of Cotton's 1.5 so far, not the heating's 2.7 kW for the hour left.
    state = projected(hass, WASHER_PROJECTED)
    assert float(state.state) == pytest.approx(0.27 + 0.18)
    assert state.attributes["ends_at"] == clock.now() + timedelta(hours=1)


async def test_measured_above_the_programs_default_leaves_nothing_to_come(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    washer = await add_washer(hass)
    await set_rows(panel, washer)
    await heat_up(hass, clock, "Eco 40-60", 0.9)

    # Past the Default row's 0.8 kWh: the cost so far, with no time left needed.
    state = projected(hass, WASHER_PROJECTED)
    assert float(state.state) == pytest.approx(0.27)
    assert state.attributes["ends_at"] is None
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_parts"] == ["electricity"]


async def test_a_measured_waters_rest_is_what_the_programs_litres_leave(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_water(hass, 1000)
    washer = await add_washer(hass, water="meter")
    await set_rows(panel, washer)
    await heat_up(hass, clock, "Cotton 60°", 0.9)
    await set_water(hass, 1020)

    # 20 of Cotton's 60 L so far at 4.00 per m³: 0.08, and 0.16 to come.
    state = projected(hass, WASHER_PROJECTED)
    assert float(state.state) == pytest.approx(0.27 + 0.18 + 0.08 + 0.16)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_parts"] == ["electricity", "water"]

    await clock.advance(minutes=5)
    await set_water(hass, 1070)
    assert float(projected(hass, WASHER_PROJECTED).state) == pytest.approx(
        0.27 + 0.18 + 0.28
    )


async def test_an_appliance_without_program_defaults_projects_its_recent_power(
    hass: HomeAssistant, clock: Clock
) -> None:
    await add_washer(hass, remaining_time=WASHER_REMAINING)
    await heat_up(hass, clock, "Cotton 60°", 0.9)

    # No kWh in its Program Defaults: its 2.7 kW for the hour left.
    assert float(projected(hass, WASHER_PROJECTED).state) == pytest.approx(0.27 + 0.81)


async def test_an_appliance_costed_by_its_program_defaults_alone_projects_nothing(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    washer = await add_washer(
        hass,
        source="per_program",
        water="per_program",
        remaining_time=WASHER_REMAINING,
    )
    await set_rows(panel, washer)
    await heat_up(hass, clock, "Cotton 60°", 0.9)

    # Its cost so far is already the Program's whole kWh and litres.
    assert projected(hass, WASHER_PROJECTED).state == STATE_UNKNOWN
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    assert (summary["projected_total"], summary["projected_end"]) == (None, None)


PLANNED = "sensor.kobra_planned_filament"


async def set_planned(hass: HomeAssistant, planned: float | str, unit: str = "g") -> None:
    hass.states.async_set(PLANNED, str(planned), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def add_planning_printer(
    hass: HomeAssistant, panel: PanelClient, hass_storage: dict[str, Any], **inputs: Any
) -> None:
    """Material used in mm and nothing else to cost, on the default PLA at 0.02 a gram."""
    place_materials(hass_storage, stored_material("pla"))
    await add_measuring_device(hass, panel, source="none", **inputs)


async def test_a_planned_mass_leaves_what_the_measured_length_weighs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await set_planned(hass, 50)
    await add_planning_printer(hass, panel, hass_storage, planned_material=PLANNED)
    await set_status(hass, "printing")
    await clock.advance(minutes=30)
    await set_usage(hass, 1000)

    # 1 m weighs 2.98 g of the 50 planned: 0.06 so far, 0.94 to come.
    assert float(projected(hass).state) == pytest.approx(1.00)
    [summary] = (await panel.call("coinop/runs/list"))["runs"]
    run = (await panel.call("coinop/runs/get", run_id=summary["id"]))["run"]
    assert run["projected_parts"] == ["material"]

    # Past the plan, nothing more is to come.
    await set_usage(hass, 20000)
    assert float(projected(hass).state) == pytest.approx(
        round(20 * GRAMS_PER_METRE * 0.02, 2)
    )
