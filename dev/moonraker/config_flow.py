from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import DOMAIN


class MoonrakerStandInFlow(ConfigFlow, domain=DOMAIN):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title="Voron 2.4", data={})
