"""Serving Run images to admins only; `<img>` can't authenticate, so the panel fetches them."""

from typing import TYPE_CHECKING, Any, cast

from aiohttp import hdrs, web
from homeassistant.components.http import KEY_HASS, HomeAssistantView, require_admin

from custom_components.wattbill.const import DOMAIN
from custom_components.wattbill.models import Run, RunImage

from .library import VARIANTS

if TYPE_CHECKING:
    from custom_components.wattbill.runtime import WattBillConfigEntry

URL = f"/api/{DOMAIN}/runs/{{run_id}}/images/{{image_id}}"
# An image id never gets other content, so a browser may keep it.
CACHE_CONTROL = "private, max-age=31536000, immutable"


def image_url(run: Run, image: RunImage, variant: str = "full") -> str:
    url = URL.format(run_id=run.id, image_id=image.id)
    return url if variant == "full" else f"{url}/{variant}"


def image_info(run: Run, image: RunImage) -> dict[str, Any]:
    """An image as the panel receives it: stored metadata plus where to fetch it."""
    return image.as_dict() | {
        "url": image_url(run, image),
        "tile_url": image_url(run, image, "tile"),
    }


class RunImageView(HomeAssistantView):
    url = URL
    name = f"api:{DOMAIN}:run_image"

    def __init__(self) -> None:
        self.extra_urls = [f"{URL}/{{variant}}"]

    @require_admin
    async def get(
        self, request: web.Request, run_id: str, image_id: str, variant: str = "full"
    ) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries or variant not in VARIANTS:
            raise web.HTTPNotFound
        wattbill = cast("WattBillConfigEntry", entries[0]).runtime_data
        run = wattbill.book.run(run_id)
        image = next((i for i in run.images if i.id == image_id), None) if run else None
        if run is None or image is None:
            raise web.HTTPNotFound
        return web.FileResponse(
            wattbill.images.path(run, image, variant),
            headers={hdrs.CACHE_CONTROL: CACHE_CONTROL},
        )
