"""Add Device and reconfigure: the subentry flow that maps a Device's Device Inputs."""

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
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import SUBENTRY_DEVICE
from .device_config import (
    CAPABILITIES,
    ENDING_TARGETS,
    Capability,
    ConsumptionSource,
    Target,
    WaterSource,
)
from .device_inputs import (
    entity_unit,
    offered_values,
    price_scale,
    unit_scale,
    usage_scale,
)
from .profiles import METERS, candidates, detect, known_integrations
from .quantities import ELECTRICITY, WATER, Quantity
from .schema import vol

# Offered when a meter or Material used attribute is picked, which has no unit of its own.
ATTRIBUTE_UNITS: dict[str, list[str]] = {
    ConsumptionSource.ENERGY: ["Wh", "kWh", "MWh"],
    ConsumptionSource.POWER: ["W", "kW"],
    WaterSource.METER: ["L", "m³", "gal", "ft³", "CCF"],
    WaterSource.FLOW: ["L/min", "L/h", "m³/h", "gal/min"],
}
USAGE_UNITS = ["mm", "cm", "m", "g", "kg"]
FACTOR = NumberSelector(
    NumberSelectorConfig(min=0, step="any", mode=NumberSelectorMode.BOX)
)
# Quick Start's choice to walk every step instead.
MANUAL = "manual"
# The sections a profile may fill only in part, as their steps store them unused.
UNUSED: dict[str, dict[str, Any]] = {
    "job": {
        "entity_id": None,
        "attribute": None,
        "material": None,
        "slots": [],
        "colour_attribute": None,
        "loaded_slot": None,
    },
    "images": {"thumbnail": None, "camera": None, "snapshot": False},
    "program": {"entity_id": None, "attribute": None},
}


def _watts(minimum: float) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            step="any",
            unit_of_measurement="W",
            mode=NumberSelectorMode.BOX,
        )
    )


def _price_selector(quantity: Quantity, currency: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            step="any",
            unit_of_measurement=f"{currency}/{quantity.price_unit}",
            mode=NumberSelectorMode.BOX,
        )
    )


def _step(quantity: Quantity, name: str) -> str:
    """Electricity's steps keep their names; another quantity's are prefixed by it."""
    return name if quantity is ELECTRICITY else f"{quantity.source_key}_{name}"


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
    and returns to it after each section. Quick Start takes the sections from an
    Integration Profile and asks only for what no profile knows.
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
        # The name of the integration Quick Start took the sections from.
        self._integration = ""

    def _capabilities(self) -> frozenset[Capability]:
        return CAPABILITIES[self._data["device_type"]]

    def _sections(self) -> dict[str, Callable[[], Awaitable[SubentryFlowResult]]]:
        """Each section's first step, in Add Device order, as the Device Type has them."""
        sections = {
            "status": self.async_step_status,
            "job": self.async_step_job,
            "images": self.async_step_images,
            "program": self.async_step_program,
            "consumption": self.async_step_consumption,
            "price": self.async_step_price,
            "water": self.async_step_water,
            "water_price": self.async_step_water_price,
        }
        needs = {
            "job": Capability.JOB,
            "images": Capability.IMAGES,
            "program": Capability.PROGRAM,
            "water": Capability.WATER,
            "water_price": Capability.WATER,
        }
        if (self._data.get("water") or {}).get("source") == WaterSource.NONE:
            del needs["water_price"], sections["water_price"]
        return {
            name: step
            for name, step in sections.items()
            if name not in needs or needs[name] in self._capabilities()
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
        return detect(
            self.hass, self._data["device_type"], self._data.get("printer_device_id")
        )

    async def async_step_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Walk the sections the profile fills, pre-filled with what it finds now."""
        self._detecting = {
            section: values
            for section, values in (self._detected() or {}).items()
            if section not in METERS
        }
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
        """The Device Type, fixed once the Device is added; Quick Start comes first
        where it has a device to offer."""
        if user_input is not None:
            self._data["device_type"] = user_input["device_type"]
            return await self.async_step_device()
        if self._quick_start_devices():
            return await self.async_step_quick_start()
        return self._device_type_form()

    def _device_type_form(self) -> SubentryFlowResult:
        schema = vol.Schema(
            {
                vol.Required("device_type"): SelectSelector(
                    SelectSelectorConfig(
                        options=list(CAPABILITIES),
                        translation_key="device_type",
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    def _quick_start_devices(self) -> dict[str, tuple[str, str, dict[str, Any]]]:
        """The HA devices of known integrations that no Device follows yet."""
        followed = {
            subentry.data["printer_device_id"]
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_DEVICE
        }
        return {
            device_id: candidate
            for device_id, candidate in candidates(self.hass).items()
            if device_id not in followed
            and not self._status_used_elsewhere(candidate[2]["status"]["entity_id"])
        }

    async def async_step_quick_start(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        offered = self._quick_start_devices()
        devices = dr.async_get(self.hass)
        names = {
            device_id: device.name_by_user or device.name or device_id
            for device_id in offered
            if (device := devices.async_get(device_id))
        }
        if user_input is not None:
            device_id = user_input["device"]
            if device_id == MANUAL:
                return self._device_type_form()
            device_type, self._integration, sections = offered[device_id]
            self._name = names[device_id]
            self._data = {"device_type": device_type, "printer_device_id": device_id}
            self._data |= {
                name: values
                for name, values in sections.items()
                if name not in UNUSED and name not in METERS
            }
            self._data |= {
                name: unused | sections.get(name, {})
                for name, unused in UNUSED.items()
                if name in self._sections()
            }
            for quantity in (ELECTRICITY, WATER):
                found = sections.get(quantity.source_key)
                if found and (
                    meter := self._meter_of(
                        quantity, found["entity_id"], [found["source"]]
                    )
                ):
                    self._data[quantity.source_key] = meter
            return await self.async_step_quick_start_confirm()
        options = [
            SelectOptionDict(
                value=device_id, label=f"{names[device_id]} · {integration}"
            )
            for device_id, (_, integration, _) in offered.items()
        ]
        schema = vol.Schema(
            {
                vol.Required("device"): SelectSelector(
                    SelectSelectorConfig(
                        # Manual setup's label is its translation.
                        options=[
                            *options,
                            SelectOptionDict(value=MANUAL, label=MANUAL),
                        ],
                        translation_key="quick_start_device",
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="quick_start",
            data_schema=self.add_suggested_values_to_schema(
                schema, {"device": next(iter(offered))}
            ),
        )

    def _meter_of(
        self, quantity: Quantity, entity_id: str, sources: list[str]
    ) -> dict[str, Any] | None:
        """The entity's section as the one of `sources` its unit makes it; None if
        its unit fits none."""
        unit = entity_unit(self.hass, entity_id)
        source = next(
            (s for s in sources if unit_scale(quantity, s, unit) is not None), None
        )
        if source is None:
            return None
        gaps = {"running_power": None} if self._fills_power_gaps(source) else {}
        return {
            "source": source,
            "entity_id": entity_id,
            "attribute": None,
            "unit": unit,
            "factor": None,
        } | gaps

    async def async_step_quick_start_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """What the profile found, and what no profile knows: the meter and the prices."""
        errors: dict[str, str] = {}
        currency = self.hass.config.currency
        capabilities = self._capabilities()
        per_program = Capability.PROGRAM_CONSUMPTION in capabilities
        meter_field = "optional_meter" if per_program else "meter"
        needs_meter = ELECTRICITY.source_key not in self._data
        if user_input is not None:
            data = dict(self._data)
            if needs_meter:
                data["consumption"] = self._quick_meter(user_input.get(meter_field))
                if data["consumption"] is None:
                    errors[meter_field] = "not_energy_or_power"
            price, price_entity = (
                user_input.get("price"),
                user_input.get("price_entity"),
            )
            if (price is None) == (price_entity is None):
                errors["price"] = "one_price"
            elif price_entity is None:
                data["price"] = {"source": "fixed", "value": price}
            elif entity_price := self._quick_price(price_entity, currency):
                data["price"] = entity_price
            else:
                errors["price_entity"] = "unknown_price_unit"
            if Capability.WATER in capabilities:
                if (water_price := user_input.get("water_price")) is None:
                    data["water"] = {"source": WaterSource.NONE.value}
                else:
                    data.setdefault("water", {"source": WaterSource.PER_PROGRAM.value})
                    data["water_price"] = {"source": "fixed", "value": water_price}
            if not errors:
                return self.async_create_entry(title=self._name, data=data)
        schema: dict[Any, Any] = {}
        if needs_meter:
            required = vol.Optional if per_program else vol.Required
            schema[required(meter_field)] = EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class=["energy", "power"])
            )
        schema[vol.Optional("price")] = _price_selector(ELECTRICITY, currency)
        schema[vol.Optional("price_entity")] = EntitySelector()
        if Capability.WATER in capabilities:
            schema[vol.Optional("water_price")] = _price_selector(WATER, currency)
        last_fixed = self._stored_price(ELECTRICITY, "fixed")
        last_price = self._stored_price(ELECTRICITY, "entity")
        last_water = self._stored_price(WATER, "fixed")
        suggested = {
            "price": last_fixed["value"] if last_fixed else None,
            "price_entity": last_price["entity_id"] if last_price else None,
            "water_price": last_water["value"] if last_water else None,
        }
        return self.async_show_form(
            step_id="quick_start_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or suggested
            ),
            errors=errors,
            description_placeholders={
                "device": self._name,
                "integration": self._integration,
                "inputs": "\n".join(f"- {name}" for name in self._found_inputs()),
                "currency": currency,
            },
        )

    def _quick_meter(self, entity_id: str | None) -> dict[str, Any] | None:
        """Electricity from the picked meter, per Program without one; None if the
        entity reports neither energy nor power."""
        if entity_id is None:
            return {"source": ConsumptionSource.PER_PROGRAM.value}
        return self._meter_of(
            ELECTRICITY, entity_id, [ConsumptionSource.ENERGY, ConsumptionSource.POWER]
        )

    def _quick_price(self, entity_id: str, currency: str) -> dict[str, Any] | None:
        """The price entity's section, the last Device's if it reads the same entity;
        None if its unit is no price."""
        last = self._stored_price(ELECTRICITY, "entity")
        if last and last["entity_id"] == entity_id:
            return dict(last)
        unit = entity_unit(self.hass, entity_id)
        if price_scale(ELECTRICITY, unit, currency) is None:
            return None
        return {
            "source": "entity",
            "entity_id": entity_id,
            "attribute": None,
            "unit": unit,
            "factor": None,
        }

    def _found_inputs(self) -> list[str]:
        """The names of the entities Quick Start took from the profile."""
        job = self._data.get("job", {})
        images = self._data.get("images", {})
        entity_ids = [
            self._data["status"]["entity_id"],
            self._data.get("program", {}).get("entity_id"),
            job.get("entity_id"),
            (job.get("material") or {}).get("entity_id"),
            *job.get("slots", []),
            job.get("loaded_slot"),
            images.get("thumbnail"),
            images.get("camera"),
            *(self._data.get(key, {}).get("entity_id") for key in METERS),
        ]
        return [
            state.name if (state := self.hass.states.get(entity_id)) else entity_id
            for entity_id in entity_ids
            if entity_id
        ]

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._data["printer_device_id"] = user_input.get("device")
            self._data |= self._detected() or {}
            return await self.async_step_name()
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Optional("device"): DeviceSelector()}),
            description_placeholders={
                "integrations": known_integrations(self._data["device_type"])
            },
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

    async def async_step_program(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            entity_id = user_input.get("entity_id")
            attribute = user_input.get("attribute") if entity_id else None
            ignored = [v for v in user_input.get("ignored", []) if v.strip()]
            self._data["program"] = {
                "entity_id": entity_id,
                "attribute": attribute or None,
            } | ({"ignored": ignored} if entity_id and ignored else {})
            return await self._section_done("program")
        stored = self._data.get("program", {})
        offered = (
            offered_values(self.hass, entity_id, stored.get("attribute"))
            if (entity_id := stored.get("entity_id"))
            else []
        )
        schema = vol.Schema(
            {
                vol.Optional("entity_id"): EntitySelector(),
                vol.Optional("attribute"): TextSelector(),
                vol.Optional("ignored"): SelectSelector(
                    SelectSelectorConfig(
                        options=list(
                            dict.fromkeys(offered + stored.get("ignored", []))
                        ),
                        multiple=True,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="program",
            data_schema=self.add_suggested_values_to_schema(
                schema, self._data.get("program")
            ),
        )

    async def async_step_consumption(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        sources = [ConsumptionSource.ENERGY, ConsumptionSource.POWER]
        if Capability.AVERAGE_POWER in self._capabilities():
            sources.append(ConsumptionSource.ESTIMATE)
        if Capability.PROGRAM_CONSUMPTION in self._capabilities():
            sources.append(ConsumptionSource.PER_PROGRAM)
        return self.async_show_menu(
            step_id="consumption", menu_options=[s.value for s in sources]
        )

    async def async_step_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(
            ELECTRICITY, ConsumptionSource.ENERGY, user_input
        )

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(
            ELECTRICITY, ConsumptionSource.POWER, user_input
        )

    async def async_step_energy_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(
            ELECTRICITY, ConsumptionSource.ENERGY, user_input
        )

    async def async_step_power_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(
            ELECTRICITY, ConsumptionSource.POWER, user_input
        )

    async def async_step_water(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        sources = [
            source
            for source in WaterSource
            if source is not WaterSource.PER_PROGRAM
            or Capability.PROGRAM_CONSUMPTION in self._capabilities()
        ]
        return self.async_show_menu(
            step_id="water", menu_options=[_step(WATER, s) for s in sources]
        )

    async def async_step_water_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(WATER, WaterSource.METER, user_input)

    async def async_step_water_flow(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_meter_step(WATER, WaterSource.FLOW, user_input)

    async def async_step_water_meter_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(WATER, WaterSource.METER, user_input)

    async def async_step_water_flow_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_unit_step(WATER, WaterSource.FLOW, user_input)

    async def async_step_water_none(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._meter = {"source": WaterSource.NONE.value}
        return await self._meter_done(WATER)

    async def async_step_per_program(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._meter = {"source": ConsumptionSource.PER_PROGRAM.value}
        return await self._meter_done(ELECTRICITY)

    async def async_step_water_per_program(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._meter = {"source": WaterSource.PER_PROGRAM.value}
        return await self._meter_done(WATER)

    async def _async_meter_step(
        self, quantity: Quantity, source: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._meter = {
                "source": source,
                "entity_id": user_input["entity_id"],
                "attribute": user_input.get("attribute") or None,
                "unit": None,
                "factor": None,
            }
            if self._fills_power_gaps(source):
                self._meter["running_power"] = user_input.get("running_power")
            if self._meter["attribute"]:
                return await self._async_unit_step(quantity, source, None)
            self._meter["unit"] = entity_unit(self.hass, self._meter["entity_id"])
            if self._understood(
                self._meter,
                unit_scale(quantity, source, self._meter["unit"]),
                user_input,
            ):
                return await self._meter_done(quantity)
            errors["entity_id"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("entity_id"): EntitySelector(),
            vol.Optional("attribute"): TextSelector(),
        }
        if self._fills_power_gaps(source):
            schema[vol.Optional("running_power")] = _watts(1)
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=_step(quantity, source),
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or self._stored_meter(quantity, source)
            ),
            errors=errors,
        )

    def _fills_power_gaps(self, source: str) -> bool:
        return (
            source == ConsumptionSource.POWER
            and Capability.AVERAGE_POWER in self._capabilities()
        )

    async def _async_unit_step(
        self, quantity: Quantity, source: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._meter["unit"] = user_input["unit"]
            if self._understood(
                self._meter,
                unit_scale(quantity, source, self._meter["unit"]),
                user_input,
            ):
                return await self._meter_done(quantity)
            errors["unit"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("unit"): SelectSelector(
                SelectSelectorConfig(options=ATTRIBUTE_UNITS[source], custom_value=True)
            )
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=_step(quantity, f"{source}_unit"),
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), user_input or self._stored_meter(quantity, source)
            ),
            errors=errors,
        )

    def _stored_meter(self, quantity: Quantity, source: str) -> dict[str, Any] | None:
        stored: dict[str, Any] | None = self._data.get(quantity.source_key)
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

    async def _meter_done(self, quantity: Quantity) -> SubentryFlowResult:
        self._data[quantity.source_key] = self._meter
        sections = self._sections()
        if quantity.price_key in sections and quantity.price_key not in self._data:
            # A source picked in reconfigure after none needs its price too.
            return await sections[quantity.price_key]()
        return await self._section_done(quantity.source_key)

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
        return self._price_menu(ELECTRICITY)

    async def async_step_fixed_price(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_fixed_price_step(ELECTRICITY, user_input)

    async def async_step_price_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_price_entity_step(ELECTRICITY, user_input)

    async def async_step_price_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_price_unit_step(ELECTRICITY, user_input)

    async def async_step_water_price(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self._price_menu(WATER)

    async def async_step_water_fixed_price(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_fixed_price_step(WATER, user_input)

    async def async_step_water_price_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_price_entity_step(WATER, user_input)

    async def async_step_water_price_unit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_price_unit_step(WATER, user_input)

    def _price_menu(self, quantity: Quantity) -> SubentryFlowResult:
        return self.async_show_menu(
            step_id=quantity.price_key,
            menu_options=[
                _step(quantity, "fixed_price"),
                _step(quantity, "price_entity"),
            ],
        )

    async def _async_fixed_price_step(
        self, quantity: Quantity, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._price = {"source": "fixed", "value": user_input["price"]}
            return await self._price_done(quantity)
        currency = self.hass.config.currency
        schema = vol.Schema(
            {vol.Required("price"): _price_selector(quantity, currency)}
        )
        stored = self._stored_price(quantity, "fixed")
        return self.async_show_form(
            step_id=_step(quantity, "fixed_price"),
            data_schema=self.add_suggested_values_to_schema(
                schema, {"price": stored["value"]} if stored else None
            ),
            description_placeholders={"currency": currency},
        )

    async def _async_price_entity_step(
        self, quantity: Quantity, user_input: dict[str, Any] | None
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
                return await self._async_price_unit_step(quantity, None)
            self._price["unit"] = entity_unit(self.hass, self._price["entity_id"])
            if self._understood(
                self._price,
                price_scale(quantity, self._price["unit"], currency),
                user_input,
            ):
                return await self._price_done(quantity)
            errors["entity_id"] = "unknown_unit"
        schema: dict[Any, Any] = {
            vol.Required("entity_id"): EntitySelector(),
            vol.Optional("attribute"): TextSelector(),
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=_step(quantity, "price_entity"),
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema),
                user_input or self._stored_price(quantity, "entity"),
            ),
            errors=errors,
            description_placeholders={"currency": currency},
        )

    async def _async_price_unit_step(
        self, quantity: Quantity, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        currency = self.hass.config.currency
        if user_input is not None:
            self._price["unit"] = user_input["unit"]
            if self._understood(
                self._price,
                price_scale(quantity, self._price["unit"], currency),
                user_input,
            ):
                return await self._price_done(quantity)
            errors["unit"] = "unknown_unit"
        units = [unit.format(currency=currency) for unit in quantity.price_units]
        schema: dict[Any, Any] = {
            vol.Required("unit"): SelectSelector(
                SelectSelectorConfig(options=units, custom_value=True)
            )
        }
        if errors:
            schema[vol.Optional("factor")] = FACTOR
        return self.async_show_form(
            step_id=_step(quantity, "price_unit"),
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema),
                user_input or self._stored_price(quantity, "entity"),
            ),
            errors=errors,
            description_placeholders={"currency": currency},
        )

    async def _price_done(self, quantity: Quantity) -> SubentryFlowResult:
        self._data[quantity.price_key] = self._price
        return await self._section_done(quantity.price_key)

    def _stored_price(self, quantity: Quantity, source: str) -> dict[str, Any] | None:
        """The Device's price, or for a new Device the last-added Device's one."""
        stored: dict[str, Any] | None = self._data.get(quantity.price_key)
        if stored is None and self.source != SOURCE_RECONFIGURE:
            stored = next(
                (
                    subentry.data[quantity.price_key]
                    for subentry in reversed([*self._get_entry().subentries.values()])
                    if subentry.subentry_type == SUBENTRY_DEVICE
                    and quantity.price_key in subentry.data
                ),
                None,
            )
        return stored if stored and stored["source"] == source else None
