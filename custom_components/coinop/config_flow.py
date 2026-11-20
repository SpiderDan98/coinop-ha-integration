from typing import Any, override

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    FlowType,
    OptionsFlow,
    SubentryFlowContext,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN, NAME, SUBENTRY_DEVICE
from .device_flow import DeviceSubentryFlow
from .schema import vol
from .spoolman import CONF_SPOOLMAN_URL, SpoolmanUnreachable, async_check
from .statement import CONF_MARKUP

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SPOOLMAN_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Optional(CONF_MARKUP): NumberSelector(
            NumberSelectorConfig(
                min=0, step="any", unit_of_measurement="%", mode=NumberSelectorMode.BOX
            )
        ),
    }
)


class CoinOpConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    # 1.2: every Device stores its Device Type.
    MINOR_VERSION = 2

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_DEVICE: DeviceSubentryFlow}

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CoinOpOptionsFlow()

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


async def _async_validate(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """The options to save, or the errors to show."""
    options, errors = dict(user_input), {}
    if url := options.pop(CONF_SPOOLMAN_URL, "").strip().rstrip("/"):
        try:
            await async_check(hass, url)
        except SpoolmanUnreachable:
            errors[CONF_SPOOLMAN_URL] = "cannot_connect"
        options[CONF_SPOOLMAN_URL] = url
    return options, errors


class CoinOpOptionsFlow(OptionsFlow):
    """The hub's integration-wide options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = await _async_validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
        )
