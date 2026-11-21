"""Parity: what an Other Device has decides how its Runs are costed, never its Device
Type's name. A shipped Device Type and an Other Device with the same mix follow the
same entities here, so every state reaches both, and their Runs must come out alike."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import (
    WASHER_ENERGY,
    WASHER_MAPPING,
    WASHER_STATUS,
    WASHER_WATER,
    add_hub,
    add_other_device,
    add_washing_machine,
)
from .stored import place_materials
from .test_doses import SCALE, set_scale
from .test_manual_runs import create
from .test_program_consumption import approx
from .test_program_correction import costs
from .test_run_event import record_events
from .test_runs import stored_runs
from .test_water import set_water
from .washing import (
    DOSES,
    LIQUID,
    PODS,
    WASHER_PROGRAM,
    WHITENER,
    set_energy,
    set_program,
)
from .websocket import PanelClient

# What tells one Device's Run, Line Item or event from another's.
IDENTITY = frozenset({"id", "run_id", "device_id", "device_name", "friendly_name"})


def likeness(value: Any) -> Any:
    """`value` without what names the Device or one of its Runs or Line Items."""
    if isinstance(value, dict):
        return {k: likeness(v) for k, v in value.items() if k not in IDENTITY}
    if isinstance(value, list):
        return [likeness(item) for item in value]
    return value


async def runs_of(
    panel: PanelClient, hass_storage: dict[str, Any], device: ConfigSubentry
) -> dict[str, list[dict[str, Any]]]:
    """The Device's Runs, oldest first, as they are stored and as the panel gets
    them."""
    listed = (await panel.call("coinop/runs/list"))["runs"]
    ids = sorted(
        (run["started"], run["id"])
        for run in listed
        if run["device_id"] == device.subentry_id
    )
    return {
        "stored": [
            run
            for run in stored_runs(hass_storage)
            if run["device_id"] == device.subentry_id
        ],
        "panel": [
            (await panel.call("coinop/runs/get", run_id=run_id))["run"]
            for _, run_id in ids
        ],
    }


# 0.30 per kWh, 4.00 per m³; 0.006 per ml of liquid, 0.30 per pod, 0.004 per g of
# whitener.
ROWS = {
    "default": {
        "doses": {"dose-liquid": 60, "dose-pods": 1, "dose-whitener": 20},
        "kwh": 0.8,
    },
    "programs": {
        "Cotton 60°": {
            "doses": {"dose-liquid": 75, "dose-whitener": 25},
            "kwh": 1.5,
            "litres": 60,
        },
    },
}
# The whitener's Dose is weighed by its stock input.
WEIGHED = [*DOSES[:2], DOSES[2] | {"stock": {"entity_id": SCALE}}]
METERED = {"source": "energy", "water": "meter"}
PER_PROGRAM = {"source": "per_program", "water": "per_program"}

TWIN_STATUS = "sensor.carpet_cleaner_status"

type Twins = tuple[ConfigSubentry, ConfigSubentry]


async def set_twins(hass: HomeAssistant, status: str) -> None:
    """Both Devices' Status at once: the one entity no two Devices can share."""
    for entity_id in (WASHER_STATUS, TWIN_STATUS):
        hass.states.async_set(entity_id, status)
    await hass.async_block_till_done()


async def add_washer_twins(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    *,
    source: str,
    water: str,
    doses: list[dict[str, Any]],
) -> Twins:
    """A washing machine ("Washer") and an Other Device that has what a washing
    machine has ("Carpet cleaner": Program, Doses, water and meters that count each
    Run from 0), both off, on the same Program, energy, water and stock entities,
    with the same Dose list `doses` and the Program Defaults `ROWS`. Their Status
    entities are set together with `set_twins`."""
    hass.config.currency = "EUR"
    place_materials(hass_storage, LIQUID, PODS, WHITENER)
    await set_energy(hass, 100)
    await set_water(hass, 1000)
    await set_scale(hass, 500)
    await set_twins(hass, "off")
    await set_program(hass, "unknown")
    entry = await add_hub(hass)
    inputs: dict[str, Any] = {
        "program": {"entity_id": WASHER_PROGRAM},
        "source": source,
        "meter": {"entity_id": WASHER_ENERGY},
        "water": water,
        "water_meter": {"entity_id": WASHER_WATER},
    }
    twins = (
        await add_washing_machine(hass, entry, **inputs),
        await add_other_device(
            hass,
            entry,
            type_name="Carpet cleaner",
            name="Carpet cleaner",
            status=TWIN_STATUS,
            mapping=WASHER_MAPPING,
            has=["program", "doses", "water", "per_run_meters"],
            **inputs,
        ),
    )
    for twin in twins:
        await panel.call(
            "coinop/devices/update_settings",
            device_id=twin.subentry_id,
            settings={"doses": doses, "program_defaults": ROWS},
        )
    return twins


async def a_measured_load(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, twins: Twins
) -> None:
    """On a Program with a row; the meters and the stock input report its end."""
    await set_program(hass, "Cotton 60°")
    await set_twins(hass, "running")
    await clock.advance(minutes=45)
    await set_scale(hass, 480)
    await clock.advance(minutes=45)
    for status in ("finished", "off"):
        await set_energy(hass, 101.2)
        await set_water(hass, 1050)
        await set_scale(hass, 480)
        await set_twins(hass, status)
    # Older Home Assistant needs a second pass for the Run event's listeners.
    await hass.async_block_till_done()


async def a_cancelled_load_nothing_measured(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, twins: Twins
) -> None:
    """On a Program without a row, while the meters and the stock input are
    unavailable."""
    await set_energy(hass, STATE_UNAVAILABLE)
    await set_water(hass, STATE_UNAVAILABLE)
    await set_scale(hass, STATE_UNAVAILABLE)
    await set_program(hass, "Eco 40-60")
    await set_twins(hass, "running")
    await clock.advance(minutes=20)
    await set_twins(hass, "cancelled")
    await clock.advance(minutes=5)


async def two_loads_counted_from_0(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, twins: Twins
) -> None:
    """Both meters count each load from 0 and drop back to 0 ten seconds after it."""
    for kwh, litres in ((0.9, 45), (1.1, 55)):
        await set_energy(hass, 0)
        await set_water(hass, 0)
        await set_twins(hass, "running")
        await clock.advance(minutes=90)
        await set_energy(hass, kwh)
        await set_water(hass, litres)
        await clock.advance(minutes=1)
        await set_twins(hass, "finished")
        await clock.advance(seconds=10)
        await set_energy(hass, 0)
        await set_water(hass, 0)
        await clock.advance(hours=20)


async def a_load_whose_program_is_corrected(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, twins: Twins
) -> None:
    """On a Program without a row, corrected to one with a row once it ended."""
    await set_program(hass, "Eco 40-60")
    await set_twins(hass, "running")
    await clock.advance(minutes=90)
    await set_twins(hass, "finished")
    await hass.async_block_till_done()
    for run in (await panel.call("coinop/runs/list"))["runs"]:
        await panel.call("coinop/runs/update", run_id=run["id"], program="Cotton 60°")


async def a_manual_run_on_a_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, twins: Twins
) -> None:
    await clock.advance(hours=5)
    for twin in twins:
        await create(panel, twin.subentry_id, name=None, program="Cotton 60°")


PROGRAMMED = [
    ("electricity", "program_default", 1.5, 0.45),
    ("water", "program_default", 60, 0.24),
    ("dose-liquid", "program_default", 75, 0.45),
    ("dose-whitener", "program_default", 25, 0.10),
]
DEFAULT_DOSES = [
    ("dose-liquid", "default_row", 60, 0.36),
    ("dose-pods", "default_row", 1, 0.30),
    ("dose-whitener", "default_row", 20, 0.08),
]


@pytest.mark.parametrize(
    ("sources", "doses", "scenario", "flags", "expected", "fired"),
    [
        pytest.param(
            METERED,
            WEIGHED,
            a_measured_load,
            [[]],
            [
                [
                    ("electricity", "measured", 1.2, 0.36),
                    ("water", "measured", 50, 0.20),
                    ("dose-liquid", "program_default", 75, 0.45),
                    ("dose-whitener", "stock_input", 20, 0.08),
                ]
            ],
            ["started", "ended"],
            id="a measured load",
        ),
        pytest.param(
            METERED,
            WEIGHED,
            a_cancelled_load_nothing_measured,
            [
                [
                    "consumption_gap",
                    "default_missing",
                    "ended_early_defaults",
                    "stock_input_unavailable",
                ]
            ],
            [
                [
                    ("electricity", "program_default", 0.8, 0.24),
                    ("water", "program_default", None, 0),
                    *DEFAULT_DOSES,
                ]
            ],
            ["started", "ended"],
            id="a cancelled load, nothing measured",
        ),
        pytest.param(
            METERED,
            DOSES,
            two_loads_counted_from_0,
            [[], []],
            [
                [
                    ("electricity", "measured", 0.9, 0.27),
                    ("water", "measured", 45, 0.18),
                    *DEFAULT_DOSES,
                ],
                [
                    ("electricity", "measured", 1.1, 0.33),
                    ("water", "measured", 55, 0.22),
                    *DEFAULT_DOSES,
                ],
            ],
            ["started", "ended", "started", "ended"],
            id="two loads counted from 0",
        ),
        pytest.param(
            PER_PROGRAM,
            DOSES,
            a_load_whose_program_is_corrected,
            [[]],
            [PROGRAMMED],
            ["started", "ended"],
            id="a load whose Program is corrected",
        ),
        pytest.param(
            PER_PROGRAM,
            DOSES,
            a_manual_run_on_a_program,
            [[]],
            [PROGRAMMED],
            [],
            id="a manual Run on a Program",
        ),
    ],
)
async def test_an_other_device_with_what_a_washing_machine_has_costs_a_run_like_one(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    sources: dict[str, str],
    doses: list[dict[str, Any]],
    scenario: Callable[[HomeAssistant, Clock, PanelClient, Twins], Awaitable[None]],
    flags: list[list[str]],
    expected: list[list[tuple[Any, ...]]],
    fired: list[str],
) -> None:
    twins = await add_washer_twins(hass, hass_storage, panel, **sources, doses=doses)
    washer, carpet_cleaner = twins
    washer_events, carpet_cleaner_events = (
        record_events(hass, f"event.{slug}_run")
        for slug in ("washer", "carpet_cleaner")
    )

    await scenario(hass, clock, panel, twins)

    washed = await runs_of(panel, hass_storage, washer)
    assert [sorted(run["flags"]) for run in washed["stored"]] == flags
    assert [approx(costs(run)) for run in washed["stored"]] == expected
    assert len(washed["panel"]) == len(expected)
    assert [event["event_type"] for event in washer_events] == fired
    cleaned = await runs_of(panel, hass_storage, carpet_cleaner)
    assert likeness(cleaned) == likeness(washed)
    assert likeness(carpet_cleaner_events) == likeness(washer_events)
