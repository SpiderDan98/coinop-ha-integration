"""Doses: a washing machine's Material Line Items from its Program Defaults."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub, add_washing_machine
from .http import HttpClient
from .stored import place_materials, stored_material
from .test_cost_statement import export
from .test_runs import stored_runs, value
from .test_washing_machines import set_energy, set_washer, wash
from .websocket import PanelClient


def laundry(material_id: str, pack_unit: str, **fields: Any) -> dict[str, Any]:
    price = {"source": "fixed", "pack_unit": pack_unit} | fields.pop("price")
    return stored_material(
        material_id,
        **({"form": "detergent", "diameter": None, "price": price} | fields),
    )


# 0.006 per ml, 0.30 per pod, 0.004 per g.
LIQUID = laundry(
    "liquid",
    "ml",
    type="Liquid detergent",
    density=1.04,
    price={"pack_price": 9.0, "pack_size": 1500.0},
)
PODS = laundry(
    "pods",
    "pcs",
    type="Detergent pods",
    density=None,
    price={"pack_price": 12.0, "pack_size": 40.0},
)
WHITENER = laundry(
    "whitener",
    "g",
    form="laundry_additive",
    type="Whitener",
    density=0.9,
    price={"pack_price": 4.0, "pack_size": 1000.0},
)
DOSES = [
    {"id": "dose-liquid", "material_id": "liquid"},
    {"id": "dose-pods", "material_id": "pods"},
    {"id": "dose-whitener", "material_id": "whitener"},
]


@pytest.fixture
async def washer(
    hass: HomeAssistant, clock: Clock, hass_storage: dict[str, Any]
) -> ConfigSubentry:
    """A washing machine on a plug's energy meter, with the laundry Materials."""
    hass.config.currency = "EUR"
    place_materials(hass_storage, LIQUID, PODS, WHITENER)
    await set_energy(hass, 100)
    await set_washer(hass, "off")
    return await add_washing_machine(hass, await add_hub(hass), price=0.50)


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

    await wash(hass, clock)

    [run] = stored_runs(hass_storage)
    assert doses(run) == [
        ("dose-liquid", "default_row", "liquid", 75, "ml", 0.006, 0.45),
        ("dose-pods", "default_row", "pods", 1, "pcs", 0.30, 0.30),
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
    await wash(hass, clock)
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
        "default": {"doses": {"dose-pods": 1}}
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
    await wash(hass, clock)

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

    await wash(hass, clock)

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
