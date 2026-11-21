"""The dev container's Spoolman, filled afresh by every load over its REST API."""

from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .data import DENSITY, MATERIALS, SPOOLMAN_ONLY, SPOOLS
from .seed import ScenarioError

# The container scripts/devenv.py starts next to Home Assistant, on their network.
URL = "http://coinop-dev-spoolman:8000"
_TIMEOUT = ClientTimeout(total=10)


async def async_fill(hass: HomeAssistant) -> dict[str, int]:
    """Replace whatever Spoolman holds by the test data; returns each Filament's id
    by its Material's name."""
    session = async_get_clientsession(hass)

    async def call(method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with session.request(
                method, f"{URL}/api/v1/{path}", timeout=_TIMEOUT, **kwargs
            ) as response:
                response.raise_for_status()
                return await response.json()
        except (ClientError, TimeoutError) as err:
            raise ScenarioError(f"Spoolman at {URL}: {err!r}") from err

    # A Filament with spools can't be deleted; a vendor's Filaments lose it.
    for kind, params in (
        ("spool", {"allow_archived": "true"}),
        ("filament", {}),
        ("vendor", {}),
    ):
        for record in await call("GET", kind, params=params):
            await call("DELETE", f"{kind}/{record['id']}")
    filaments = [*MATERIALS, *SPOOLMAN_ONLY]
    vendors = {
        vendor: (await call("POST", "vendor", json={"name": vendor}))["id"]
        for vendor in dict.fromkeys(vendor for *_, vendor, _ in filaments if vendor)
    }
    ids = {}
    for name, type_, colour, vendor, price in filaments:
        spools = SPOOLS.get(name, [])
        hexes = [hex.lstrip("#") for hex in colour.split(",")]
        colours = (
            {"multi_color_hexes": ",".join(hexes), "multi_color_direction": "coaxial"}
            if len(hexes) > 1
            else {"color_hex": hexes[0]}
        )
        filament = {
            "name": name.removeprefix(f"{vendor} ") if vendor else name,
            "vendor_id": vendors[vendor] if vendor else None,
            "material": type_,
            "price": None if any(s.price for s in spools) else price,
            "density": DENSITY[type_],
            "diameter": 1.75,
            "weight": 1000,
        } | colours
        ids[name] = (await call("POST", "filament", json=filament))["id"]
        for spool in spools:
            await call(
                "POST",
                "spool",
                json={
                    "filament_id": ids[name],
                    "remaining_weight": spool.remaining,
                    "location": spool.location,
                    "price": spool.price,
                    "archived": spool.archived,
                },
            )
    return ids
