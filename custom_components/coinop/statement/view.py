"""The Cost Statement download: rendered on request, from the Runs as they are now.

The browser fetches it with a plain link, so the panel gets a signed path
(`signed_path`) and the view still lets admins only.
"""

from datetime import datetime

from aiohttp import hdrs, web
from homeassistant.components.http import KEY_HASS, HomeAssistantView, require_admin
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util, slugify

from custom_components.coinop.const import DOMAIN
from custom_components.coinop.images.view import loaded_coinop
from custom_components.coinop.models import Run

from .document import render
from .export import EXPIRES, Options
from .text import STRINGS

URL = f"/api/{DOMAIN}/cost_statement/{{token}}"


def signed_path(hass: HomeAssistant, token: str, refresh_token_id: str | None) -> str:
    return async_sign_path(
        hass,
        URL.format(token=token),
        EXPIRES,
        refresh_token_id=refresh_token_id,
    )


def filename(options: Options, now: datetime) -> str:
    title = options.title or STRINGS[options.language]["title"]
    slug = slugify(title, separator="-") or slugify(
        STRINGS["en"]["title"], separator="-"
    )
    return f"{slug}-{dt_util.as_local(now).date().isoformat()}.pdf"


class CostStatementView(HomeAssistantView):
    url = URL
    name = f"api:{DOMAIN}:cost_statement"

    @require_admin
    async def get(self, request: web.Request, token: str) -> web.Response:
        hass, now = request.app[KEY_HASS], dt_util.utcnow()
        coinop = loaded_coinop(request)
        export = coinop.statements.get(token, now) if coinop else None
        if coinop is None or export is None:
            raise web.HTTPNotFound
        runs = sorted(
            (
                # A copy, as rendering runs outside the event loop.
                Run.from_dict(run.as_dict())
                for run_id in export.run_ids
                if (run := coinop.book.run(run_id)) and run.finalised
            ),
            key=lambda run: run.started,
        )
        if not runs:
            raise web.HTTPNotFound
        covers = {
            run.id: coinop.images.path(run, cover, "full")
            for run in runs
            if export.options.images and (cover := run.cover)
        }
        pdf = await hass.async_add_executor_job(
            lambda: render(
                runs,
                export.options,
                covers=covers,
                now=now,
                currency=hass.config.currency,
                country=hass.config.country,
                time_zone=dt_util.get_default_time_zone(),
            )
        )
        return web.Response(
            body=pdf,
            content_type="application/pdf",
            headers={
                hdrs.CONTENT_DISPOSITION: (
                    f'attachment; filename="{filename(export.options, now)}"'
                ),
                hdrs.CACHE_CONTROL: "no-store",
            },
        )
