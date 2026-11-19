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

from .device_config import ENDING_TARGETS, ConsumptionSource, Target
from .device_inputs import entity_unit, offered_values, unit_scale
from .schema import vol

# Offered when a meter attribute is picked, which has no unit of its own.
ATTRIBUTE_UNITS = {
    ConsumptionSource.ENERGY: ["Wh", "kWh", "MWh"],
    ConsumptionSource.POWER: ["W", "kW"],
}
FACTOR = NumberSelector(
    NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
)


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
        if user_input is not None:
            self._data["status"] = {
                "entity_id": user_input["entity_id"],
                "attribute": user_input.get("attribute") or None,
            }
            return await self.async_step_mapping()
        return self.async_show_form(
            step_id="status",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_id"): EntitySelector(),
                    vol.Optional("attribute"): TextSelector(),
                }
            ),
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
        return self.async_show_menu(
            step_id="consumption", menu_options=[s.value for s in ConsumptionSource]
        )

    async def async_step_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(ConsumptionSource.ENERGY, user_input)

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(ConsumptionSource.POWER, user_input)

    async def async_step_energy_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(ConsumptionSource.ENERGY, user_input)

    async def async_step_power_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(ConsumptionSource.POWER, user_input)

    async def _async_meter_step(
        self, source: ConsumptionSource, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            meter = self._data["consumption"] = {
                "source": source.value,
                "entity_id": user_input["entity_id"],
                "attribute": user_input.get("attribute") or None,
                "unit": None,
                "factor": None,
            }
            if source is ConsumptionSource.POWER:
                meter["running_power"] = user_input.get("running_power")
            if meter["attribute"]:
                return await (
                    self.async_step_energy_unit()
                    if source is ConsumptionSource.ENERGY
                    else self.async_step_power_unit()
                )
            meter["unit"] = entity_unit(self.hass, meter["entity_id"])
            if self._unit_understood(source, user_input):
                return await self.async_step_price()
            errors["entity_id"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("entity_id"): EntitySelector(),
            vol.Optional("attribute"): TextSelector(),
        }
        if source is ConsumptionSource.POWER:
            schema[vol.Optional("running_power")] = _watts(1)
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=source.value,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input
            ),
            errors=errors,
        )

    async def _async_unit_step(
        self, source: ConsumptionSource, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data["consumption"]["unit"] = user_input["unit"]
            if self._unit_understood(source, user_input):
                return await self.async_step_price()
            errors["unit"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("unit"): SelectSelector(
                SelectSelectorConfig(options=ATTRIBUTE_UNITS[source], custom_value=True)
            )
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=f"{source}_unit",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input
            ),
            errors=errors,
        )

    def _unit_understood(
        self, source: ConsumptionSource, user_input: dict[str, Any]
    ) -> bool:
        """A recognised unit, or else a conversion factor the user entered."""
        meter = self._data["consumption"]
        if unit_scale(source, meter["unit"]) is not None:
            return True
        meter["factor"] = user_input.get("factor") or None
        return meter["factor"] is not None

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
