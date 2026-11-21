"""Spoolman, read directly over its REST API: every Filament is a linked Material.

Every read (Materials tab, Run end, start) gives each Filament without one a
linked Material, unless it waits for the user to merge it into an own Material
of its type (and colour); a linked Material takes its name, price and details
from its Filament and is archived once the Filament is gone. Between reads, and
while Spoolman is unreachable, the last price read applies.
"""

import asyncio
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, NamedTuple

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.hassio import is_hassio
from yarl import URL

from .catalog import Catalog
from .const import DOMAIN
from .materials import Material, MaterialForm, SpoolmanPrice

CONF_SPOOLMAN_URL = "spoolman_url"
ISSUE_SPOOLMAN_FOUND = "spoolman_found"
_TIMEOUT = ClientTimeout(total=10)
_PORT = 7912
# The Spoolman integration (Disane87/spoolman-homeassistant) keeps its URL here.
_INTEGRATION_DOMAIN = "spoolman"
_INTEGRATION_URL = "spoolman_url"


class SpoolmanUnreachable(Exception):
    """Spoolman isn't set up, didn't answer, or answered with something else."""


class StaleMerge(Exception):
    """A merge picked a Material or Filament that isn't waiting for it (any more)."""


@dataclass(frozen=True)
class Filament:
    id: int
    name: str | None
    vendor: str | None
    type: str | None
    density: float
    diameter: float
    colour: str | None
    # The price and weight Spoolman prices it by; None without a price.
    pack: tuple[float, float] | None

    @property
    def material_name(self) -> str:
        return (
            " ".join(filter(None, (self.vendor, self.name)))
            or self.type
            or str(self.id)
        )

    @property
    def price_per_gram(self) -> float | None:
        return None if self.pack is None else self.pack[0] / self.pack[1]

    def material_fields(self) -> dict[str, Any]:
        """What a linked Material takes over from its Filament, its price included."""
        price, weight = self.pack or (None, None)
        return {
            "name": self.material_name,
            "form": MaterialForm.FILAMENT,
            "type": self.type or self.name or str(self.id),
            "density": self.density,
            "diameter": self.diameter,
            "colour": self.colour,
            "vendor": self.vendor,
            "price": SpoolmanPrice(
                self.id, self.price_per_gram, price, weight
            ).as_dict(),
        }

    def matches(self, material: Material) -> bool:
        """Whether the Filament is a candidate for merging the (own) Material."""
        return (
            self.type is not None
            and self.type.casefold() == material.type.casefold()
            and material.colour in (None, self.colour)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.material_name,
            "vendor": self.vendor,
            "type": self.type,
            "colour": self.colour,
            "price_per_gram": self.price_per_gram,
        }


class Merge(NamedTuple):
    """An own filament Material and the Filaments it could be merged into, best first
    (same vendor)."""

    material: Material
    candidates: list[Filament]


def _pack(
    filament: dict[str, Any], spools: list[dict[str, Any]]
) -> tuple[float, float] | None:
    """`filament.price` per `filament.weight`, else the newest priced spool's
    `spool.price` per its `initial_weight` (both are prices of a whole spool)."""
    if (price := filament.get("price")) is not None and filament.get("weight"):
        return float(price), float(filament["weight"])
    for spool in sorted(
        spools, key=lambda spool: (spool.get("registered") or "", spool["id"])
    )[::-1]:
        weight = spool.get("initial_weight") or filament.get("weight")
        if not spool.get("archived") and spool.get("price") is not None and weight:
            return float(spool["price"]), float(weight)
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
        pack=_pack(data, spools),
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


def clean_url(url: str) -> str:
    return url.strip().rstrip("/")


async def async_check(hass: HomeAssistant, url: str) -> None:
    """Raise SpoolmanUnreachable unless Spoolman answers at `url`."""
    info = await _async_get(hass, url, "info")
    if not isinstance(info, dict) or "version" not in info:
        raise SpoolmanUnreachable


async def _async_addon_urls(hass: HomeAssistant) -> list[str]:
    """Where HA reaches each running Spoolman add-on inside the Supervisor's network."""
    if not is_hassio(hass):
        return []
    # Only loaded on a Supervisor install, where hassio is already set up.
    from homeassistant.components.hassio import (
        SupervisorError,
        get_supervisor_client,
    )

    client = get_supervisor_client(hass)
    urls: list[str] = []
    try:
        for addon in await client.addons.list():
            if "spoolman" not in addon.slug or addon.state != "started":
                continue
            info = await client.addons.addon_info(addon.slug)
            # An Ingress add-on's own proxy adds the Ingress path, so its port serves the API at /.
            ports = [info.ingress_port] if info.ingress and info.ingress_port else []
            ports += [int(port.partition("/")[0]) for port in info.network or {}]
            urls += [f"http://{info.hostname}:{port}" for port in [*ports, _PORT]]
    except SupervisorError:
        pass
    return urls


async def async_find(hass: HomeAssistant) -> str | None:
    """A Spoolman URL that answers: the Spoolman integration's first, then an add-on's."""
    candidates = [
        clean_url(url)
        for entry in hass.config_entries.async_entries(_INTEGRATION_DOMAIN)
        if isinstance(url := entry.data.get(_INTEGRATION_URL), str)
    ] + await _async_addon_urls(hass)
    for url in dict.fromkeys(candidates):
        try:
            await async_check(hass, url)
        except SpoolmanUnreachable:
            continue
        return url
    return None


async def async_offer(hass: HomeAssistant, wanted: bool) -> None:
    """Offer the Spoolman found in HA as a repair, while `wanted` (no URL set, a Device uses Material)."""
    if not wanted or (url := await async_find(hass)) is None:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_SPOOLMAN_FOUND)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_SPOOLMAN_FOUND,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_SPOOLMAN_FOUND,
        translation_placeholders={"url": url},
        data={"url": url},
    )


class Spoolman:
    """The Spoolman set in the hub options (if any), and the Materials linked to it."""

    def __init__(self, hass: HomeAssistant, url: str | None, catalog: Catalog) -> None:
        self._hass = hass
        self.url = url
        self._catalog = catalog
        # One read at a time, so no Filament gets two Materials.
        self._lock = asyncio.Lock()

    async def async_read(self) -> list[Merge]:
        """Read every Filament and bring the Materials up to date; returns the own
        Materials with the Filaments waiting to be merged into them."""
        async with self._lock:
            filaments = await self._async_filaments()
            await self._async_sync(filaments)
            return self._merges(filaments)

    async def async_refresh(self) -> bool:
        """Read Spoolman; False if that failed."""
        try:
            await self.async_read()
        except SpoolmanUnreachable:
            return False
        return True

    async def async_merge(self, picks: dict[str, int | None]) -> list[Merge]:
        """Link each own Material to the Filament picked for it, or keep it (None)
        and give its candidates their own Materials; returns what still waits.

        Raises StaleMerge unless every pick is a candidate of its Material.
        """
        async with self._lock:
            filaments = await self._async_filaments()
            merges = {merge.material.id: merge for merge in self._merges(filaments)}
            picked = [f for f in picks.values() if f is not None]
            if len(set(picked)) < len(picked) or any(
                material_id not in merges
                or filament_id
                not in (None, *(f.id for f in merges[material_id].candidates))
                for material_id, filament_id in picks.items()
            ):
                raise StaleMerge
            by_id = {filament.id: filament for filament in filaments}
            for material_id, filament_id in picks.items():
                if filament_id is not None:
                    await self._catalog.async_link_spoolman(
                        merges[material_id].material,
                        by_id[filament_id].material_fields(),
                    )
            await self._async_sync(filaments, kept=picks.keys())
            return self._merges(filaments)

    async def _async_filaments(self) -> list[Filament]:
        if self.url is None:
            raise SpoolmanUnreachable
        try:
            filaments = await _async_get(self._hass, self.url, "filament")
            spools = await _async_get(self._hass, self.url, "spool")
            return [
                _filament(
                    filament,
                    [s for s in spools if s["filament"]["id"] == filament["id"]],
                )
                for filament in filaments
            ]
        except (KeyError, TypeError, AttributeError) as err:
            raise SpoolmanUnreachable from err

    async def _async_sync(
        self, filaments: list[Filament], kept: Collection[str] = ()
    ) -> None:
        waiting = {
            filament.id
            for merge in self._merges(filaments)
            if merge.material.id not in kept
            for filament in merge.candidates
        }
        await self._catalog.async_sync_spoolman(
            {filament.id: filament.material_fields() for filament in filaments},
            waiting,
        )

    def _merges(self, filaments: list[Filament]) -> list[Merge]:
        linked = self._catalog.linked_filaments()
        unlinked = [f for f in filaments if f.id not in linked]
        merges = []
        for material in self._catalog.materials():
            if (
                material.linked
                or material.archived
                or material.form is not MaterialForm.FILAMENT
                or material.by_piece
            ):
                continue
            same_vendor = (material.vendor or "").casefold()
            candidates = sorted(
                (f for f in unlinked if f.matches(material)),
                key=lambda f: (f.vendor or "").casefold() != same_vendor,
            )
            if candidates:
                merges.append(Merge(material, candidates))
        return merges
