"""After setup: WattBill's own HA device per Device, renaming and removing Devices."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .devices import add_device, add_hub, add_printer
from .test_runs import TOTAL_COST


def wattbill_device(hass: HomeAssistant, entity_id: str = TOTAL_COST) -> dr.DeviceEntry:
    entity = er.async_get(hass).async_get(entity_id)
    assert entity is not None, entity_id
    assert entity.device_id is not None, entity_id
    device = dr.async_get(hass).async_get(entity.device_id)
    assert isinstance(device, dr.DeviceEntry), entity_id
    return device


async def test_a_devices_entities_sit_on_its_own_ha_device_linked_to_the_printer(
    hass: HomeAssistant,
) -> None:
    printer = add_printer(hass, "Kobra S1")
    entry = await add_hub(hass)

    await add_device(hass, entry, name="Kobra", printer=printer.id)

    device = wattbill_device(hass)
    assert device.id != printer.id
    assert device.name == "Kobra"
    assert device.via_device_id == printer.id
    assert wattbill_device(hass, "sensor.kobra_runs") == device


async def test_without_a_printer_device_the_ha_device_stands_alone(
    hass: HomeAssistant,
) -> None:
    entry = await add_hub(hass)

    await add_device(hass, entry, name="Kobra")

    device = wattbill_device(hass)
    assert device.name == "Kobra"
    assert device.via_device_id is None
