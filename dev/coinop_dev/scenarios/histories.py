"""How each Device with history gets its Runs: through the websocket commands or by
replaying its helpers' states with past timestamps."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
import random
from typing import Any

from homeassistant.core import HomeAssistant

from .data import (
    IRRIGATION_WATER,
    LAUNDRY,
    LOADS,
    MATERIALS,
    MOWS,
    OVEN_PROGRAMS,
    PARTS,
    SESSIONS,
    TAGS,
    WASHER_METERS,
    WATERINGS,
    Charge,
    Cycle,
    Load,
    Mow,
    Watering,
)
from .seed import Seed, async_set, replay, replay_meters


async def prusa(seed: Seed) -> None:
    black, white, red = (name for name, *_ in MATERIALS[:3])

    def ago(days: int) -> datetime:
        return seed.now - timedelta(days=days)

    customer = ["Customer Miller", "Electronics"]
    add = seed.add_run
    await add(
        "prusa", "Benchy", ago(48), 1.2, tags=["Prototypes"], material=black, grams=14
    )
    await add(
        "prusa",
        "Desk cable holder",
        ago(42),
        2.6,
        tags=["Household"],
        material=black,
        grams=38,
    )
    await add(
        "prusa",
        "Sensor box enclosure",
        ago(35),
        6.7,
        tags=customer,
        material=white,
        grams=112,
        note="Lid printed separately.",
    )
    await add(
        "prusa",
        "Sensor box enclosure v2",
        ago(33),
        1.2,
        "failed",
        tags=customer,
        material=white,
        grams=21,
    )
    await add(
        "prusa", "Plant pot", ago(26), 15.5, tags=["Garden"], material=red, grams=260
    )
    await add(
        "prusa",
        "Dishwasher spare part",
        ago(9),
        0.7,
        "cancelled",
        tags=["Household"],
        material=black,
        grams=6,
    )
    await add(
        "prusa",
        "Camera mount",
        ago(2),
        3.3,
        tags=["Customer Miller"],
        material=red,
        grams=54,
        parts=2,
    )


async def bambu(seed: Seed) -> None:
    rng = seed.random
    names = [name for name, *_ in MATERIALS[:5]]
    for day in sorted(rng.sample(range(1, 42), 10), reverse=True):
        hours = round(rng.uniform(0.5, 9), 1)
        await seed.add_run(
            "bambu",
            rng.choice(PARTS),
            seed.now - timedelta(days=day, hours=rng.randrange(12)),
            hours,
            rng.choices(["completed", "failed", "cancelled"], [90, 6, 4])[0],
            tags=rng.sample(TAGS, rng.choice([0, 1, 2])),
            material=rng.choice(names),
            grams=round(hours * rng.uniform(8, 18), 1),
        )


async def printer_years(seed: Seed, printer: str, gaps: Sequence[int]) -> None:
    """Two years of Runs, `gaps` days apart."""
    box = seed.templates["Shipping box"]
    rng = seed.random
    names = [name for name, *_ in MATERIALS]
    day = 730
    while (day := day - rng.choice(gaps)) > 0:
        started = (
            seed.now
            - timedelta(days=day, hours=rng.randrange(14))
            - timedelta(hours=10)
        )
        hours = round(rng.lognormvariate(1.0, 0.8), 1) + 0.2
        outcome = rng.choices(["completed", "failed", "cancelled"], [88, 7, 5])[0]
        part = rng.choice(PARTS)
        material = rng.choice(names[:-1] if day < 200 else names)
        weighed = rng.random() > 0.02
        run = await seed.add_run(
            printer,
            part if rng.random() > 0.2 else f"{part} v{rng.randrange(2, 5)}",
            started,
            hours,
            outcome,
            tags=rng.sample(TAGS, rng.choice([0, 1, 1, 1, 2])),
            material=material,
            grams=round(hours * rng.uniform(8, 18), 1) if weighed else None,
            note="Customer pickup on Friday." if rng.random() < 0.05 else None,
            parts=rng.choice([2, 4, 6]) if rng.random() < 0.1 else None,
            thumbnail=rng.random() < 0.7,
        )
        if rng.random() < 0.1:
            await seed.api.call(
                "coinop/line_items/add_template",
                run_id=run["id"],
                template_id=box["id"],
            )
    # TPU went unused for the last 200 days.
    seed.retired.add(names[-1])


async def washer_settings(seed: Seed) -> None:
    detergent, softener, whitener, sheets = (
        seed.materials[name]["id"] for name, *_ in LAUNDRY
    )
    await seed.api.call(
        "coinop/devices/update_settings",
        device_id=seed.devices["washer"],
        settings={
            "doses": [
                {
                    "id": "detergent",
                    "material_id": detergent,
                    "stock": {"entity_id": "input_number.detergent_scale"},
                },
                {"id": "softener", "material_id": softener},
                {"id": "whitener", "material_id": whitener},
                {"id": "sheets", "material_id": sheets},
            ],
            "program_defaults": {
                "default": {
                    "kwh": 0.9,
                    "litres": 50,
                    "doses": {"detergent": 75, "softener": 30},
                },
                "programs": {
                    "Cotton 60°": {
                        "kwh": 1.1,
                        "litres": 56,
                        "doses": {
                            "detergent": 75,
                            "softener": 30,
                            "whitener": 20,
                            "sheets": 1,
                        },
                    },
                    "Eco 40-60": {
                        "kwh": 0.72,
                        "litres": 48,
                        "doses": {"detergent": 70, "softener": 30},
                    },
                    "Wool": {"kwh": 0.4, "litres": 45, "doses": {"detergent": 40}},
                },
            },
        },
    )


async def oven_settings(seed: Seed) -> None:
    await seed.api.call(
        "coinop/devices/update_settings",
        device_id=seed.devices["oven"],
        settings={
            "program_defaults": {
                "default": {"doses": {}, "kwh": 1.0},
                "programs": {
                    program: {"doses": {}, "kwh": kwh}
                    for program, kwh in OVEN_PROGRAMS.items()
                },
            }
        },
    )


async def set_doses(
    seed: Seed, device: str, doses: Mapping[str, str], defaults: Mapping[str, Any]
) -> None:
    """Gives `device` a Dose of each Material named in `doses`, by Dose id, and the
    Program Defaults `defaults`."""
    await seed.api.call(
        "coinop/devices/update_settings",
        device_id=seed.devices[device],
        settings={
            "doses": [
                {"id": dose, "material_id": seed.materials[name]["id"]}
                for dose, name in doses.items()
            ],
            "program_defaults": defaults,
        },
    )


def _days(
    rng: random.Random, gaps: Sequence[int], first: int = 730, last: int = 30
) -> Iterator[int]:
    """Every few days, `gaps` apart, from `first` days ago until `last` days ago."""
    day = first
    while day > last:
        yield day
        day -= rng.choice(gaps)


def _summers(rng: random.Random, gaps: Sequence[int], last: int) -> Iterator[int]:
    """Every few days through the last two summers, from day 300 of their year back
    to day `last`."""
    for summer in (1, 0):
        yield from _days(rng, gaps, 365 * summer + 300, 365 * summer + last)


def _typical[C: (Load, Cycle)](cycles: Iterable[C]) -> dict[str | None, C]:
    """A finished cycle of each Program, which a long history repeats."""
    return {cycle.program: cycle for cycle in cycles if cycle.outcome == "finished"}


def _vary(
    rng: random.Random, amount: float, share: float = 1, by: float = 0.1
) -> float:
    return amount * share * rng.uniform(1 - by, 1 + by)


def _outcome(rng: random.Random, cancelled: int = 5) -> tuple[str, float]:
    """An Outcome, and the share of its cycle a cancelled one ran."""
    outcome = rng.choices(["finished", "cancelled"], [100 - cancelled, cancelled])[0]
    return outcome, rng.uniform(0.2, 0.6) if outcome == "cancelled" else 1


async def _end(
    hass: HomeAssistant,
    status: str,
    outcome: str,
    end: datetime,
    meters: Mapping[str, float],
) -> None:
    await replay(hass, status, outcome, end)
    # A report after the end spares the wait for it.
    await replay_meters(hass, meters, end + timedelta(minutes=1))


async def wash(seed: Seed, loads: Iterable[Load]) -> None:
    hass, meters = seed.hass, dict(WASHER_METERS)
    program, status = "input_select.washer_program", "input_select.washer_status"
    for load in loads:
        if meters["detergent_scale"] < load.grams:
            # A new bottle; a refill between loads counts nothing.
            meters["detergent_scale"] += 1500
        start = seed.now.replace(hour=9, minute=30) - timedelta(days=load.days_ago)
        end = start + timedelta(minutes=load.minutes)
        known = None if load.recognised else load.program
        await replay(hass, program, known or "", start)
        await replay_meters(hass, meters, start)
        await replay(hass, status, "running", start)
        meters["detergent_scale"] -= load.grams
        await replay_meters(hass, meters, start + timedelta(minutes=3))
        if load.program and load.recognised:
            at = start + timedelta(minutes=load.recognised)
            await replay(hass, program, load.program, at)
        meters["washer_energy"] = round(meters["washer_energy"] + load.kwh, 3)
        meters["washer_water"] = round(meters["washer_water"] + load.litres, 1)
        await replay_meters(hass, meters, end - timedelta(minutes=2))
        await _end(hass, status, load.outcome, end, meters)
    for key, value in meters.items():
        await async_set(hass, f"input_number.{key}", value)
    await async_set(hass, program, "Wool")
    await async_set(hass, status, "off")


async def washer_long(seed: Seed) -> None:
    """A load every few days for two years, then the short level's."""
    rng = seed.random
    typical = _typical(LOADS)
    loads = []
    for day in _days(rng, range(4, 11)):
        usual = typical[rng.choice(list(typical))]
        outcome, share = _outcome(rng)
        loads.append(
            Load(
                day,
                usual.program,
                0,
                round(_vary(rng, usual.minutes, share, by=0.05)),
                round(_vary(rng, usual.kwh, share), 2),
                round(_vary(rng, usual.litres, share), 1),
                round(_vary(rng, usual.grams)),
                outcome,
            )
        )
    await wash(seed, [*loads, *LOADS])


async def replay_cycles(
    seed: Seed, key: str, meters: Mapping[str, float], cycles: Iterable[Cycle]
) -> None:
    """Replays each cycle on the helpers named `key`: its Program, its Status from
    running to its Outcome and its meters counting."""
    hass, readings = seed.hass, dict(meters)
    status = f"input_select.{key}_status"
    for cycle in cycles:
        start = seed.now.replace(hour=cycle.hour, minute=0) - timedelta(
            days=cycle.days_ago
        )
        length = timedelta(minutes=cycle.minutes)
        await replay(hass, f"input_select.{key}_program", cycle.program or "", start)
        await replay_meters(hass, readings, start)
        await replay(hass, status, "running", start)
        for meter, amount in zip(readings, cycle.counted, strict=True):
            readings[meter] = round(readings[meter] + amount, 3)
        await replay_meters(hass, readings, start + length * 0.9)
        await _end(hass, status, cycle.outcome, start + length, readings)
    for meter, value in readings.items():
        await async_set(hass, f"input_number.{meter}", value)
    await async_set(hass, status, "off")


async def replay_years(
    seed: Seed,
    key: str,
    meters: Mapping[str, float],
    cycles: Sequence[Cycle],
    gaps: Sequence[int],
    hours: Sequence[int],
) -> None:
    """A cycle every few days from two years ago to a month ago on the Programs of
    `cycles`, a few cancelled part of the way, then `cycles`."""
    rng = seed.random
    typical = _typical(cycles)
    years = []
    for day in _days(rng, gaps):
        usual = typical[rng.choice(list(typical))]
        outcome, share = _outcome(rng)
        years.append(
            Cycle(
                day,
                rng.choice(hours),
                usual.program,
                round(_vary(rng, usual.minutes, share, by=0.05), 1),
                outcome,
                tuple(round(_vary(rng, amount, share), 3) for amount in usual.counted),
            )
        )
    await replay_cycles(seed, key, meters, [*years, *cycles])


async def charge(seed: Seed, sessions: Iterable[Charge]) -> None:
    """Each session counted from 0, as a session energy sensor counts it; the
    sensor drops back to 0 five minutes after the car is unplugged."""
    hass = seed.hass
    status, meter = "input_select.carport_charger_status", "carport_charger_session"
    session = f"input_number.{meter}"
    for charging in sessions:
        start = seed.now.replace(hour=charging.hour, minute=0) - timedelta(
            days=charging.days_ago
        )
        await replay(hass, session, 0, start)
        await replay(hass, status, "charging", start)
        halfway = start + timedelta(minutes=charging.charging // 2)
        await replay(hass, session, round(charging.kwh / 2, 1), halfway)
        charged = start + timedelta(minutes=charging.charging)
        await replay(hass, session, charging.kwh, charged)
        if charging.full:
            await replay(hass, status, "connected", charged)
        end = charged + timedelta(minutes=charging.full)
        await _end(hass, status, "disconnected", end, {meter: charging.kwh})
        await replay(hass, session, 0, end + timedelta(minutes=5))
    await async_set(hass, session, 0)
    await async_set(hass, status, "disconnected")


async def charger_long(seed: Seed) -> None:
    """A charge every few days for two years, then the short level's."""
    rng = seed.random
    years = []
    for day in _days(rng, range(2, 7)):
        kwh = round(rng.uniform(8, 48), 1)
        # 11 kW, a little less at the end.
        minutes = round(kwh / 10 * 60)
        full = rng.choice([0, 0, 240, 480, 600])
        years.append(Charge(day, rng.choice([18, 19, 20, 21]), minutes, full, kwh))
    await charge(seed, [*years, *SESSIONS])


async def mow(seed: Seed, mows: Iterable[Mow]) -> None:
    """Charging after mowing is Paused, so what the station draws lands in the Run."""
    hass = seed.hass
    status, meter = "input_select.robotic_mower_status", "robotic_mower_station_energy"
    readings = {meter: 85.0}
    for mowing in mows:
        start = seed.now.replace(hour=mowing.hour, minute=0) - timedelta(
            days=mowing.days_ago
        )
        await replay_meters(hass, readings, start)
        await replay(hass, status, "mowing", start)
        if mowing.stuck:
            at = start + timedelta(minutes=mowing.minutes // 2)
            await replay(hass, status, "error", at)
            await replay(hass, status, "mowing", at + timedelta(minutes=mowing.stuck))
        back = start + timedelta(minutes=mowing.minutes + mowing.stuck)
        await replay(hass, status, "returning", back)
        docked = back + timedelta(minutes=5)
        await replay(hass, status, "charging", docked)
        end = docked + timedelta(minutes=mowing.charging)
        readings[meter] = round(readings[meter] + mowing.kwh, 3)
        await replay_meters(hass, readings, end - timedelta(minutes=1))
        await _end(hass, status, "parked", end, readings)
    await async_set(hass, f"input_number.{meter}", readings[meter])
    await async_set(hass, status, "parked")


async def mower_long(seed: Seed) -> None:
    """Every few days through two summers, then the short level's mows."""
    rng = seed.random
    summers = []
    for day in _summers(rng, range(1, 4), 120):
        minutes = rng.randrange(70, 120, 5)
        kwh = round(minutes / 360 * rng.uniform(0.9, 1.1), 2)
        stuck = rng.choice([20, 35]) if rng.random() < 0.05 else 0
        summers.append(Mow(day, rng.choice([9, 10, 14, 15]), minutes, 70, kwh, stuck))
    await mow(seed, [*summers, *MOWS])


async def water(seed: Seed, waterings: Iterable[Watering]) -> None:
    hass, meter = seed.hass, "irrigation_water"
    status, readings = "input_select.irrigation_status", {meter: IRRIGATION_WATER}
    for watering in waterings:
        start = seed.now.replace(hour=watering.hour, minute=0) - timedelta(
            days=watering.days_ago
        )
        end = start + timedelta(minutes=watering.minutes)
        await replay_meters(hass, readings, start)
        await replay(hass, status, "watering", start)
        readings[meter] = round(readings[meter] + watering.litres, 1)
        await replay_meters(hass, readings, end - timedelta(minutes=1))
        await _end(hass, status, "off", end, readings)
    await async_set(hass, f"input_number.{meter}", readings[meter])
    await async_set(hass, status, "off")


async def irrigation_long(seed: Seed) -> None:
    """Every few days through two summers, then the short level's waterings."""
    rng = seed.random
    summers = []
    for day in _summers(rng, range(2, 5), 140):
        minutes = rng.choice([15, 20, 20, 25, 35])
        litres = round(minutes * rng.uniform(8, 9.5), 1)
        summers.append(Watering(day, 20 if minutes > 30 else 6, minutes, litres))
    await water(seed, [*summers, *WATERINGS])
