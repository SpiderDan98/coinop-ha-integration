"""Add Device: the subentry flow that maps a printer's Device Inputs."""

from typing import Any

from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .const import SUBENTRY_DEVICE
from .device_config import ENDING_TARGETS, Target
from .device_inputs import offered_values
from .schema import vol


def _watts(minimum: float) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            step="any",
            unit_of_measurement="W",
            mode=NumberSelectorMode.BOX,
        )
    )


def _mapping_error(mapping: dict[str, list[str]]) -> str | None:
    if not mapping[Target.RUNNING]:
        return "no_running_value"
    if not any(mapping[target] for target in ENDING_TARGETS):
        return "no_ending_value"
    values = [value for values in mapping.values() for value in values]
    if len(values) != len(set(values)):
        return "value_mapped_twice"
    return None


class DeviceSubentryFlow(ConfigSubentryFlow):
    """Each step stores its own section of the Device's data under one key."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._name = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._name = user_input["name"]
            return await self.async_step_status()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name"): TextSelector()}),
        )

    async def async_step_status(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._status_used_elsewhere(user_input["entity_id"]):
                errors["entity_id"] = "status_already_used"
            else:
                self._data["status"] = {
                    "entity_id": user_input["entity_id"],
                    "attribute": user_input.get("attribute") or None,
                }
                return await self.async_step_mapping()
        schema = vol.Schema(
            {
                vol.Required("entity_id"): EntitySelector(),
                vol.Optional("attribute"): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="status",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    def _status_used_elsewhere(self, entity_id: str) -> bool:
        return any(
            subentry.data["status"]["entity_id"] == entity_id
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_DEVICE
        )

    async def async_step_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            mapping = {t.value: list(user_input.get(t.value, [])) for t in Target}
            if error := _mapping_error(mapping):
                errors["base"] = error
            else:
                self._data["mapping"] = mapping
                return await self.async_step_consumption()
        status = self._data["status"]
        values = SelectSelector(
            SelectSelectorConfig(
                options=offered_values(
                    self.hass, status["entity_id"], status["attribute"]
                ),
                multiple=True,
                custom_value=True,
            )
        )
        schema = vol.Schema({vol.Optional(target.value): values for target in Target})
        return self.async_show_form(
            step_id="mapping",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_consumption(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self.async_show_menu(step_id="consumption", menu_options=["estimate"])

    async def async_step_estimate(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["consumption"] = {
                "source": "estimate",
                "running_power": user_input["running_power"],
                "paused_power": user_input.get("paused_power"),
            }
            return await self.async_step_price()
        return self.async_show_form(
            step_id="estimate",
            data_schema=vol.Schema(
                {
                    vol.Required("running_power"): _watts(1),
                    vol.Optional("paused_power"): _watts(0),
                }
            ),
        )

    async def async_step_price(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["price"] = {"source": "fixed", "value": user_input["price"]}
            return self.async_create_entry(title=self._name, data=self._data)
        currency = self.hass.config.currency
        return self.async_show_form(
            step_id="price",
            data_schema=vol.Schema(
                {
                    vol.Required("price"): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            step="any",
                            unit_of_measurement=f"{currency}/kWh",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
            description_placeholders={"currency": currency},
        )
