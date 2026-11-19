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
    BooleanSelector,
    DeviceSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .const import SUBENTRY_DEVICE
from .device_config import ENDING_TARGETS, ConsumptionSource, Target
from .device_inputs import (
    entity_unit,
    offered_values,
    price_scale,
    unit_scale,
    usage_scale,
)
from .profiles import detect
from .schema import vol

# Offered when a meter or Material used attribute is picked, which has no unit of its own.
ATTRIBUTE_UNITS = {
    ConsumptionSource.ENERGY: ["Wh", "kWh", "MWh"],
    ConsumptionSource.POWER: ["W", "kW"],
}
USAGE_UNITS = ["mm", "cm", "m", "g", "kg"]
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
        # The consumption or price section while its unit is still being asked for.
        self._meter: dict[str, Any] = {}
        self._price: dict[str, Any] = {}
        self._job: dict[str, Any] = {}
        # The profile's sections while Detect again walks them.
        self._detecting: dict[str, Any] = {}

    def _sections(self) -> dict[str, Callable[[], Awaitable[SubentryFlowResult]]]:
        """Each section's first step, in Add Device order."""
        return {
            "status": self.async_step_status,
            "job": self.async_step_job,
            "images": self.async_step_images,
            "consumption": self.async_step_consumption,
            "price": self.async_step_price,
        }

    async def _section_done(self, section: str) -> SubentryFlowResult:
        sections = self._sections()
        names = list(sections)
        following = names[names.index(section) + 1 :]
        if self.source == SOURCE_RECONFIGURE and not (
            following and following[0] in self._detecting
        ):
            self._detecting = {}
            return await self.async_step_reconfigure()
        if following:
            return await sections[following[0]]()
        return self.async_create_entry(title=self._name, data=self._data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._data:
            self._data = dict(self._get_reconfigure_subentry().data)
        detect_again = ["detect"] if self._detected() else []
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[*self._sections(), *detect_again, "save"],
        )

    def _detected(self) -> dict[str, Any] | None:
        return detect(self.hass, self._data.get("printer_device_id"))

    async def async_step_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Walk the sections the profile fills, pre-filled with what it finds now."""
        self._detecting = self._detected() or {}
        for section, values in self._detecting.items():
            self._data[section] = (self._data.get(section) or {}) | values
        return await self.async_step_status()

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
            self._data |= detect(self.hass, self._data["printer_device_id"]) or {}
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
        errors: dict[str, str] = {}
        if user_input is not None:
            material = user_input.get("material_entity_id")
            self._job = {
                "entity_id": user_input.get("entity_id"),
                "attribute": user_input.get("attribute") or None,
                "material": {
                    "entity_id": material,
                    "attribute": user_input.get("material_attribute") or None,
                    "unit": None,
                }
                if material
                else None,
                "slots": list(user_input.get("slots", [])),
                "colour_attribute": user_input.get("colour_attribute") or None,
                "loaded_slot": user_input.get("loaded_slot"),
            }
            usage = self._job["material"]
            if usage is None:
                return await self._job_done()
            if usage["attribute"]:
                return await self.async_step_material_unit()
            usage["unit"] = entity_unit(self.hass, usage["entity_id"])
            if usage_scale(usage["unit"]):
                return await self._job_done()
            errors["material_entity_id"] = "not_length_or_mass"
        schema = vol.Schema(
            {
                vol.Optional("entity_id"): EntitySelector(),
                vol.Optional("attribute"): TextSelector(),
                vol.Optional("material_entity_id"): EntitySelector(),
                vol.Optional("material_attribute"): TextSelector(),
                # The order picked is the Slot order.
                vol.Optional("slots"): EntitySelector(
                    EntitySelectorConfig(multiple=True, reorder=True)
                ),
                vol.Optional("colour_attribute"): TextSelector(),
                vol.Optional("loaded_slot"): EntitySelector(),
            }
        )
        stored = self._data.get("job") or {}
        usage = stored.get("material") or {}
        return self.async_show_form(
            step_id="job",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input
                or stored
                | {
                    "material_entity_id": usage.get("entity_id"),
                    "material_attribute": usage.get("attribute"),
                },
            ),
            errors=errors,
        )

    async def async_step_material_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if usage_scale(user_input["unit"]):
                self._job["material"]["unit"] = user_input["unit"]
                return await self._job_done()
            errors["unit"] = "not_length_or_mass"
        schema = vol.Schema(
            {
                vol.Required("unit"): SelectSelector(
                    SelectSelectorConfig(options=USAGE_UNITS, custom_value=True)
                )
            }
        )
        stored = (self._data.get("job") or {}).get("material")
        return self.async_show_form(
            step_id="material_unit",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or stored
            ),
            errors=errors,
        )

    async def _job_done(self) -> SubentryFlowResult:
        self._data["job"] = self._job
        return await self._section_done("job")

    async def async_step_images(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            camera = user_input.get("camera")
            self._data["images"] = {
                "thumbnail": user_input.get("thumbnail"),
                "camera": camera,
                "snapshot": camera is not None and user_input["snapshot"],
            }
            return await self._section_done("images")
        schema = vol.Schema(
            {
                vol.Optional("thumbnail"): EntitySelector(
                    EntitySelectorConfig(domain="image")
                ),
                vol.Optional("camera"): EntitySelector(
                    EntitySelectorConfig(domain="camera")
                ),
                vol.Optional("snapshot", default=True): BooleanSelector(),
            }
        )
        stored = self._data.get("images", {})
        return self.async_show_form(
            step_id="images",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                # Without a camera the toggle was off only for lack of one.
                stored
                | {"snapshot": stored["snapshot"] if stored.get("camera") else True},
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
            if self._understood(
                self._meter, unit_scale(source, self._meter["unit"]), user_input
            ):
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
            if self._understood(
                self._meter, unit_scale(source, self._meter["unit"]), user_input
            ):
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

    @staticmethod
    def _understood(
        section: dict[str, Any], scale: float | None, user_input: dict[str, Any]
    ) -> bool:
        """A recognised unit, or else a conversion factor the user entered."""
        if scale is not None:
            return True
        section["factor"] = user_input.get("factor") or None
        return section["factor"] is not None

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
        return self.async_show_menu(
            step_id="price", menu_options=["fixed_price", "price_entity"]
        )

    async def async_step_fixed_price(
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
        stored = self._stored_price("fixed")
        return self.async_show_form(
            step_id="fixed_price",
            data_schema=self.add_suggested_values_to_schema(
                schema, {"price": stored["value"]} if stored else None
            ),
            description_placeholders={"currency": currency},
        )

    async def async_step_price_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        currency = self.hass.config.currency
        if user_input is not None:
            self._price = {
                "source": "entity",
                "entity_id": user_input["entity_id"],
                "attribute": user_input.get("attribute") or None,
                "unit": None,
                "factor": None,
            }
            if self._price["attribute"]:
                return await self.async_step_price_unit()
            self._price["unit"] = entity_unit(self.hass, self._price["entity_id"])
            if self._understood(
                self._price, price_scale(self._price["unit"], currency), user_input
            ):
                return await self._price_done()
            errors["entity_id"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("entity_id"): EntitySelector(),
            vol.Optional("attribute"): TextSelector(),
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id="price_entity",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or self._stored_price("entity")
            ),
            errors=errors,
            description_placeholders={"currency": currency},
        )

    async def async_step_price_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        currency = self.hass.config.currency
        if user_input is not None:
            self._price["unit"] = user_input["unit"]
            if self._understood(
                self._price, price_scale(self._price["unit"], currency), user_input
            ):
                return await self._price_done()
            errors["unit"] = "unknown_unit"
        units = [f"{currency}/kWh", "ct/kWh", f"{currency}/MWh"]
        schema: dict[Any, Any] = {
            vol.Required("unit"): SelectSelector(
                SelectSelectorConfig(options=units, custom_value=True)
            )
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id="price_unit",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or self._stored_price("entity")
            ),
            errors=errors,
            description_placeholders={"currency": currency},
        )

    async def _price_done(self) -> SubentryFlowResult:
        self._data["price"] = self._price
        return await self._section_done("price")

    def _stored_price(self, source: str) -> dict[str, Any] | None:
        """The Device's price, or for a new Device the last-added Device's one."""
        stored: dict[str, Any] | None = self._data.get("price")
        if stored is None and self.source != SOURCE_RECONFIGURE:
            stored = next(
                (
                    subentry.data["price"]
                    for subentry in reversed([*self._get_entry().subentries.values()])
                    if subentry.subentry_type == SUBENTRY_DEVICE
                ),
                None,
            )
        return stored if stored and stored["source"] == source else None
