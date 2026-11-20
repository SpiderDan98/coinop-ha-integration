"""Manual Runs take their electricity from recorder history while it covers the Run."""

from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.typing import RecorderInstanceGenerator

from .clock import CLOCK_START, Clock
from .devices import ENERGY, POWER, add_device, add_hub, add_washing_machine
from .test_dynamic_price import PRICE_ENTITY, segments, set_price
from .test_manual_runs import at, create
from .test_measured import add_metered_device, electricity, set_meter
from .test_runs import NO_MATERIAL
from .test_washing_machines import set_energy
from .test_water import set_water, water
from .websocket import PanelClient


@pytest.fixture
async def mock_recorder_before_hass(
    async_setup_recorder_instance: RecorderInstanceGenerator,
) -> None:
    """Set the recorder up before `hass`, as the recorder fixtures require."""


@pytest.fixture(autouse=True)
async def recorder(
    hass: HomeAssistant,
    clock: Clock,
    async_setup_recorder_instance: RecorderInstanceGenerator,
) -> None:
    """Recording from `CLOCK_START` on."""
    await async_setup_recorder_instance(hass)


async def history_until(hass: HomeAssistant, clock: Clock, hours: float) -> None:
    await async_wait_recording_done(hass)
    await clock.move_to(CLOCK_START + timedelta(hours=hours))


async def test_an_energy_meters_history_is_interpolated_at_start_and_end(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    [device] = entry.subentries.values()
    await clock.advance(minutes=30)
    await set_meter(hass, 10.1)
    await clock.advance(hours=1)
    await set_meter(hass, 10.3)
    await clock.advance(hours=1)
    await set_meter(hass, 10.4)
    await history_until(hass, clock, 5)

    run = await create(panel, device.subentry_id, started=at(0.75), ended=at(2))

    item = electricity(run)
    assert item["method"] == "from_history"
    # 10.15 at 10:45, 10.35 at 12:00.
    assert item["quantity"] == pytest.approx(0.2)
    assert item["amount"] == pytest.approx(0.06)
    assert run["flags"] == NO_MATERIAL


async def test_a_power_sensors_history_is_integrated_over_the_run(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_meter(hass, 100, entity=POWER, unit="W")
    entry = await add_metered_device(hass, "power")
    [device] = entry.subentries.values()
    await clock.advance(hours=1)
    await set_meter(hass, 300, entity=POWER, unit="W")
    await clock.advance(hours=2)
    await set_meter(hass, 0, entity=POWER, unit="W")
    await history_until(hass, clock, 5)

    run = await create(panel, device.subentry_id, started=at(0.5), ended=at(2))

    item = electricity(run)
    assert item["method"] == "from_history"
    assert item["quantity"] == pytest.approx(0.05 + 0.3)


async def test_the_price_entitys_history_splits_the_run_at_each_price_change(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_price(hass, 0.20)
    await set_meter(hass, 10.0)
    entry = await add_hub(hass)
    device = await add_device(
        hass, entry, source="energy", meter={"entity_id": ENERGY}, price=PRICE_ENTITY
    )
    await clock.advance(hours=1)
    await set_price(hass, 0.40)
    await set_meter(hass, 10.2)
    await clock.advance(hours=1)
    await set_meter(hass, 10.4)
    await history_until(hass, clock, 5)

    run = await create(panel, device.subentry_id, started=at(0.5), ended=at(1.5))

    assert segments(run) == [
        (at(0.5), at(1), 0.1, 0.20),
        (at(1), at(1.5), 0.1, 0.40),
    ]
    assert electricity(run)["amount"] == pytest.approx(0.06)
    assert run["flags"] == NO_MATERIAL


async def test_history_needs_a_meter_reading_at_the_runs_start(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_meter(hass, 10.0)
    entry = await add_metered_device(hass)
    [device] = entry.subentries.values()
    await set_meter(hass, STATE_UNAVAILABLE)
    await clock.advance(hours=1)
    await set_meter(hass, 10.1)
    await clock.advance(hours=1)
    await set_meter(hass, 10.2)
    await history_until(hass, clock, 5)

    run = await create(panel, device.subentry_id, started=at(0.5), ended=at(2))

    assert electricity(run)["method"] == "entered"


async def test_a_print_made_while_home_assistant_was_down_is_estimated(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    # States timed before the recorder started stand in for those around a downtime.
    await clock.move_to(CLOCK_START - timedelta(hours=4))
    await set_price(hass, 0.25)
    await set_meter(hass, 0, entity=POWER, unit="W")
    entry = await add_hub(hass)
    device = await add_device(
        hass,
        entry,
        source="power",
        meter={"entity_id": POWER, "running_power": 50},
        price=PRICE_ENTITY,
    )
    await clock.advance(hours=3)
    await set_meter(hass, 0, entity=POWER, unit="W")
    await history_until(hass, clock, 1)

    run = await create(panel, device.subentry_id, started=at(-3.5), ended=at(-2.5))

    item = electricity(run)
    assert item["method"] == "estimated"
    assert item["quantity"] == pytest.approx(0.05)
    assert item["unit_price"] == pytest.approx(0.25)
    assert run["flags"] == ["price_gap", *NO_MATERIAL]


async def test_a_manual_wash_takes_its_water_from_history(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_water(hass, 1000)
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    washer = await add_washing_machine(hass, entry, water="meter", water_price=4.0)
    await clock.advance(hours=1)
    await set_water(hass, 1040)
    await clock.advance(hours=1)
    await set_water(hass, 1060)
    await history_until(hass, clock, 5)

    run = await create(panel, washer.subentry_id, started=at(0.5), ended=at(1.5))

    item = water(run)
    assert item["method"] == "from_history"
    # 1020 at 10:30, 1050 at 11:30.
    assert item["quantity"] == pytest.approx(30)
    assert item["amount"] == pytest.approx(0.12)


async def test_without_water_history_a_manual_wash_gets_water_to_enter(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_water(hass, 1000)
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    washer = await add_washing_machine(hass, entry, water="meter")
    await history_until(hass, clock, 5)

    run = await create(panel, washer.subentry_id, started=at(-3), ended=at(-2))

    item = water(run)
    assert (item["method"], item["quantity"], item["deletable"]) == (
        "entered",
        None,
        True,
    )


async def test_a_manual_wash_without_a_water_source_has_no_water(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await set_energy(hass, 100)
    entry = await add_hub(hass)
    washer = await add_washing_machine(hass, entry)
    await history_until(hass, clock, 5)

    run = await create(panel, washer.subentry_id, started=at(1), ended=at(2))

    assert [item["kind"] for item in run["line_items"]] == ["electricity"]
