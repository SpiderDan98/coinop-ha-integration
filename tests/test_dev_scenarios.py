"""The dev container's Scenarios load through today's websocket API."""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml_dict
import pytest
from pytest_homeassistant_custom_component.common import MockUser

import custom_components
from dev.coinop_dev import async_setup
from dev.coinop_dev.scenarios import (
    HISTORIES,
    PIECES,
    PRESETS,
    DeviceWithHistory,
    async_load,
)

from .clock import Clock
from .devices import configure
from .test_device_flow import fields
from .test_quick_start import offered, open_add_device, pick
from .websocket import PanelClient

DEV = Path(__file__).parents[1] / "dev"
CONFIG = DEV / "configuration.yaml"
PLUG_ENERGY = "sensor.washing_machine_plug_energy"
DISHWASHER_PLUG_ENERGY = "sensor.dishwasher_plug_energy"
PLUG_POWER = "sensor.kobra_s1_plug_power"
VORON_PLUG_POWER = "sensor.voron_2_4_plug_power"

# The static stand-ins' Pieces: the HA device's label in Quick Start, its plug's power
# helper and sensor, its Status entity, and a Status of a running and a finished print.
STATIC = {
    "anycubic.3d_printer": (
        "Anycubic Kobra S1 · Anycubic 3D Printer - Local Control",
        "input_number.anycubic_kobra_power",
        "sensor.anycubic_kobra_s1_plug_power",
        "event.anycubic_kobra_s1_print_event",
        "started",
        "finished",
    ),
    "bambu_lab.3d_printer": (
        "P1S · Bambu Lab",
        "input_number.p1s_power",
        "sensor.p1s_plug_power",
        "sensor.p1s_print_status",
        "running",
        "finish",
    ),
    "prusalink.3d_printer": (
        "Prusa Core One · PrusaLink",
        "input_number.core_one_power",
        "sensor.prusa_core_one_plug_power",
        "sensor.prusa_core_one",
        "printing",
        "finished",
    ),
    "octoprint.3d_printer": (
        "OctoPrint · OctoPrint",
        "input_number.octoprint_power",
        "sensor.octoprint_plug_power",
        "sensor.octoprint_current_state",
        "printing",
        "finishing",
    ),
    "ha_creality_ws.3d_printer": (
        "K1C · Creality",
        "input_number.k1c_power",
        "sensor.k1c_plug_power",
        "sensor.k1c_print_status",
        "printing",
        "completed",
    ),
    "elegoo_printer.3d_printer": (
        "Centauri Carbon · Elegoo",
        "input_number.centauri_carbon_power",
        "sensor.centauri_carbon_plug_power",
        "sensor.centauri_carbon_print_status",
        "printing",
        "complete",
    ),
}

# The static EV chargers' Pieces: each HA device Quick Start offers, as its label, its
# Status entity and the counter it meters with, then a Status of a charging and of an
# unplugged car.
EV_CHARGERS = {
    "evcc_intg.ev_charger": (
        [
            (
                "evcc ☀️🚘 Solar Charging [evcc] · evcc",
                "binary_sensor.evcc_garage_charging",
                "sensor.evcc_garage_charged_energy",
            )
        ],
        "on",
        "off",
    ),
    "ocpp.ev_charger": (
        [
            (
                f"charger Connector {n} · OCPP",
                f"sensor.charger_conn{n}_status_connector",
                f"sensor.charger_conn{n}_energy_active_import_register",
            )
            for n in (1, 2)
        ],
        "Charging",
        "Available",
    ),
    "easee.ev_charger": (
        [("Garage · Easee", "sensor.garage_status", "sensor.garage_lifetime_energy")],
        "charging",
        "disconnected",
    ),
    "zaptec.ev_charger": (
        [
            (
                "Driveway · Zaptec",
                "sensor.driveway_charger_operation_mode",
                "sensor.driveway_total_charge_power_session",
            )
        ],
        "connected_charging",
        "disconnected",
    ),
    "goecharger_mqtt.ev_charger": (
        [
            (
                "go-eCharger · go-e Charger MQTT",
                "sensor.go_echarger_car",
                "sensor.go_echarger_eto",
            )
        ],
        "charging",
        "idle",
    ),
    "goecharger_api2.ev_charger": (
        [
            (
                "go-e Charger · go-e Charger API v2",
                "sensor.go_e_charger_car_value",
                "sensor.go_e_charger_eto",
            )
        ],
        "Charging",
        "Idle",
    ),
    "wallbox.ev_charger": (
        [
            (
                "Wallbox Garage · Wallbox",
                "sensor.wallbox_garage_status_description",
                "sensor.wallbox_garage_added_energy",
            )
        ],
        "Charging",
        "Ready",
    ),
}

EV_CHARGER_DEVICES = [
    device for devices, _, _ in EV_CHARGERS.values() for device in devices
]


@pytest.fixture
async def helpers(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Devices' helpers from the dev configuration.yaml, and the dev container's
    integrations where Home Assistant finds them. Its camera stays in the container:
    the platform needs the ffmpeg binary."""
    monkeypatch.setattr(
        custom_components, "__path__", [*custom_components.__path__, str(DEV)]
    )
    hass.data.pop(DATA_CUSTOM_COMPONENTS, None)
    config = await hass.async_add_executor_job(load_yaml_dict, CONFIG)
    for domain in ("input_select", "input_text", "input_number", "template"):
        assert await async_setup_component(hass, domain, {domain: config[domain]})


def test_the_load_service_offers_every_preset_piece_and_option() -> None:
    fields = load_yaml_dict(DEV / "coinop_dev" / "services.yaml")["load"]["fields"]

    assert fields["preset"]["selector"]["select"]["options"] == list(PRESETS)
    assert fields["pieces"]["selector"]["select"]["options"] == list(PIECES)
    assert fields["history"]["selector"]["select"]["options"] == list(HISTORIES)
    assert "boolean" in fields["open_run"]["selector"]


def test_no_two_pieces_share_a_helper_and_loading_resets_every_helper_a_device_uses() -> (
    None
):
    users: dict[str, list[str]] = {}
    unreset = {}
    for name, piece in PIECES.items():
        for helper in piece.helpers:
            users.setdefault(helper, []).append(name)
        if isinstance(piece, DeviceWithHistory):
            inputs = set(re.findall(r"input_\w+\.\w+", json.dumps(piece.device)))
            unreset[name] = inputs - set(piece.helpers)

    assert {helper: names for helper, names in users.items() if len(names) > 1} == {}
    assert {name: inputs for name, inputs in unreset.items() if inputs} == {}


async def counts(panel: PanelClient) -> tuple[int, int, int, int]:
    """Devices, Materials, Runs and open Runs."""
    runs = (await panel.call("coinop/runs/list"))["runs"]
    return (
        len((await panel.call("coinop/devices/list"))["devices"]),
        len((await panel.call("coinop/materials/list"))["materials"]),
        len(runs),
        sum(run["ended"] is None for run in runs),
    )


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("empty", (0, 0, 0, 0)),
        ("quick-start", (0, 0, 0, 0)),
        ("few-runs", (1, 8, 7, 0)),
        ("printing-now", (1, 8, 8, 1)),
        ("two-printers", (2, 8, 17, 0)),
        ("washing-machine", (1, 4, 10, 0)),
        ("irrigation", (1, 0, 6, 0)),
    ],
)
async def test_a_preset_fills_coinop_from_scratch(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    name: str,
    expected: tuple[int, int, int, int],
) -> None:
    await async_load(hass, name, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == expected
    assert len(hass.config_entries.async_entries("coinop")) == 1


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    ("piece", "expected"),
    [
        ("prusa", (1, 8, 7, 0)),
        ("bambu", (1, 8, 10, 0)),
        ("washer", (1, 4, 10, 0)),
        ("irrigation", (1, 0, 6, 0)),
    ],
)
async def test_a_device_with_history_loads_alone(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    piece: str,
    expected: tuple[int, int, int, int],
) -> None:
    await async_load(hass, {"pieces": [piece]}, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == expected


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    ("piece", "label"),
    [
        (
            "anycubic.3d_printer",
            "Anycubic Kobra S1 · Anycubic 3D Printer - Local Control",
        ),
        ("anycubic_cloud.3d_printer", "Kobra S1 · Anycubic Cloud & LAN"),
        ("bambu_lab.3d_printer", "P1S · Bambu Lab"),
        ("prusalink.3d_printer", "Prusa Core One · PrusaLink"),
        ("octoprint.3d_printer", "OctoPrint · OctoPrint"),
        ("ha_creality_ws.3d_printer", "K1C · Creality"),
        ("elegoo_printer.3d_printer", "Centauri Carbon · Elegoo"),
        ("moonraker.3d_printer", "Voron 2.4 · Moonraker"),
        ("ha_washdata.washing_machine", "Washing machine · WashData"),
        ("ha_washdata.dishwasher", "Dishwasher · WashData"),
        (
            "tesla_wall_connector.ev_charger",
            "Tesla Wall Connector · Tesla Wall Connector",
        ),
    ],
)
async def test_a_quick_start_piece_loads_alone(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    piece: str,
    label: str,
) -> None:
    await async_load(hass, {"pieces": [piece]}, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == (0, 0, 0, 0)
    [entry] = hass.config_entries.async_entries("coinop")
    result = await open_add_device(hass, entry)
    assert [option["label"] for option in offered(result)] == [label, "manual"]


@pytest.mark.usefixtures("helpers")
async def test_all_pieces_load_together_with_their_shared_data_once(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, {"pieces": list(PIECES)}, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == (4, 12, 33, 0)
    await panel.subscribe("coinop/catalog/subscribe")
    catalog = await panel.event()
    assert len(catalog["tags"]) == 6
    assert len(catalog["templates"]) == 1
    [entry] = hass.config_entries.async_entries("coinop")
    assert len(offered(await open_add_device(hass, entry))) == 20
    # Under its own id: a Status shared with another Piece's would have a suffix.
    assert all(hass.states.get(status) for _, _, _, status, *_ in STATIC.values())
    assert all(hass.states.get(status) for _, status, _ in EV_CHARGER_DEVICES)


DEVICES_WITH_HISTORY = [
    n for n, p in PIECES.items() if isinstance(p, DeviceWithHistory)
]


@pytest.mark.usefixtures("helpers")
async def test_without_history_every_device_with_history_exists_without_a_run(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(
        hass,
        {"pieces": DEVICES_WITH_HISTORY, "history": "none", "open_run": False},
        hass_admin_user,
    )
    await hass.async_block_till_done()

    devices = (await panel.call("coinop/devices/list"))["devices"]
    assert [device["name"] for device in devices] == [
        "Prusa MK4",
        "Bambu Lab X1C",
        "Washing machine",
        "Garden valve",
    ]
    assert (await panel.call("coinop/runs/list"))["runs"] == []


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize("piece", DEVICES_WITH_HISTORY)
async def test_a_device_with_long_history_has_runs_from_up_to_two_years_ago(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    piece: str,
) -> None:
    await async_load(hass, {"pieces": [piece], "history": "long"}, hass_admin_user)
    await hass.async_block_till_done()

    runs = (await panel.call("coinop/runs/list"))["runs"]
    oldest = min(datetime.fromisoformat(run["started"]) for run in runs)
    assert len(runs) > 50
    assert timedelta(days=365) < dt_util.now() - oldest < timedelta(days=731)
    assert all(run["ended"] for run in runs)


# What ends each Device with history's open Run, set as its integration would.
ENDS = {
    "prusa": {"input_select.prusa_status": "finished"},
    "bambu": {"input_select.bambu_status": "finished"},
    "washer": {"input_select.washer_status": "finished"},
    "irrigation": {"input_select.irrigation_status": "off"},
}


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize("history", ["none", "short"])
async def test_the_open_run_option_starts_a_run_on_each_device_that_its_helpers_end(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
    history: str,
) -> None:
    await async_load(
        hass,
        {"pieces": list(PIECES), "history": history, "open_run": True},
        hass_admin_user,
    )
    await hass.async_block_till_done()
    runs = (await panel.call("coinop/runs/list"))["runs"]
    running = {run["id"]: run["device_name"] for run in runs if run["ended"] is None}

    await clock.advance(minutes=30)
    for helpers in ENDS.values():
        for entity_id, value in helpers.items():
            await set_helper(hass, entity_id, value)
    await clock.advance(minutes=10)

    assert list(ENDS) == DEVICES_WITH_HISTORY
    assert sorted(running.values()) == [
        "Bambu Lab X1C",
        "Garden valve",
        "Prusa MK4",
        "Washing machine",
    ]
    runs = (await panel.call("coinop/runs/list"))["runs"]
    assert {run["outcome"] for run in runs if run["id"] in running} == {"completed"}
    assert not [run for run in runs if run["ended"] is None]
    assert len(runs) == (4 if history == "none" else 33 + 4)


@pytest.mark.usefixtures("helpers")
async def test_the_long_history_spans_two_years_and_goes_with_the_next_scenario(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, "long-history", hass_admin_user)
    runs = (await panel.call("coinop/runs/list"))["runs"]
    devices, materials, _, _ = await counts(panel)
    thumbnails = await hass.async_add_executor_job(
        lambda: list(files.glob("images/*/*"))
    )

    await async_load(hass, "empty", hass_admin_user)

    assert (devices, materials) == (2, 8)
    assert len(runs) > 250
    assert any(run["flags"] for run in runs)
    assert thumbnails
    assert await counts(panel) == (0, 0, 0, 0)
    assert not await hass.async_add_executor_job(files.exists)


@pytest.mark.usefixtures("helpers")
async def test_the_washing_machine_mixes_measured_values_and_program_defaults(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, "washing-machine", hass_admin_user)
    await hass.async_block_till_done()

    runs = [
        (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
        for run in (await panel.call("coinop/runs/list"))["runs"]
    ]
    methods = {
        (item["kind"], item.get("method") or item.get("dose_source"))
        for run in runs
        for item in run["line_items"]
    }
    assert methods == {
        ("electricity", "measured"),
        ("water", "measured"),
        ("material", "stock_input"),
        ("material", "program_default"),
        ("material", "default_row"),
    }
    assert {run["program"] for run in runs} == {
        "Cotton 60°",
        "Eco 40-60",
        "Wool",
        "Quick 30",
        None,
    }
    assert any("ended_early_defaults" in run["flags"] for run in runs)


@pytest.mark.usefixtures("helpers")
async def test_the_irrigation_is_listed_under_its_type_name_and_costs_only_its_water(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    await async_load(hass, "irrigation", hass_admin_user)
    await hass.async_block_till_done()

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert (device["type"], device["type_name"]) == ("other", "Irrigation")
    assert device["ha_settings"]["consumption"] == {"source": "none"}
    assert device["ha_settings"]["water"]["source"] == "meter"
    runs = [
        (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
        for run in (await panel.call("coinop/runs/list"))["runs"]
    ]
    assert {
        (item["kind"], item["method"]) for run in runs for item in run["line_items"]
    } == {("water", "measured")}
    assert all(len(run["line_items"]) == 1 for run in runs)
    assert sum(run["line_items"][0]["quantity"] for run in runs) == pytest.approx(
        1207.5
    )
    assert all(run["finalised"] and run["total"] > 0 for run in runs)
    assert {(run["outcome"], *run["flags"]) for run in runs} == {("completed",)}
    assert hass.states.is_state("input_select.irrigation_status", "off")


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    "data", [{"preset": "washing-machine"}, {"pieces": ["washer"]}], ids=str
)
async def test_the_load_service_fills_coinop_when_a_task_awaits_its_call(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    data: dict[str, Any],
) -> None:
    """As over REST (`make dev`), whose view awaits the service call in a task."""
    assert await async_setup(hass, {})
    call = hass.services.async_call(
        "coinop_dev",
        "load",
        data,
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )

    async with asyncio.timeout(10):
        await hass.async_create_task(call)

    assert await counts(panel) == (1, 4, 10, 0)


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    "data", [{"preset": "washing-machine"}, {"pieces": ["washer"]}], ids=str
)
async def test_the_load_service_fills_coinop_when_its_executor_jobs_are_done_at_once(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: dict[str, Any],
) -> None:
    """Awaiting an executor job that is done already doesn't suspend, so the load can
    reach its first report before Home Assistant tracks the tasks running it."""

    def done_at_once(executor: Any, job: Any, *args: Any) -> asyncio.Future[Any]:
        future = hass.loop.create_future()
        future.set_result(job(*args))
        return future

    assert await async_setup(hass, {})
    monkeypatch.setattr(hass.loop, "run_in_executor", done_at_once)
    call = hass.services.async_call(
        "coinop_dev",
        "load",
        data,
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )

    async with asyncio.timeout(10):
        await hass.async_create_task(call)

    assert await counts(panel) == (1, 4, 10, 0)


@pytest.mark.usefixtures("helpers")
async def test_the_scenarios_command_answers_the_pieces_presets_and_the_loaded_selection(
    hass: HomeAssistant, hass_admin_user: MockUser, panel: PanelClient, files: Path
) -> None:
    # Coin-op set up before the panel connects, without storing a selection.
    await async_load(hass, "empty", hass_admin_user)
    assert await async_setup(hass, {})
    before = await panel.call("coinop_dev/scenarios")

    await load(hass, hass_admin_user, {"preset": "two-printers"})
    from_preset = await panel.call("coinop_dev/scenarios")
    await load(
        hass,
        hass_admin_user,
        {"pieces": ["irrigation", "washer"], "history": "none", "open_run": True},
    )
    picked = await panel.call("coinop_dev/scenarios")

    assert (before["preset"], before["selection"]) == (None, None)
    assert [
        (group["device_type"], [piece["name"] for piece in group["pieces"]])
        for group in before["groups"]
    ] == [
        (
            "3d_printer",
            [
                "prusa",
                "bambu",
                "anycubic.3d_printer",
                "anycubic_cloud.3d_printer",
                "bambu_lab.3d_printer",
                "prusalink.3d_printer",
                "octoprint.3d_printer",
                "ha_creality_ws.3d_printer",
                "elegoo_printer.3d_printer",
                "moonraker.3d_printer",
            ],
        ),
        ("washing_machine", ["washer", "ha_washdata.washing_machine"]),
        ("dishwasher", ["ha_washdata.dishwasher"]),
        ("ev_charger", ["tesla_wall_connector.ev_charger", *EV_CHARGERS]),
        ("other", ["irrigation"]),
    ]
    prusa, _, _, kobra, *_ = before["groups"][0]["pieces"]
    assert (prusa["title"], prusa["section"]) == ("Prusa MK4", "device")
    assert (kobra["title"], kobra["section"]) == (
        "Kobra S1 · Anycubic Cloud & LAN",
        "quick_start",
    )
    assert all(piece["description"] for g in before["groups"] for piece in g["pieces"])
    presets = {preset["name"]: preset for preset in before["presets"]}
    assert list(presets) == [
        "empty",
        "quick-start",
        "few-runs",
        "printing-now",
        "two-printers",
        "long-history",
        "washing-machine",
        "irrigation",
    ]
    assert presets["two-printers"]["title"] == "Two printers"
    assert before["options"] == {"history": ["none", "short", "long"]}
    assert presets["two-printers"]["selection"] == {
        "pieces": ["prusa", "bambu"],
        "history": "short",
        "open_run": False,
    }
    assert presets["long-history"]["selection"]["history"] == "long"
    assert presets["printing-now"]["selection"]["open_run"] is True
    assert presets["quick-start"]["selection"]["pieces"] == [
        "anycubic.3d_printer",
        "anycubic_cloud.3d_printer",
        "bambu_lab.3d_printer",
        "prusalink.3d_printer",
        "octoprint.3d_printer",
        "ha_creality_ws.3d_printer",
        "elegoo_printer.3d_printer",
        "moonraker.3d_printer",
        "ha_washdata.washing_machine",
        "ha_washdata.dishwasher",
        "tesla_wall_connector.ev_charger",
        *EV_CHARGERS,
    ]
    assert (from_preset["preset"], from_preset["selection"]) == (
        "two-printers",
        {"pieces": ["prusa", "bambu"], "history": "short", "open_run": False},
    )
    assert (picked["preset"], picked["selection"]) == (
        None,
        {"pieces": ["washer", "irrigation"], "history": "none", "open_run": True},
    )


async def load(hass: HomeAssistant, user: MockUser, data: dict[str, Any]) -> None:
    await hass.services.async_call(
        "coinop_dev", "load", data, blocking=True, context=Context(user_id=user.id)
    )
    await hass.async_block_till_done()


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_washing_machine_washdata_follows(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass, "Washing machine · WashData", optional_meter=PLUG_ENERGY, price=0.32
    )

    await set_helper(hass, "input_number.washdata_washer_energy", 100)
    await set_helper(hass, "input_select.washdata_washer_program", "Eco 40-60")
    await set_helper(hass, "input_select.washdata_washer_status", "running")
    await clock.advance(hours=1)
    await set_helper(hass, "input_number.washdata_washer_energy", 100.7)
    await set_helper(hass, "input_select.washdata_washer_status", "cancelled")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["outcome"]) == ("Eco 40-60", "cancelled")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.7)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_dishwasher_washdata_follows_as_a_dishwasher(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass,
        "Dishwasher · WashData",
        optional_meter=DISHWASHER_PLUG_ENERGY,
        price=0.32,
        water_price=4.2,
    )

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert (device["name"], device["type"]) == ("Dishwasher", "dishwasher")
    await set_helper(hass, "input_number.washdata_dishwasher_energy", 50)
    await set_helper(hass, "input_select.washdata_dishwasher_program", "Eco 50°")
    await set_helper(hass, "input_select.washdata_dishwasher_status", "running")
    await clock.advance(hours=2)
    await set_helper(hass, "input_number.washdata_dishwasher_energy", 50.9)
    await set_helper(hass, "input_select.washdata_dishwasher_status", "finished")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["program"], run["outcome"]) == ("Eco 50°", "completed")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.9)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_printer_of_the_anycubic_stand_in(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(
        hass, "Kobra S1 · Anycubic Cloud & LAN", meter=PLUG_POWER, price=0.32
    )

    await set_helper(hass, "input_number.kobra_power", 120)
    await set_helper(hass, "input_text.kobra_job", "Benchy.gcode")
    await set_helper(hass, "input_select.kobra_status", "printing")
    await clock.advance(hours=1)
    await set_helper(hass, "input_select.kobra_status", "finished")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["name"], run["outcome"]) == ("Benchy", "completed")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.12)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_moonraker_printer_with_its_preview_as_thumbnail(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()

    await quick_start(hass, "Voron 2.4 · Moonraker", meter=VORON_PLUG_POWER, price=0.32)

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["type"] == "3d_printer"
    await set_helper(hass, "input_number.voron_power", 150)
    await set_helper(hass, "input_text.voron_job", "Benchy.gcode")
    await set_helper(hass, "input_select.voron_status", "printing")
    await clock.advance(hours=1)
    await set_helper(hass, "input_number.voron_filament", 3.2)
    await set_helper(hass, "input_select.voron_status", "complete")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert (run["name"], run["outcome"]) == ("Benchy", "completed")
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    assert [image["kind"] for image in run["images"]] == ["thumbnail"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.15)


@pytest.mark.usefixtures("helpers")
async def test_quick_start_adds_the_wall_connector_with_its_own_meter(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await hass.async_block_till_done()
    await set_helper(hass, "input_number.wall_connector_energy", 1200)

    await quick_start(hass, "Tesla Wall Connector · Tesla Wall Connector", price=0.32)

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["type"] == "ev_charger"
    await set_helper(hass, "input_select.wall_connector_status", "charging")
    await clock.advance(hours=1)
    await set_helper(hass, "input_number.wall_connector_energy", 1207)
    await set_helper(hass, "input_select.wall_connector_status", "waiting_car")
    await clock.advance(hours=1)
    await set_helper(hass, "input_select.wall_connector_status", "charging")
    await clock.advance(hours=1)
    await set_helper(hass, "input_number.wall_connector_energy", 1211)
    await set_helper(hass, "input_select.wall_connector_status", "not_connected")
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert run["outcome"] == "completed"
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(11)


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize(
    ("piece", "label", "power", "plug", "status", "running", "finished"),
    [(piece, *row) for piece, row in STATIC.items()],
)
async def test_quick_start_adds_a_static_stand_ins_printer_run_through_its_status(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
    piece: str,
    label: str,
    power: str,
    plug: str,
    status: str,
    running: str,
    finished: str,
) -> None:
    """As a contributor sets the Status in the developer tools, keeping its attributes."""
    await async_load(hass, {"pieces": [piece]}, hass_admin_user)
    await hass.async_block_till_done()
    [entry] = hass.config_entries.async_entries("coinop")
    result = await open_add_device(hass, entry)
    [device_id] = [o["value"] for o in offered(result) if o["label"] == label]

    result = await configure(hass, result, {"device": device_id})
    result = await configure(hass, result, {"meter": plug, "price": 0.32})
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")

    [device] = (await panel.call("coinop/devices/list"))["devices"]
    assert device["type"] == "3d_printer"
    await set_helper(hass, power, 100)
    await set_state(hass, status, running)
    await clock.advance(hours=1)
    await set_state(hass, status, finished)
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert run["outcome"] == "completed"
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(0.1)


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize("piece", EV_CHARGERS)
async def test_quick_start_adds_a_static_ev_charger_with_the_counter_it_brings(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    piece: str,
) -> None:
    chargers, _, _ = EV_CHARGERS[piece]
    await async_load(hass, {"pieces": [piece]}, hass_admin_user)
    await hass.async_block_till_done()

    assert await counts(panel) == (0, 0, 0, 0)
    [entry] = hass.config_entries.async_entries("coinop")
    devices = {
        o["label"]: o["value"] for o in offered(await open_add_device(hass, entry))
    }
    assert list(devices) == [label for label, _, _ in chargers] + ["manual"]
    for label, status, counter in chargers:
        result = await pick(hass, entry, devices[label])
        assert fields(result) == ["price", "price_entity"]
        result = await configure(hass, result, {"price": 0.32})
        assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
        data = list(entry.subentries.values())[-1].data
        assert data["device_type"] == "ev_charger"
        assert data["status"]["entity_id"] == status
        assert data["consumption"]["entity_id"] == counter


@pytest.mark.usefixtures("helpers")
@pytest.mark.parametrize("piece", EV_CHARGERS)
async def test_a_static_ev_chargers_charge_is_run_through_its_status(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    panel: PanelClient,
    files: Path,
    clock: Clock,
    piece: str,
) -> None:
    """As a contributor sets the Status and the counter in the developer tools."""
    [(label, status, counter), *_], charging, unplugged = EV_CHARGERS[piece]
    await async_load(hass, {"pieces": [piece]}, hass_admin_user)
    await hass.async_block_till_done()
    [entry] = hass.config_entries.async_entries("coinop")
    result = await open_add_device(hass, entry)
    [device_id] = [o["value"] for o in offered(result) if o["label"] == label]
    result = await configure(hass, result, {"device": device_id})
    await configure(hass, result, {"price": 0.32})

    reading = hass.states.get(counter)
    assert reading is not None
    per_kwh = 1000 if reading.attributes["unit_of_measurement"] == "Wh" else 1
    await set_state(hass, status, charging)
    await clock.advance(hours=1)
    await set_state(hass, counter, str(float(reading.state) + 7 * per_kwh))
    await set_state(hass, status, unplugged)
    await clock.advance(minutes=10)

    [run] = (await panel.call("coinop/runs/list"))["runs"]
    assert run["outcome"] == "completed"
    run = (await panel.call("coinop/runs/get", run_id=run["id"]))["run"]
    [electricity] = [i for i in run["line_items"] if i["kind"] == "electricity"]
    assert electricity["quantity"] == pytest.approx(7)


async def test_the_next_scenario_takes_the_stand_ins_devices_away(
    hass: HomeAssistant,
    hass_admin_user: MockUser,
    helpers: None,
    files: Path,
) -> None:
    stand_ins = {
        "anycubic": 1,
        "anycubic_cloud": 1,
        "bambu_lab": 1,
        "prusalink": 1,
        "octoprint": 1,
        "ha_creality_ws": 1,
        "elegoo_printer": 1,
        "moonraker": 1,
        "ha_washdata": 2,
        "tesla_wall_connector": 1,
        **{piece.split(".")[0]: 1 for piece in EV_CHARGERS},
    }
    await async_load(hass, "quick-start", hass_admin_user)
    assert {d: len(hass.config_entries.async_entries(d)) for d in stand_ins} == (
        stand_ins
    )

    await async_load(hass, "empty", hass_admin_user)

    assert not any(hass.config_entries.async_entries(d) for d in stand_ins)
    assert not any(hass.states.get(status) for _, _, _, status, *_ in STATIC.values())
    assert not any(hass.states.get(status) for _, status, _ in EV_CHARGER_DEVICES)


@pytest.mark.usefixtures("helpers")
async def test_the_next_scenario_resets_the_helpers_left_running(
    hass: HomeAssistant, hass_admin_user: MockUser, files: Path
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    running: dict[str, str | float] = {
        "input_select.prusa_status": "printing",
        "input_text.prusa_job": "Benchy.gcode",
        "input_select.kobra_status": "printing",
        "input_number.kobra_power": 120,
        "input_select.voron_status": "printing",
        "input_number.voron_filament": 3.2,
        "input_number.p1s_power": 120,
        "input_select.washer_status": "running",
        "input_select.washdata_dishwasher_status": "running",
        "input_select.irrigation_status": "watering",
        "input_select.wall_connector_status": "charging",
    }
    for entity_id, value in running.items():
        await set_helper(hass, entity_id, value)

    await async_load(hass, "empty", hass_admin_user)

    assert {entity_id: state(hass, entity_id) for entity_id in running} == {
        "input_select.prusa_status": "idle",
        "input_text.prusa_job": "",
        "input_select.kobra_status": "idle",
        "input_number.kobra_power": "0.0",
        "input_select.voron_status": "standby",
        "input_number.voron_filament": "0.0",
        "input_number.p1s_power": "0.0",
        "input_select.washer_status": "off",
        "input_select.washdata_dishwasher_status": "off",
        "input_select.irrigation_status": "off",
        "input_select.wall_connector_status": "not_connected",
    }


@pytest.mark.usefixtures("helpers")
async def test_the_next_scenario_sets_a_static_stand_ins_status_back(
    hass: HomeAssistant, hass_admin_user: MockUser, files: Path
) -> None:
    await async_load(hass, "quick-start", hass_admin_user)
    await set_state(hass, "sensor.p1s_print_status", "running")

    await async_load(hass, "quick-start", hass_admin_user)

    assert state(hass, "sensor.p1s_print_status") == "idle"


async def quick_start(hass: HomeAssistant, label: str, **answers: Any) -> None:
    """Add the HA device Quick Start offers as `label`."""
    [entry] = hass.config_entries.async_entries("coinop")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "quick_start"
    devices = {option["label"]: option["value"] for option in offered(result)}
    assert list(devices) == [
        "Anycubic Kobra S1 · Anycubic 3D Printer - Local Control",
        "Kobra S1 · Anycubic Cloud & LAN",
        "P1S · Bambu Lab",
        "Prusa Core One · PrusaLink",
        "OctoPrint · OctoPrint",
        "K1C · Creality",
        "Centauri Carbon · Elegoo",
        "Voron 2.4 · Moonraker",
        "Washing machine · WashData",
        "Dishwasher · WashData",
        "Tesla Wall Connector · Tesla Wall Connector",
        *(label for label, _, _ in EV_CHARGER_DEVICES),
        "manual",
    ]
    result = await configure(hass, result, {"device": devices[label]})
    result = await configure(hass, result, answers)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")


def state(hass: HomeAssistant, entity_id: str) -> str:
    current = hass.states.get(entity_id)
    assert current is not None
    return current.state


async def set_helper(hass: HomeAssistant, entity_id: str, value: str | float) -> None:
    domain = entity_id.split(".")[0]
    service, field = (
        ("select_option", "option")
        if domain == "input_select"
        else ("set_value", "value")
    )
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, field: value}, blocking=True
    )
    await hass.async_block_till_done()


async def set_state(hass: HomeAssistant, entity_id: str, value: str) -> None:
    """An event entity's state is when it fired; the event is its `event_type`."""
    current = hass.states.get(entity_id)
    assert current is not None
    attributes = dict(current.attributes)
    if entity_id.startswith("event."):
        attributes["event_type"] = value
        value = dt_util.utcnow().isoformat()
    hass.states.async_set(entity_id, value, attributes)
    await hass.async_block_till_done()
