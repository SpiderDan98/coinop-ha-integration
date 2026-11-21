"""Doses: a washing machine's Material Line Items from its Program Defaults."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .http import HttpClient
from .stored import place_materials, stored_material
from .test_cost_statement import export
from .test_persistence import restart
from .test_runs import stored_runs, value
from .test_washing_machines import washer_entry
from .washing import (
    DOSES,
    add_washer,
    set_energy,
    set_washer,
    washed,
)
from .websocket import PanelClient


@pytest.fixture
async def washer(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> ConfigSubentry:
    """A washing machine on a plug's energy meter, with the laundry Materials."""
    return await add_washer(hass, hass_storage, program=False, price=0.50)


async def dose(
    panel: PanelClient, washer: ConfigSubentry, default: dict[str, float]
) -> Any:
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES, "program_defaults": {"default": {"doses": default}}},
    )
    return result["settings"]


def doses(run: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            item["dose_id"],
            item["dose_source"],
            item["material_id"],
            item["quantity"],
            item["unit"],
            pytest.approx(item["unit_price"]),
            pytest.approx(item["amount"]),
        )
        for item in run["line_items"]
        if item["kind"] == "material"
    ]


async def test_each_dose_of_the_default_row_is_a_material_line_item(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await dose(panel, washer, {"dose-liquid": 75, "dose-pods": 1})

    await washed(hass, clock, kwh=1.2)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-liquid", "default_row", "liquid", 75, "ml", 0.006, 0.45),
        ("dose-pods", "default_row", "pods", 1, "pcs", 0.30, 0.30),
    ]
    assert run["flags"] == []


async def test_dishwasher_products_and_beverage_ingredients_are_dosed(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    def pack(price: float, size: float, unit: str) -> dict[str, Any]:
        return {
            "diameter": None,
            "price": {
                "source": "fixed",
                "pack_price": price,
                "pack_size": size,
                "pack_unit": unit,
            },
        }

    place_materials(
        hass_storage,
        stored_material(
            "tabs",
            form="dishwasher_product",
            type="Dishwasher tabs",
            density=None,
            **pack(9.0, 60.0, "pcs"),
        ),
        stored_material(
            "beans",
            form="beverage_ingredient",
            type="Coffee beans",
            density=0.4,
            **pack(16.0, 1000.0, "g"),
        ),
        stored_material(
            "milk",
            form="beverage_ingredient",
            type="Milk",
            density=1.03,
            **pack(1.2, 1000.0, "ml"),
        ),
    )
    device = await add_washer(hass, program=False, price=0.50)
    await panel.call(
        "coinop/devices/update_settings",
        device_id=device.subentry_id,
        settings={
            "doses": [
                {"id": f"dose-{material}", "material_id": material}
                for material in ("tabs", "beans", "milk")
            ],
            "program_defaults": {
                "default": {
                    "doses": {"dose-tabs": 1, "dose-beans": 10, "dose-milk": 150}
                }
            },
        },
    )

    await washed(hass, clock, kwh=1.2)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-tabs", "default_row", "tabs", 1, "pcs", 0.15, 0.15),
        ("dose-beans", "default_row", "beans", 10, "g", 0.016, 0.16),
        ("dose-milk", "default_row", "milk", 150, "ml", 0.0012, 0.18),
    ]
    assert run["flags"] == []


async def test_editing_the_default_row_changes_the_open_run_but_no_ended_one(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await dose(panel, washer, {"dose-liquid": 75})
    await washed(hass, clock, kwh=1.2)
    await set_washer(hass, "running")

    await dose(panel, washer, {"dose-liquid": 60, "dose-whitener": 20})

    ended, running = (await panel.call("coinop/runs/list"))["runs"]
    assert (ended["total"], running["total"]) == (1.05, 0.44)
    await set_washer(hass, "finished")
    _, run = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-liquid", "default_row", "liquid", 60, "ml", 0.006, 0.36),
        ("dose-whitener", "default_row", "whitener", 20, "g", 0.004, 0.08),
    ]


async def test_a_removed_dose_leaves_the_default_row(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    await dose(panel, washer, {"dose-liquid": 75, "dose-pods": 1})

    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": DOSES[1:]},
    )

    assert result["settings"]["doses"] == DOSES[1:]
    assert result["settings"]["program_defaults"] == {
        "default": {"doses": {"dose-pods": 1}},
        "programs": {},
    }


@pytest.mark.parametrize(
    ("status", "outcome", "flags"),
    [
        ("cancelled", "cancelled", ["ended_early_defaults"]),
        ("finished", "completed", []),
    ],
)
async def test_a_cancelled_run_is_flagged_for_its_defaults(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
    status: str,
    outcome: str,
    flags: list[str],
) -> None:
    await dose(panel, washer, {"dose-pods": 1})
    await set_washer(hass, "running")
    await clock.advance(minutes=10)

    await set_washer(hass, status)
    await set_energy(hass, 100.2)

    [run] = stored_runs(hass_storage)
    assert (run["outcome"], run["flags"]) == (outcome, flags)
    assert len(doses(run)) == 1


@pytest.mark.parametrize(
    ("added", "code"),
    [
        ({"id": "dose-new", "material_id": "gone"}, "not_found"),
        ({"id": "dose-new", "material_id": "whitener"}, "not_allowed"),
        ({"id": "dose-pods", "material_id": "liquid"}, "invalid_format"),
    ],
)
async def test_a_new_dose_needs_its_own_id_and_a_pickable_material(
    washer: ConfigSubentry, panel: PanelClient, added: dict[str, str], code: str
) -> None:
    await panel.call("coinop/materials/archive", material_id="whitener")

    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": [DOSES[1], added]},
    )

    assert error["code"] == code


async def test_a_dose_keeps_its_archived_material(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await dose(panel, washer, {"dose-liquid": 75, "dose-whitener": 20})
    await panel.call("coinop/materials/archive", material_id="whitener")

    settings = await dose(panel, washer, {"dose-whitener": 30})
    await washed(hass, clock, kwh=1.2)

    assert settings["doses"] == DOSES
    [run] = stored_runs(hass_storage)
    assert doses(run) == []


async def test_a_printer_has_no_doses(hass: HomeAssistant, panel: PanelClient) -> None:
    await add_device(hass, await add_hub(hass))
    [printer] = (await panel.call("coinop/devices/list"))["devices"]

    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=printer["id"],
        settings={"doses": DOSES},
    )

    assert error["code"] == "not_allowed"


async def test_doses_count_as_material_costs(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    browser: HttpClient,
) -> None:
    await dose(panel, washer, {"dose-liquid": 75, "dose-pods": 1})

    await washed(hass, clock, kwh=1.2)

    assert value(hass, "sensor.washer_material_cost") == pytest.approx(0.75)
    groups = (await panel.call("coinop/aggregates/get", group_by=["material"]))[
        "groups"
    ]
    assert [(g["material_name"], g["cost"]) for g in groups] == [
        ("LIQUID", 0.45),
        ("PODS", 0.3),
        (None, 0.6),
    ]
    [run] = (await panel.call("coinop/runs/list"))["runs"]
    statement = await export(panel, browser, run_ids=[run["id"]])
    assert "LIQUID 75 ml €0.006 €0.45" in statement.lines
    assert "PODS 1 pcs €0.30 €0.30" in statement.lines


SCALE = "sensor.whitener_scale"


async def set_scale(hass: HomeAssistant, level: Any, unit: str = "g") -> None:
    hass.states.async_set(SCALE, str(level), {"unit_of_measurement": unit})
    await hass.async_block_till_done()


async def stock(
    panel: PanelClient,
    washer: ConfigSubentry,
    stock_input: dict[str, Any],
    default: dict[str, float] | None = None,
) -> Any:
    """The Whitener's Dose weighed by `stock_input`."""
    result = await panel.call(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={
            "doses": [*DOSES[:2], DOSES[2] | {"stock": stock_input}],
            "program_defaults": {"default": {"doses": default or {}}},
        },
    )
    return result["settings"]


async def test_a_stock_input_doses_what_it_lost_during_the_run_ignoring_refills(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 500)
    await stock(panel, washer, {"entity_id": SCALE}, {"dose-whitener": 20})
    await set_washer(hass, "running")
    await clock.advance(minutes=5)
    await set_scale(hass, 450)
    await set_scale(hass, 1000)
    await clock.advance(minutes=60)
    await set_scale(hass, 975)
    await clock.advance(minutes=25)

    await set_washer(hass, "finished")
    await set_energy(hass, 100)
    await set_scale(hass, 975)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-whitener", "stock_input", "whitener", 75, "g", 0.004, 0.30)
    ]
    assert run["flags"] == []


async def test_stock_usage_survives_a_restart(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 500)
    await stock(panel, washer, {"entity_id": SCALE})
    await set_washer(hass, "running")
    await clock.advance(minutes=30)
    await set_scale(hass, 450)
    await set_scale(hass, 1000)

    await restart(hass, washer_entry(hass))
    await clock.advance(minutes=60)
    await set_scale(hass, 975)
    await set_washer(hass, "finished")
    await set_energy(hass, 100)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-whitener", "stock_input", "whitener", 75, "g", 0.004, 0.30)
    ]
    assert "stocks" not in run


async def test_the_last_stock_report_may_come_up_to_five_minutes_late(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 500)
    await stock(panel, washer, {"entity_id": SCALE})
    await set_washer(hass, "running")
    await clock.advance(minutes=90)
    await set_washer(hass, "finished")
    await set_energy(hass, 100)
    await clock.advance(minutes=4)
    assert stored_runs(hass_storage) == []

    await set_scale(hass, 425)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-whitener", "stock_input", "whitener", 75, "g", 0.004, 0.30)
    ]


async def test_an_unavailable_stock_input_falls_back_to_the_default_with_a_flag(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, "unavailable")
    await stock(panel, washer, {"entity_id": SCALE}, {"dose-whitener": 20})

    await washed(hass, clock, kwh=1.2)
    await clock.advance(minutes=4, seconds=59)
    assert stored_runs(hass_storage) == []
    await clock.advance(seconds=1)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-whitener", "default_row", "whitener", 20, "g", 0.004, 0.08)
    ]
    assert run["flags"] == ["stock_input_unavailable"]


async def test_a_stock_input_that_lost_nothing_doses_nothing(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    await set_scale(hass, 500)
    await stock(panel, washer, {"entity_id": SCALE}, {"dose-whitener": 20})

    await washed(hass, clock, kwh=1.2)
    await set_scale(hass, 500)

    [run] = stored_runs(hass_storage)
    assert (doses(run), run["flags"]) == ([], [])


async def test_a_volume_in_an_attribute_is_converted_through_the_density(
    hass: HomeAssistant,
    clock: Clock,
    washer: ConfigSubentry,
    panel: PanelClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.states.async_set(SCALE, "ok", {"level": 0.3})
    await stock(panel, washer, {"entity_id": SCALE, "attribute": "level", "unit": "L"})
    await set_washer(hass, "running")
    await clock.advance(minutes=90)

    hass.states.async_set(SCALE, "ok", {"level": 0.25})
    await set_washer(hass, "finished")
    await set_energy(hass, 100)

    [run] = stored_runs(hass_storage)
    # 50 ml at 0.9 g/ml.
    assert doses(run) == [
        (
            "dose-whitener",
            "stock_input",
            "whitener",
            pytest.approx(45),
            "g",
            0.004,
            0.18,
        )
    ]


@pytest.mark.parametrize(
    "stock_input",
    [
        {"entity_id": SCALE, "attribute": "level"},
        {"entity_id": SCALE, "attribute": "level", "unit": "W"},
        {"attribute": "level", "unit": "g"},
    ],
)
async def test_a_stock_input_needs_an_entity_and_with_an_attribute_a_unit(
    washer: ConfigSubentry, panel: PanelClient, stock_input: dict[str, str]
) -> None:
    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": [DOSES[2] | {"stock": stock_input}]},
    )

    assert error["code"] == "invalid_format"


async def test_a_dose_counted_in_pieces_has_no_stock_input(
    washer: ConfigSubentry, panel: PanelClient
) -> None:
    error = await panel.error(
        "coinop/devices/update_settings",
        device_id=washer.subentry_id,
        settings={"doses": [DOSES[1] | {"stock": {"entity_id": SCALE}}]},
    )

    assert error["code"] == "not_allowed"
