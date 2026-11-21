"""Dev container only: a stand-in for WashData (3dg1luk43/ha_washdata).

Each config entry is one device, as in WashData, and keeps the kind picked for it as
`device_type` in its data, which tells Coin-op its Device Type. Its state and program
follow the helpers of its kind from the dev configuration.yaml.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..coinop_dev import stand_in
from ..coinop_dev.stand_in import async_unload_entry

# The helpers' prefix in the dev configuration.yaml, by kind.
HELPERS = {
    "washing_machine": "washdata_washer",
    "dishwasher": "washdata_dishwasher",
    "tumble_dryer": "washdata_dryer",
}
# The Status helper's `cancelled` is WashData's `interrupted`, and WashData knows no
# program while the device is off.
STATE = "{% set s = states('STATUS') %}{{ 'interrupted' if s == 'cancelled' else s }}"
PROGRAM = "{{ 'off' if is_state('STATUS', 'off') else states('PROGRAM') }}"

__all__ = ["async_setup_entry", "async_unload_entry"]


def follow(kind: str) -> dict[str, str]:
    status, program = (
        f"input_select.{HELPERS[kind]}_{helper}" for helper in ("status", "program")
    )
    return {
        "washer_state": STATE.replace("STATUS", status),
        "washer_program": PROGRAM.replace("STATUS", status).replace("PROGRAM", program),
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await stand_in.async_setup_entry(hass, entry, follow)
