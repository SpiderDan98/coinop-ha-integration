"""The dev container's Scenarios load through today's websocket API."""

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from dev.coinop_dev.scenarios import async_load

from .websocket import PanelClient

CONFIG = Path(__file__).parents[1] / "dev" / "configuration.yaml"


@pytest.fixture
async def helpers(hass: HomeAssistant) -> None:
    """The printers' helpers from the dev configuration.yaml."""
    config = await hass.async_add_executor_job(load_yaml_dict, CONFIG)
    for domain in ("input_select", "input_text"):
        assert await async_setup_component(hass, domain, {domain: config[domain]})


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
        ("few-runs", (1, 3, 7, 0)),
        ("printing-now", (1, 3, 8, 1)),
        ("two-printers", (2, 5, 60, 0)),
    ],
)
async def test_a_scenario_fills_coinop_from_scratch(
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
