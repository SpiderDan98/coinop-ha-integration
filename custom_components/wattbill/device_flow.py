"""Add Device and reconfigure: the subentry flow that maps a printer's Device Inputs."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    DeviceSelector,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .const import SUBENTRY_DEVICE
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
    """Each step stores its own section of the Device's data under one key.

    Add Device walks the sections in order; reconfigure offers them as a menu
    and returns to it after each section.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._name = ""
        # The consumption section while its unit is still being asked for.
        self._meter: dict[str, Any] = {}

    def _sections(self) -> dict[str, Callable[[], Awaitable[SubentryFlowResult]]]:
        """Each section's first step, in Add Device order."""
        return {
            "status": self.async_step_status,
            "job": self.async_step_job,
            "consumption": self.async_step_consumption,
            "price": self.async_step_price,
        }

    async def _section_done(self, section: str) -> SubentryFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            return await self.async_step_reconfigure()
        sections = self._sections()
        names = list(sections)
        if following := names[names.index(section) + 1 :]:
            return await sections[following[0]]()
        return self.async_create_entry(title=self._name, data=self._data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._data:
            self._data = dict(self._get_reconfigure_subentry().data)
        return self.async_show_menu(
            step_id="reconfigure", menu_options=[*self._sections(), "save"]
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self.async_update_and_abort(
            self._get_entry(), self._get_reconfigure_subentry(), data=self._data
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["printer_device_id"] = user_input.get("device")
            return await self.async_step_name()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional("device"): DeviceSelector()}),
        )

    async def async_step_name(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._name = user_input["name"]
            return await self.async_step_status()
        device_id = self._data["printer_device_id"]
        printer = dr.async_get(self.hass).async_get(device_id) if device_id else None
        schema = vol.Schema({vol.Required("name"): TextSelector()})
        return self.async_show_form(
            step_id="name",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {"name": printer.name_by_user or printer.name} if printer else None,
            ),
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
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data.get("status")
            ),
            errors=errors,
        )

    def _status_used_elsewhere(self, entity_id: str) -> bool:
        own = (
            self._get_reconfigure_subentry().subentry_id
            if self.source == SOURCE_RECONFIGURE
            else None
        )
        return any(
            subentry.data["status"]["entity_id"] == entity_id
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_DEVICE and subentry.subentry_id != own
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
                return await self._section_done("status")
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
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data.get("mapping")
            ),
            errors=errors,
        )

    async def async_step_job(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["job"] = {
                "entity_id": user_input.get("entity_id"),
                "attribute": user_input.get("attribute") or None,
            }
            return await self._section_done("job")
        schema = vol.Schema(
            {
                vol.Optional("entity_id"): EntitySelector(),
                vol.Optional("attribute"): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="job",
            data_schema=self.add_suggested_values_to_schema(
                schema, self._data.get("job")
            ),
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
            self._meter = {
                "source": source.value,
                "entity_id": user_input["entity_id"],
                "attribute": user_input.get("attribute") or None,
                "unit": None,
                "factor": None,
            }
            if source is ConsumptionSource.POWER:
                self._meter["running_power"] = user_input.get("running_power")
            if self._meter["attribute"]:
                return await (
                    self.async_step_energy_unit()
                    if source is ConsumptionSource.ENERGY
                    else self.async_step_power_unit()
                )
            self._meter["unit"] = entity_unit(self.hass, self._meter["entity_id"])
            if self._unit_understood(source, user_input):
                return await self._meter_done()
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
                vol.Schema(schema), user_input or self._stored_meter(source)
            ),
            errors=errors,
        )

    async def _async_unit_step(
        self, source: ConsumptionSource, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._meter["unit"] = user_input["unit"]
            if self._unit_understood(source, user_input):
                return await self._meter_done()
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
                vol.Schema(schema), user_input or self._stored_meter(source)
            ),
            errors=errors,
        )

    def _stored_meter(self, source: ConsumptionSource) -> dict[str, Any] | None:
        stored: dict[str, Any] | None = self._data.get("consumption")
        return stored if stored and stored["source"] == source else None

    def _unit_understood(
        self, source: ConsumptionSource, user_input: dict[str, Any]
    ) -> bool:
        """A recognised unit, or else a conversion factor the user entered."""
        if unit_scale(source, self._meter["unit"]) is not None:
            return True
        self._meter["factor"] = user_input.get("factor") or None
        return self._meter["factor"] is not None

    async def _meter_done(self) -> SubentryFlowResult:
        self._data["consumption"] = self._meter
        return await self._section_done("consumption")

    async def async_step_estimate(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["consumption"] = {
                "source": "estimate",
                "running_power": user_input["running_power"],
                "paused_power": user_input.get("paused_power"),
            }
            return await self._section_done("consumption")
        schema = vol.Schema(
            {
                vol.Required("running_power"): _watts(1),
                vol.Optional("paused_power"): _watts(0),
            }
        )
        stored = self._data.get("consumption")
        return self.async_show_form(
            step_id="estimate",
            data_schema=self.add_suggested_values_to_schema(
                schema, stored if stored and stored["source"] == "estimate" else None
            ),
        )

    async def async_step_price(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["price"] = {"source": "fixed", "value": user_input["price"]}
            return await self._section_done("price")
        currency = self.hass.config.currency
        schema = vol.Schema(
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
        )
        stored = self._data.get("price")
        return self.async_show_form(
            step_id="price",
            data_schema=self.add_suggested_values_to_schema(
                schema, {"price": stored["value"]} if stored else None
            ),
            description_placeholders={"currency": currency},
        )
