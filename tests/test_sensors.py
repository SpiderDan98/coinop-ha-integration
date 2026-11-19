"""Per-Device sensors: totals for long-term statistics, current and last Run."""

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
import pytest

from .clock import Clock
from .devices import add_device, add_hub
from .test_runs import set_status, value


@pytest.mark.parametrize(
    ("entity_id", "device_class", "unit"),
    [
        ("sensor.kobra_total_cost", "monetary", "EUR"),
        ("sensor.kobra_electricity_cost", "monetary", "EUR"),
        ("sensor.kobra_material_cost", "monetary", "EUR"),
        ("sensor.kobra_other_cost", "monetary", "EUR"),
        ("sensor.kobra_material_used", "weight", "g"),
        ("sensor.kobra_energy_in_runs", "energy", "kWh"),
    ],
)
async def test_totals_are_statistics_capable(
    hass: HomeAssistant, clock: Clock, entity_id: str, device_class: str, unit: str
) -> None:
    hass.config.currency = "EUR"
    entry = await add_hub(hass)
    await add_device(hass, entry)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0.0"
    assert {
        key: state.attributes.get(key)
        for key in ("device_class", "state_class", ATTR_UNIT_OF_MEASUREMENT)
    } == {
        "device_class": device_class,
        "state_class": "total",
        ATTR_UNIT_OF_MEASUREMENT: unit,
    }


async def test_totals_split_the_cost_by_kind_and_count_energy(
    hass: HomeAssistant, clock: Clock
) -> None:
    entry = await add_hub(hass)
    await add_device(hass, entry, running_power=100, price=0.5)

    await set_status(hass, "printing")
    await clock.advance(hours=2)

    assert value(hass, "sensor.kobra_energy_in_runs") == pytest.approx(0.2)
    assert value(hass, "sensor.kobra_electricity_cost") == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_total_cost") == pytest.approx(0.1)
    assert value(hass, "sensor.kobra_material_cost") == 0
    assert value(hass, "sensor.kobra_other_cost") == 0
    assert value(hass, "sensor.kobra_material_used") == 0
