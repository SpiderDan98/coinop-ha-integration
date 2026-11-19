"""Catalogue changes pushed to every open panel.

`CATALOGUES` names each catalogue and how the panel receives it; a new catalogue
only adds an entry there and announces its name from `Catalog`.
"""

from collections.abc import Callable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from custom_components.wattbill.catalog import MATERIALS, Catalog
from custom_components.wattbill.const import DOMAIN
from custom_components.wattbill.runtime import WattBill
from custom_components.wattbill.schema import vol
from custom_components.wattbill.tags import TAGS
from custom_components.wattbill.templates import TEMPLATES

from .command import command
from .materials import material_dict

# Outlives a reload of the hub entry, so open subscriptions keep receiving.
SIGNAL_CATALOG_CHANGED = f"{DOMAIN}_catalog_changed"

CATALOGUES: dict[str, Callable[[Catalog], list[Any]]] = {
    MATERIALS: lambda catalog: [material_dict(m) for m in catalog.materials()],
    TAGS: lambda catalog: catalog.tags(),
    TEMPLATES: lambda catalog: [t.as_dict() for t in catalog.templates()],
}


@callback
def async_announce(hass: HomeAssistant, catalog: Catalog) -> CALLBACK_TYPE:
    """Forward the catalogue changes to every panel subscription."""
    return catalog.async_listen(
        lambda name: async_dispatcher_send(hass, SIGNAL_CATALOG_CHANGED, catalog, name)
    )


@command({vol.Required("type"): "wattbill/catalog/subscribe"})
def _subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    wattbill: WattBill,
) -> None:
    """First event: every catalogue (`{"materials": [...], "tags": [...],
    "templates": [...]}`).

    Then each change: the changed catalogue alone.
    """

    @callback
    def forward(catalog: Catalog, name: str) -> None:
        connection.send_event(msg["id"], {name: CATALOGUES[name](catalog)})

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_CATALOG_CHANGED, forward
    )
    connection.send_result(msg["id"])
    connection.send_event(
        msg["id"], {name: read(wattbill.catalog) for name, read in CATALOGUES.items()}
    )


COMMANDS = (_subscribe,)
