"""How each Device with history gets its Runs: through the websocket commands or by
replaying its helpers' states with past timestamps."""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

from .data import (
    COOKINGS,
    DISHES,
    DISHWASHER_METERS,
    DRINKS,
    DRYER_METERS,
    IRRIGATION_WATER,
    LAUNDRY,
    LOADS,
    MATERIALS,
    MOWS,
    OVEN_PROGRAMS,
    PARTS,
    SESSIONS,
    TAGS,
    TUMBLES,
    TYPICAL,
    TYPICAL_DISHES,
    TYPICAL_DRINKS,
    TYPICAL_TUMBLES,
    WASHER_METERS,
    WATERINGS,
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


async def _long_history(seed: Seed, printer: str, gaps: list[int]) -> None:
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


async def prusa_long(seed: Seed) -> None:
    await _long_history(seed, "prusa", [1, 2, 3, 4, 5, 6])


async def bambu_long(seed: Seed) -> None:
    await _long_history(seed, "bambu", [3, 4, 5, 6, 7, 8, 9])


async def prusa_start(seed: Seed) -> None:
    await seed.set_printer("prusa", "printing", "Gridfinity bins 3x2.gcode")


async def bambu_start(seed: Seed) -> None:
    await seed.set_printer("bambu", "printing", "Spool holder.gcode")


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


async def washer_short(seed: Seed) -> None:
    await _wash(seed, LOADS)


async def washer_long(seed: Seed) -> None:
    """A load every few days for two years, then the short level's."""
    rng = seed.random
    loads, day = [], 730
    while day > 30:
        program = rng.choice([*TYPICAL, None])
        minutes, kwh, litres, grams = TYPICAL[program or "Cotton 60°"]
        outcome = rng.choices(["finished", "cancelled"], [95, 5])[0]
        share = rng.uniform(0.2, 0.6) if outcome == "cancelled" else 1
        loads.append(
            (
                day,
                program,
                0,
                round(minutes * share * rng.uniform(0.95, 1.05)),
                round(kwh * share * rng.uniform(0.9, 1.1), 2),
                round(litres * share * rng.uniform(0.9, 1.1), 1),
                round(grams * rng.uniform(0.9, 1.1)),
                outcome,
            )
        )
        day -= rng.randrange(4, 11)
    await _wash(seed, [*loads, *LOADS])


async def _wash(seed: Seed, loads: list[tuple[Any, ...]]) -> None:
    meters = dict(WASHER_METERS)
    for days, program, recognised, minutes, kwh, litres, grams, outcome in loads:
        if meters["detergent_scale"] < grams:
            # A new bottle; a refill between loads counts nothing.
            meters["detergent_scale"] += 1500
        start = seed.now.replace(hour=9, minute=30) - timedelta(days=days)
        end = start + timedelta(minutes=minutes)
        known = None if recognised else program
        await replay(seed.hass, "input_select.washer_program", known or "", start)
        await replay_meters(seed.hass, meters, start)
        await replay(seed.hass, "input_select.washer_status", "running", start)
        meters["detergent_scale"] -= grams
        await replay_meters(seed.hass, meters, start + timedelta(minutes=3))
        if program and recognised:
            at = start + timedelta(minutes=recognised)
            await replay(seed.hass, "input_select.washer_program", program, at)
        meters["washer_energy"] = round(meters["washer_energy"] + kwh, 3)
        meters["washer_water"] = round(meters["washer_water"] + litres, 1)
        await replay_meters(seed.hass, meters, end - timedelta(minutes=2))
        await replay(seed.hass, "input_select.washer_status", outcome, end)
        # Reports after the end spare the wait for them.
        await replay_meters(seed.hass, meters, end + timedelta(minutes=1))
    for key, value in meters.items():
        await async_set(seed.hass, f"input_number.{key}", value)
    await async_set(seed.hass, "input_select.washer_program", "Wool")
    await async_set(seed.hass, "input_select.washer_status", "off")


async def washer_start(seed: Seed) -> None:
    await async_set(seed.hass, "input_select.washer_program", "Cotton 60°")
    await async_set(seed.hass, "input_select.washer_status", "running")


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


async def oven_short(seed: Seed) -> None:
    await _cook(seed, COOKINGS)


async def oven_long(seed: Seed) -> None:
    """A meal every few days for two years, then the short level's."""
    rng = seed.random
    cookings, day = [], 730
    while day > 30:
        outcome = rng.choices(["finished", "cancelled"], [96, 4])[0]
        cookings.append(
            (
                day,
                rng.choice([12, 13, 17, 18, 19]),
                rng.choice([*OVEN_PROGRAMS, None]),
                rng.randrange(20, 95, 5),
                outcome,
            )
        )
        day -= rng.randrange(3, 10)
    await _cook(seed, [*cookings, *COOKINGS])


async def _cook(seed: Seed, cookings: list[tuple[Any, ...]]) -> None:
    for days, hour, program, minutes, outcome in cookings:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        await replay(
            seed.hass, "input_select.kitchen_oven_program", program or "", start
        )
        await replay(seed.hass, "input_select.kitchen_oven_status", "running", start)
        end = start + timedelta(minutes=minutes)
        await replay(seed.hass, "input_select.kitchen_oven_status", outcome, end)
    await async_set(seed.hass, "input_select.kitchen_oven_program", "Fan plus 180°")
    await async_set(seed.hass, "input_select.kitchen_oven_status", "off")


async def oven_start(seed: Seed) -> None:
    await async_set(seed.hass, "input_select.kitchen_oven_program", "Pizza 220°")
    await async_set(seed.hass, "input_select.kitchen_oven_status", "running")


async def charger_short(seed: Seed) -> None:
    await _charge(seed, SESSIONS)


async def charger_long(seed: Seed) -> None:
    """A charge every few days for two years, then the short level's."""
    rng = seed.random
    sessions, day = [], 730
    while day > 30:
        kwh = round(rng.uniform(8, 48), 1)
        # 11 kW, a little less at the end.
        charging = round(kwh / 10 * 60)
        full = rng.choice([0, 0, 240, 480, 600])
        sessions.append((day, rng.choice([18, 19, 20, 21]), charging, full, kwh))
        day -= rng.randrange(2, 7)
    await _charge(seed, [*sessions, *SESSIONS])


async def _charge(seed: Seed, sessions: list[tuple[int, int, int, int, float]]) -> None:
    """Each session counted from 0, as a session energy sensor counts it; the
    sensor drops back to 0 five minutes after the car is unplugged."""
    hass = seed.hass
    status, session = (
        "input_select.carport_charger_status",
        "input_number.carport_charger_session",
    )
    for days, hour, charging, full, kwh in sessions:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        await replay(hass, session, 0, start)
        await replay(hass, status, "charging", start)
        halfway = start + timedelta(minutes=charging // 2)
        await replay(hass, session, round(kwh / 2, 1), halfway)
        charged = start + timedelta(minutes=charging)
        await replay(hass, session, kwh, charged)
        if full:
            await replay(hass, status, "connected", charged)
        end = charged + timedelta(minutes=full)
        await replay(hass, status, "disconnected", end)
        # A report after the end spares the wait for it.
        await replay(hass, session, kwh, end + timedelta(minutes=1))
        await replay(hass, session, 0, end + timedelta(minutes=5))
    await async_set(hass, session, 0)
    await async_set(hass, status, "disconnected")


async def charger_start(seed: Seed) -> None:
    await async_set(seed.hass, "input_select.carport_charger_status", "charging")


async def mower_short(seed: Seed) -> None:
    await _mow(seed, MOWS)


async def mower_long(seed: Seed) -> None:
    """Every few days through two summers, then the short level's mows."""
    rng = seed.random
    mows = []
    for summer in (1, 0):
        day = 365 * summer + 300
        while day > 365 * summer + 120:
            minutes = rng.randrange(70, 120, 5)
            kwh = round(minutes / 360 * rng.uniform(0.9, 1.1), 2)
            stuck = rng.choice([20, 35]) if rng.random() < 0.05 else 0
            mows.append((day, rng.choice([9, 10, 14, 15]), minutes, 70, kwh, stuck))
            day -= rng.randrange(1, 4)
    await _mow(seed, [*mows, *MOWS])


async def _mow(seed: Seed, mows: list[tuple[int, int, int, int, float, int]]) -> None:
    """Charging after mowing is Paused, so what the station draws lands in the Run."""
    hass = seed.hass
    status, meter = (
        "input_select.robotic_mower_status",
        {"robotic_mower_station_energy": 85.0},
    )
    for days, hour, minutes, charging, kwh, stuck in mows:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        await replay_meters(hass, meter, start)
        await replay(hass, status, "mowing", start)
        if stuck:
            at = start + timedelta(minutes=minutes // 2)
            await replay(hass, status, "error", at)
            await replay(hass, status, "mowing", at + timedelta(minutes=stuck))
        back = start + timedelta(minutes=minutes + stuck)
        await replay(hass, status, "returning", back)
        docked = back + timedelta(minutes=5)
        await replay(hass, status, "charging", docked)
        end = docked + timedelta(minutes=charging)
        meter["robotic_mower_station_energy"] = round(
            meter["robotic_mower_station_energy"] + kwh, 3
        )
        await replay_meters(hass, meter, end - timedelta(minutes=1))
        await replay(hass, status, "parked", end)
        # A report after the end spares the wait for it.
        await replay_meters(hass, meter, end + timedelta(minutes=1))
    await async_set(
        hass,
        "input_number.robotic_mower_station_energy",
        meter["robotic_mower_station_energy"],
    )
    await async_set(hass, status, "parked")


async def mower_start(seed: Seed) -> None:
    await async_set(seed.hass, "input_select.robotic_mower_status", "mowing")


async def irrigation_short(seed: Seed) -> None:
    await _water(seed, WATERINGS)


async def irrigation_long(seed: Seed) -> None:
    """Every few days through two summers, then the short level's waterings."""
    rng = seed.random
    waterings = []
    for summer in (1, 0):
        day = 365 * summer + 300
        while day > 365 * summer + 140:
            minutes = rng.choice([15, 20, 20, 25, 35])
            litres = round(minutes * rng.uniform(8, 9.5), 1)
            waterings.append((day, 20 if minutes > 30 else 6, minutes, litres))
            day -= rng.randrange(2, 5)
    await _water(seed, [*waterings, *WATERINGS])


async def _water(seed: Seed, waterings: list[tuple[int, int, int, float]]) -> None:
    meter = {"irrigation_water": IRRIGATION_WATER}
    for days, hour, minutes, litres in waterings:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        end = start + timedelta(minutes=minutes)
        await replay_meters(seed.hass, meter, start)
        await replay(seed.hass, "input_select.irrigation_status", "watering", start)
        meter["irrigation_water"] = round(meter["irrigation_water"] + litres, 1)
        await replay_meters(seed.hass, meter, end - timedelta(minutes=1))
        await replay(seed.hass, "input_select.irrigation_status", "off", end)
        # A report after the end spares the wait for it.
        await replay_meters(seed.hass, meter, end + timedelta(minutes=1))
    await async_set(
        seed.hass, "input_number.irrigation_water", meter["irrigation_water"]
    )
    await async_set(seed.hass, "input_select.irrigation_status", "off")


async def irrigation_start(seed: Seed) -> None:
    await async_set(seed.hass, "input_select.irrigation_status", "watering")


def _years_of(
    seed: Seed,
    typical: Mapping[str, tuple[float, ...]],
    gaps: range,
    hours: tuple[int, ...],
) -> list[tuple[Any, ...]]:
    """A cycle every few days from two years ago to a month ago, in the shape of
    `DISHES`, on `typical`'s Programs; a few are cancelled part of the way."""
    rng = seed.random
    cycles, day = [], 730
    while day > 30:
        program = rng.choice(list(typical))
        minutes, *counted = typical[program]
        outcome = rng.choices(["finished", "cancelled"], [95, 5])[0]
        share = rng.uniform(0.2, 0.6) if outcome == "cancelled" else 1
        cycles.append(
            (
                day,
                rng.choice(hours),
                program,
                round(minutes * share * rng.uniform(0.95, 1.05), 1),
                outcome,
                *(
                    round(amount * share * rng.uniform(0.9, 1.1), 3)
                    for amount in counted
                ),
            )
        )
        day -= rng.choice(gaps)
    return cycles


async def _replay_cycles(
    seed: Seed,
    key: str,
    meters: Mapping[str, float],
    cycles: Iterable[tuple[Any, ...]],
) -> None:
    """Replays each cycle of the shape of `DISHES` on the helpers named `key`: its
    Program, its Status from running to its Outcome and its meters counting."""
    hass, readings = seed.hass, dict(meters)
    for days, hour, program, minutes, outcome, *counted in cycles:
        start = seed.now.replace(hour=hour, minute=0) - timedelta(days=days)
        length = timedelta(minutes=minutes)
        await replay(hass, f"input_select.{key}_program", program, start)
        await replay_meters(hass, readings, start)
        await replay(hass, f"input_select.{key}_status", "running", start)
        for meter, amount in zip(readings, counted, strict=True):
            readings[meter] = round(readings[meter] + amount, 3)
        await replay_meters(hass, readings, start + length * 0.9)
        await replay(hass, f"input_select.{key}_status", outcome, start + length)
        # A report after the end spares the wait for it.
        await replay_meters(hass, readings, start + length + timedelta(minutes=1))
    for meter, value in readings.items():
        await async_set(hass, f"input_number.{meter}", value)
    await async_set(hass, f"input_select.{key}_status", "off")


async def start_cycle(seed: Seed, key: str, program: str) -> None:
    await async_set(seed.hass, f"input_select.{key}_program", program)
    await async_set(seed.hass, f"input_select.{key}_status", "running")


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


async def dishwasher_short(seed: Seed) -> None:
    await _replay_cycles(seed, "dishwasher", DISHWASHER_METERS, DISHES)


async def dishwasher_long(seed: Seed) -> None:
    long = _years_of(seed, TYPICAL_DISHES, range(3, 8), (13, 20, 21))
    await _replay_cycles(seed, "dishwasher", DISHWASHER_METERS, [*long, *DISHES])


async def dryer_short(seed: Seed) -> None:
    await _replay_cycles(seed, "dryer", DRYER_METERS, TUMBLES)


async def dryer_long(seed: Seed) -> None:
    long = _years_of(seed, TYPICAL_TUMBLES, range(4, 11), (10, 11, 18))
    await _replay_cycles(seed, "dryer", DRYER_METERS, [*long, *TUMBLES])


async def coffee_short(seed: Seed) -> None:
    await _replay_cycles(seed, "coffee", {}, DRINKS)


async def coffee_long(seed: Seed) -> None:
    long = _years_of(seed, TYPICAL_DRINKS, range(3, 9), (7, 8, 15))
    await _replay_cycles(seed, "coffee", {}, [*long, *DRINKS])
