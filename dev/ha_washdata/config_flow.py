from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import DOMAIN

WASHING_MACHINE = {"name": "Washing machine", "device_type": "washing_machine"}


class WashDataStandInFlow(ConfigFlow, domain=DOMAIN):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Like WashData, the entry is named after its one device and keeps the kind
        picked for it as `device_type` in its data; without input, a washing machine.

        WashData's power sensor and minimum power are left out: nothing reads them.
        """
        data = WASHING_MACHINE | (user_input or {})
        return self.async_create_entry(title=data["name"], data=data)
