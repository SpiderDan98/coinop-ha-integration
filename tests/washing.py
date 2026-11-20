"""Washing machines set up through Add Device, and loads run on them."""

from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from .clock import Clock
from .devices import WASHER_ENERGY, WASHER_STATUS, add_hub, add_washing_machine
from .stored import place_materials, stored_material

WASHER_PROGRAM = "sensor.washer_program"


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


async def set_washer(hass: HomeAssistant, status: str) -> None:
    hass.states.async_set(WASHER_STATUS, status)
    await hass.async_block_till_done()


async def set_energy(hass: HomeAssistant, kwh: float | str) -> None:
    hass.states.async_set(WASHER_ENERGY, str(kwh), {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()


async def set_program(
    hass: HomeAssistant, program: str, attributes: dict[str, Any] | None = None
) -> None:
    hass.states.async_set(WASHER_PROGRAM, program, attributes)
    await hass.async_block_till_done()


async def add_washer(
    hass: HomeAssistant,
    hass_storage: dict[str, Any] | None = None,
    *,
    program: bool = True,
    source: str = "energy",
    **options: Any,
) -> ConfigSubentry:
    """A washing machine, off, in EUR. `hass_storage` places the laundry Materials;
    `program` gives it a Program input on `WASHER_PROGRAM` (with no Program yet); an
    energy meter starts at 100 kWh. `options` go to `add_washing_machine`."""
    hass.config.currency = "EUR"
    if hass_storage is not None:
        place_materials(hass_storage, LIQUID, PODS, WHITENER)
    if source == "energy":
        await set_energy(hass, 100)
    await set_washer(hass, "off")
    if program:
        await set_program(hass, "unknown")
        options["program"] = {"entity_id": WASHER_PROGRAM}
    return await add_washing_machine(
        hass, await add_hub(hass), source=source, **options
    )


async def washed(
    hass: HomeAssistant,
    clock: Clock,
    program: str | None = None,
    *,
    outcome: str = "finished",
    kwh: float | None = None,
) -> None:
    """A 90-minute load ended as `outcome`, on `program` if given; with `kwh` the
    energy meter counts it and reports again at the end, which finalises the Run."""
    if program is not None:
        await set_program(hass, program)
    start = 0.0
    if kwh is not None:
        meter = hass.states.get(WASHER_ENERGY)
        assert meter is not None
        start = float(meter.state)
    await set_washer(hass, "running")
    await clock.advance(minutes=90)
    if kwh is not None:
        await set_energy(hass, start + kwh)
    await set_washer(hass, outcome)
    if kwh is not None:
        await set_energy(hass, start + kwh)
