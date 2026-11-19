"""Config flow for the WattBill hub entry."""

from typing import Any, override

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    FlowType,
    SubentryFlowContext,
)
from homeassistant.core import callback

from .const import DOMAIN, NAME, SUBENTRY_DEVICE
from .device_flow import DeviceSubentryFlow


class WattBillConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_DEVICE: DeviceSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})

    @override
    async def async_on_create_entry(self, result: ConfigFlowResult) -> ConfigFlowResult:
        add_device = await self.hass.config_entries.subentries.async_init(
            (result["result"].entry_id, SUBENTRY_DEVICE),
            context=SubentryFlowContext(source=SOURCE_USER),
        )
        result["next_flow"] = (FlowType.CONFIG_SUBENTRIES_FLOW, add_device["flow_id"])
        return result
