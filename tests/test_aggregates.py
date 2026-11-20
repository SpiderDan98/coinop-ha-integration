"""Totals across Runs for the Overview and Analysis, grouped any way the panel asks."""

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from .clock import CLOCK_START, Clock
from .devices import add_hub
from .stored import (
    electricity,
    line_item,
    place_materials,
    place_runs,
    stored_material,
    stored_run,
)
from .websocket import PanelClient

DAY = timedelta(days=1)


def receipt(
    started: datetime, hours: float, kwh: float, *items: dict[str, Any]
) -> list[dict[str, Any]]:
    return [electricity(kwh, 0.25, started, started + timedelta(hours=hours)), *items]


async def groups(panel: PanelClient, *group_by: str) -> Any:
    result = await panel.call("coinop/aggregates/get", group_by=list(group_by))
    return result["groups"]


async def test_without_grouping_everything_adds_up_to_one_total(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    benchy = CLOCK_START - 3 * DAY
    helmet = CLOCK_START - 2 * DAY
    place_runs(
        hass_storage,
        stored_run(
            "benchy",
            started=benchy,
            hours=2,
            line_items=receipt(
                benchy,
                2,
                0.4,
                line_item("material", 0.505, id="pla", quantity=20.2, unit="g"),
                line_item("other", 0.5, id="wear"),
            ),
        ),
        stored_run(
            "helmet",
            started=helmet,
            hours=4,
            outcome="failed",
            flags=["fault"],
            line_items=receipt(
                helmet,
                4,
                0.8,
                line_item("other", -1.0, id="refund"),
            ),
        ),
    )
    await add_hub(hass)

    [total] = await groups(panel)

    assert total == {
        "cost": 0.31,
        "electricity_cost": 0.3,
        "water_cost": 0.0,
        "material_cost": 0.51,
        "other_cost": -0.5,
        "material_grams": pytest.approx(20.2),
        "energy_kwh": pytest.approx(1.2),
        "water_litres": 0.0,
        "runs": 2,
        "running_hours": pytest.approx(6),
        "flagged_runs": 1,
    }


def pick(groups: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    return [{key: group[key] for key in keys} for group in groups]


async def test_a_run_counts_in_the_month_it_started_in_ha_time_zone(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    # 00:30 on 1 January in Berlin, still December in UTC.
    new_year = datetime.fromisoformat("2025-12-31T23:30:00+00:00")
    december = datetime.fromisoformat("2025-12-20T10:00:00+00:00")
    place_runs(
        hass_storage,
        stored_run(
            "late",
            started=december,
            line_items=receipt(
                december, 2, 0.4, line_item("material", 1.0, id="pla", unit="g")
            ),
        ),
        stored_run("over-midnight", started=new_year, hours=3),
    )
    await add_hub(hass)

    by_month = await groups(panel, "month", "kind")

    assert pick(by_month, "month", "kind", "cost", "runs") == [
        {"month": "2025-12", "kind": "electricity", "cost": 0.1, "runs": 1},
        {"month": "2025-12", "kind": "material", "cost": 1.0, "runs": 1},
        {"month": "2026-01", "kind": "electricity", "cost": 0.07, "runs": 1},
    ]


async def test_material_cost_groups_by_material(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    copy = {
        "type": "PLA",
        "density": 1.24,
        "diameter": 1.75,
        "price_per_gram": 0.02,
    }
    pla = {"material_id": "pla", "material": copy | {"name": "PLA when priced"}}
    gone = {"material_id": "gone", "material": copy | {"name": "Old PETG"}}
    place_materials(hass_storage, stored_material("pla", name="PLA Basic Black"))
    place_runs(
        hass_storage,
        stored_run(
            "vase",
            line_items=receipt(
                CLOCK_START - DAY,
                2,
                0.4,
                line_item("material", 0.4, id="a", quantity=20, unit="g", **pla),
                line_item("material", 0.2, id="b", quantity=10, unit="g", **gone),
            ),
        ),
        stored_run(
            "bowl",
            line_items=receipt(
                CLOCK_START - DAY,
                2,
                0.4,
                line_item("material", 0.6, id="a", quantity=30, unit="g", **pla),
                line_item("material", 0, id="b", quantity=None, unit="g"),
            ),
        ),
    )
    await add_hub(hass)

    by_material = await groups(panel, "kind", "material")

    assert pick(
        by_material, "kind", "material_id", "material_name", "cost", "runs"
    ) == [
        {
            "kind": "electricity",
            "material_id": None,
            "material_name": None,
            "cost": 0.2,
            "runs": 2,
        },
        {
            "kind": "material",
            "material_id": "gone",
            "material_name": "Old PETG",
            "cost": 0.2,
            "runs": 1,
        },
        {
            "kind": "material",
            "material_id": "pla",
            "material_name": "PLA Basic Black",
            "cost": 1.0,
            "runs": 2,
        },
        {
            "kind": "material",
            "material_id": None,
            "material_name": None,
            "cost": 0.0,
            "runs": 1,
        },
    ]
    assert [group["material_grams"] for group in by_material] == [0, 10, 50, 0]


async def test_a_run_counts_once_in_each_of_its_tags(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(
        hass_storage,
        stored_run("helmet", tags=["Cosplay", "Gift"], outcome="failed"),
        stored_run("vase", tags=["Gift"]),
        stored_run("hook", device_id="device-mini", device_name="Mini"),
    )
    await add_hub(hass)

    by_tag = await groups(panel, "tag")
    by_outcome = await groups(panel, "outcome")
    by_device = await groups(panel, "device")

    assert pick(by_tag, "tag", "runs", "cost") == [
        {"tag": "Cosplay", "runs": 1, "cost": 0.07},
        {"tag": "Gift", "runs": 2, "cost": 0.14},
        {"tag": None, "runs": 1, "cost": 0.07},
    ]
    assert pick(by_outcome, "outcome", "runs") == [
        {"outcome": "completed", "runs": 2},
        {"outcome": "failed", "runs": 1},
    ]
    assert pick(by_device, "device_id", "device_name", "runs") == [
        {"device_id": "device-kobra", "device_name": "Kobra", "runs": 2},
        {"device_id": "device-mini", "device_name": "Mini", "runs": 1},
    ]


async def test_runs_group_by_their_program_none_as_no_program(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    started = CLOCK_START - DAY
    rinse = receipt(started, 2, 0.24, line_item("other", 0.5, id="rinse"))
    place_runs(
        hass_storage,
        stored_run("monday", program="Cotton 60°"),
        stored_run("tuesday", program="Cotton 60°", line_items=rinse),
        stored_run("wednesday", program="Eco 40-60"),
        stored_run("thursday"),
    )
    await add_hub(hass)

    by_program = await groups(panel, "program")

    assert pick(by_program, "program", "runs", "cost") == [
        {"program": "Cotton 60°", "runs": 2, "cost": 0.63},
        {"program": "Eco 40-60", "runs": 1, "cost": 0.07},
        {"program": None, "runs": 1, "cost": 0.07},
    ]


async def test_an_open_run_counts_at_its_provisional_cost(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(
        hass_storage,
        stored_run("done"),
        stored_run(
            "printing",
            started=CLOCK_START - timedelta(hours=1),
            ended=False,
            line_items=[line_item("electricity", 0.05, method="estimated")],
        ),
    )
    await add_hub(hass)

    by_outcome = await groups(panel, "outcome")

    assert pick(by_outcome, "outcome", "cost", "runs") == [
        {"outcome": "completed", "cost": 0.07, "runs": 1},
        {"outcome": None, "cost": 0.05, "runs": 1},
    ]
    assert by_outcome[1]["running_hours"] == pytest.approx(1)


async def test_without_runs_there_are_no_groups(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    assert await groups(panel) == []
    assert await groups(panel, "month") == []


async def test_only_known_dimensions_group(
    hass: HomeAssistant, clock: Clock, panel: PanelClient
) -> None:
    await add_hub(hass)

    unknown = await panel.error("coinop/aggregates/get", group_by=["colour"])
    twice = await panel.error("coinop/aggregates/get", group_by=["tag", "tag"])

    assert (unknown["code"], twice["code"]) == ("invalid_format", "invalid_format")


async def test_totals_of_only_some_runs(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """The basket, the gallery's filtered Runs, failed and cancelled Runs."""
    place_runs(
        hass_storage,
        stored_run("helmet", outcome="failed"),
        stored_run("vase"),
        stored_run("hook", outcome="cancelled"),
    )
    await add_hub(hass)

    result = await panel.call(
        "coinop/aggregates/get", run_ids=["helmet", "hook", "gone"]
    )
    none = await panel.call("coinop/aggregates/get", run_ids=[])

    assert pick(result["groups"], "cost", "runs") == [{"cost": 0.14, "runs": 2}]
    assert none["groups"] == []


async def test_totals_of_only_some_materials(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    """The Materials the Overview's chart sums up as "other materials"."""
    used = {"quantity": 10, "unit": "g"}
    place_runs(
        hass_storage,
        stored_run(
            "vase",
            line_items=receipt(
                CLOCK_START - DAY,
                2,
                0.4,
                line_item("material", 0.4, id="a", material_id="pla", **used),
                line_item("material", 0.2, id="b", material_id="petg", **used),
                line_item("material", 0.1, id="c", material_id="tpu", **used),
                line_item("material", 0.05, id="d", **used),
            ),
        ),
    )
    await add_hub(hass)

    result = await panel.call(
        "coinop/aggregates/get", group_by=["kind"], material_ids=["petg", None]
    )

    assert pick(result["groups"], "kind", "cost", "material_grams") == [
        {"kind": "electricity", "cost": 0.1, "material_grams": 0},
        {"kind": "material", "cost": 0.25, "material_grams": 20},
    ]
