"""Spoolman, read directly over its REST API: Filaments priced per gram.

Linked Materials take their price and their type, density, diameter, colour and
vendor from their Filament every time Coin-op reads Spoolman; between reads,
and while Spoolman is unreachable, the last price read applies.
"""

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from .catalog import Catalog
from .materials import Material, MaterialForm, SpoolmanPrice

CONF_SPOOLMAN_URL = "spoolman_url"
_TIMEOUT = ClientTimeout(total=10)


class SpoolmanUnreachable(Exception):
    """Spoolman isn't set up, didn't answer, or answered with something else."""


@dataclass(frozen=True)
class Filament:
    id: int
    name: str | None
    vendor: str | None
    type: str | None
    density: float
    diameter: float
    colour: str | None
    price_per_gram: float | None

    def material_fields(self) -> dict[str, Any]:
        """What a linked Material takes over from its Filament, its price included."""
        return {
            "price": SpoolmanPrice(self.id, self.price_per_gram).as_dict(),
            "form": MaterialForm.FILAMENT,
            "density": self.density,
            "diameter": self.diameter,
            "colour": self.colour,
            "vendor": self.vendor,
        } | ({"type": self.type} if self.type else {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "vendor": self.vendor,
            "type": self.type,
            "density": self.density,
            "diameter": self.diameter,
            "colour": self.colour,
            "price_per_gram": self.price_per_gram,
        }


def _price_per_gram(
    filament: dict[str, Any], spools: list[dict[str, Any]]
) -> float | None:
    """`filament.price ÷ filament.weight`, else the newest priced spool's
    `spool.price ÷ initial_weight` (both are prices of a whole spool)."""
    if (price := filament.get("price")) is not None and filament.get("weight"):
        return float(price) / float(filament["weight"])
    for spool in sorted(
        spools, key=lambda spool: (spool.get("registered") or "", spool["id"])
    )[::-1]:
        weight = spool.get("initial_weight") or filament.get("weight")
        if not spool.get("archived") and spool.get("price") is not None and weight:
            return float(spool["price"]) / float(weight)
    return None


def _colour(filament: dict[str, Any]) -> str | None:
    hexes = filament.get("color_hex") or (filament.get("multi_color_hexes") or "")
    first = hexes.split(",")[0].strip().lstrip("#")[:6]
    return f"#{first.lower()}" if len(first) == 6 else None


def _filament(data: dict[str, Any], spools: list[dict[str, Any]]) -> Filament:
    vendor = data.get("vendor") or {}
    return Filament(
        id=data["id"],
        name=data.get("name"),
        vendor=vendor.get("name"),
        type=(data.get("material") or "").strip() or None,
        density=data["density"],
        diameter=data["diameter"],
        colour=_colour(data),
        price_per_gram=_price_per_gram(data, spools),
    )


async def _async_get(hass: HomeAssistant, url: str, path: str) -> Any:
    parsed = URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise SpoolmanUnreachable
    try:
        async with async_get_clientsession(hass).get(
            f"{url}/api/v1/{path}", timeout=_TIMEOUT
        ) as response:
            response.raise_for_status()
            return await response.json()
    except (ClientError, TimeoutError, ValueError) as err:
        raise SpoolmanUnreachable from err


async def async_check(hass: HomeAssistant, url: str) -> None:
    """Raise SpoolmanUnreachable unless Spoolman answers at `url`."""
    info = await _async_get(hass, url, "info")
    if not isinstance(info, dict) or "version" not in info:
        raise SpoolmanUnreachable


class Spoolman:
    """The Spoolman set in the hub options (if any), and the Materials linked to it."""

    def __init__(self, hass: HomeAssistant, url: str | None, catalog: Catalog) -> None:
        self._hass = hass
        self.url = url
        self._catalog = catalog

    async def async_filaments(self) -> list[Filament]:
        """Read every Filament and bring the linked Materials up to date."""
        if self.url is None:
            raise SpoolmanUnreachable
        try:
            filaments = await _async_get(self._hass, self.url, "filament")
            spools = await _async_get(self._hass, self.url, "spool")
            read = [
                _filament(
                    filament,
                    [s for s in spools if s["filament"]["id"] == filament["id"]],
                )
                for filament in filaments
            ]
        except (KeyError, TypeError, AttributeError) as err:
            raise SpoolmanUnreachable from err
        await self._catalog.async_sync_spoolman(
            {filament.id: filament.material_fields() for filament in read}
        )
        return read

    async def async_update_prices(self) -> bool:
        """Read Spoolman if a Material is linked to it; False if that failed."""
        if not any(
            isinstance(m.price, SpoolmanPrice) for m in self._catalog.materials()
        ):
            return True
        try:
            await self.async_filaments()
        except SpoolmanUnreachable:
            return False
        return True

    async def _async_filament(self, filament_id: int) -> Filament | None:
        return next(
            (f for f in await self.async_filaments() if f.id == filament_id), None
        )

    async def async_create_material(self, filament_id: int) -> Material | None:
        """A new Material linked to the Filament; None if Spoolman has no such Filament."""
        if (filament := await self._async_filament(filament_id)) is None:
            return None
        name = " ".join(filter(None, (filament.vendor, filament.name)))
        return await self._catalog.async_create_material(
            {
                "name": name or filament.type or str(filament.id),
                "type": filament.name or str(filament.id),
            }
            | filament.material_fields()
        )

    async def async_link(
        self, material: Material, filament_id: int, changes: dict[str, Any]
    ) -> Material | None:
        """Link the Material to the Filament along with `changes`; None if there is no such Filament."""
        if (filament := await self._async_filament(filament_id)) is None:
            return None
        return await self._catalog.async_update_material(
            material, changes | filament.material_fields()
        )
