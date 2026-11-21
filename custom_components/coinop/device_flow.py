"""Add Device and reconfigure: the subentry flow that maps a Device's Device Inputs."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntryState,
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
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN, SUBENTRY_DEVICE
from .device_config import (
    CHOICES,
    DEVICE_TYPES,
    ENDING_TARGETS,
    NO_SOURCE,
    Capability,
    ConsumptionSource,
    Target,
    WaterSource,
    capabilities_of,
    picked_choices,
    picks_capabilities,
    refused_combination,
    stored_capabilities,
)
from .device_inputs import (
    entity_unit,
    offered_values,
    price_scale,
    unit_scale,
    usage_scale,
)
from .profiles import METERS, Candidate, candidates, detect, known_integrations
from .quantities import ELECTRICITY, WATER, Quantity
from .run_book import unfinalised
from .schema import vol
from .sensor import async_remove_lost
from .store import async_stored_runs

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
# The sections only a Device with the Capability has.
NEEDS = {
    "job": Capability.JOB,
    "images": Capability.IMAGES,
    "program": Capability.PROGRAM,
    "water": Capability.WATER,
    "water_price": Capability.WATER,
}
# The sources only a Device with the Capability is offered, by the quantity's section.
SOURCE_NEEDS: dict[str, dict[StrEnum, Capability]] = {
    ELECTRICITY.source_key: {
        ConsumptionSource.ESTIMATE: Capability.AVERAGE_POWER,
        ConsumptionSource.PER_PROGRAM: Capability.PROGRAM_CONSUMPTION,
    },
    WATER.source_key: {WaterSource.PER_PROGRAM: Capability.PROGRAM_CONSUMPTION},
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
    Integration Profile and asks only for what no profile knows. An Other Device's
    menu leads with the step that changes its Type Name and what it has, after
    which reconfigure walks the sections the change brings.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._name = ""
        # The consumption or price section while its unit is still being asked for.
        self._meter: dict[str, Any] = {}
        self._price: dict[str, Any] = {}
        self._job: dict[str, Any] = {}
        # The sections reconfigure walks before it returns to its menu.
        self._walking: frozenset[str] = frozenset()
        self._candidate: Candidate | None = None

    def _capabilities(self) -> frozenset[Capability]:
        return capabilities_of(self._data)

    def _sections(self) -> dict[str, Callable[[], Awaitable[SubentryFlowResult]]]:
        """Each section's first step, in Add Device order, as the Device has them."""
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
        for quantity in (ELECTRICITY, WATER):
            source = (self._data.get(quantity.source_key) or {}).get("source")
            if source == NO_SOURCE:
                del sections[quantity.price_key]
        return self._fitting(sections)

    def _fitting[T](self, sections: Mapping[str, T]) -> dict[str, T]:
        """Those of the sections the Device has: a profile also finds a washing
        machine's water meter for a Device added as a tumble dryer."""
        capabilities = self._capabilities()
        return {
            name: section
            for name, section in sections.items()
            if name not in NEEDS or NEEDS[name] in capabilities
        }

    async def _section_done(self, section: str) -> SubentryFlowResult:
        names = list(self._sections())
        return await self._walk(names[names.index(section) + 1 :])

    async def _walk(self, following: list[str]) -> SubentryFlowResult:
        """Go on to the first of the `following` sections. Reconfigure skips those it
        isn't walking and returns to its menu after the last; Add Device is done."""
        if self.source == SOURCE_RECONFIGURE:
            following = [name for name in following if name in self._walking]
            if not following:
                self._walking = frozenset()
                return await self.async_step_reconfigure()
        if following:
            return await self._sections()[following[0]]()
        return self.async_create_entry(title=self._name, data=self._data)

    async def _walk_before_menu(self, sections: Iterable[str]) -> SubentryFlowResult:
        """Reconfigure walks those of `sections` the Device has, in Add Device's
        order, before it shows its menu again."""
        self._walking = frozenset(sections)
        return await self._walk(list(self._sections()))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._data:
            self._data = dict(self._get_reconfigure_subentry().data)
        # What the Device has decides its sections, so it leads them.
        choices = ["other"] if picks_capabilities(self._data["device_type"]) else []
        detect_again = ["detect"] if self._detected() else []
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[*choices, *self._sections(), *detect_again, "save"],
        )

    def _detected(self) -> dict[str, Any] | None:
        found = detect(
            self.hass, self._data["device_type"], self._data.get("printer_device_id")
        )
        return found and self._fitting(found)

    async def async_step_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Walk the sections the profile fills, pre-filled with what it finds now."""
        detected = {
            section: values
            for section, values in (self._detected() or {}).items()
            if section not in METERS
        }
        for section, values in detected.items():
            self._data[section] = (self._data.get(section) or {}) | values
        return await self._walk_before_menu(detected)

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        had, has = capabilities_of(subentry.data), self._capabilities()
        # A Run may have started after the `other` step let the change through.
        if has != had and (refusal := await self._async_refusal()):
            return self.async_abort(reason=refusal)
        # Only here: a setup or reload must never cost a Device an entity.
        async_remove_lost(self.hass, subentry.subentry_id, had - has)
        return self.async_update_and_abort(self._get_entry(), subentry, data=self._data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The Device Type, fixed once the Device is added; Quick Start comes first
        where it has a device to offer."""
        if user_input is not None:
            self._data["device_type"] = user_input["device_type"]
            if picks_capabilities(self._data["device_type"]):
                return await self.async_step_other()
            return await self.async_step_device()
        if self._quick_start_devices():
            return await self.async_step_quick_start()
        return self._device_type_form()

    def _device_type_form(self) -> SubentryFlowResult:
        return self.async_show_form(
            step_id="user", data_schema=self._device_type_schema(list(DEVICE_TYPES))
        )

    @staticmethod
    def _device_type_schema(device_types: list[str]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("device_type"): SelectSelector(
                    SelectSelectorConfig(
                        options=device_types,
                        translation_key="device_type",
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )

    async def async_step_other(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """What a shipped Device Type answers by itself: the Type Name the Device is
        listed under and what it has."""
        if self.source == SOURCE_RECONFIGURE and (
            refusal := await self._async_refusal()
        ):
            return self.async_abort(reason=refusal)
        errors: dict[str, str] = {}
        if user_input is not None:
            type_name = user_input["type_name"].strip()
            picked = [choice for choice in CHOICES if user_input[choice]]
            if not type_name:
                errors["type_name"] = "type_name_required"
            if refused := refused_combination(picked):
                errors["base"] = refused
            if not errors:
                self._data["type_name"] = type_name
                self._data["capabilities"] = stored_capabilities(picked)
                if self.source == SOURCE_RECONFIGURE:
                    return await self._async_fit_sections()
                return await self.async_step_device()
        known = list(
            dict.fromkeys(
                type_name
                for subentry in self._get_entry().subentries.values()
                if (type_name := subentry.data.get("type_name"))
            )
        )
        schema = vol.Schema(
            {
                # A picker without anything to pick would only hide the text field.
                vol.Required("type_name"): SelectSelector(
                    SelectSelectorConfig(options=known, custom_value=True)
                )
                if known
                else TextSelector(),
                **{
                    vol.Optional(choice, default=False): BooleanSelector()
                    for choice in CHOICES
                },
            }
        )
        return self.async_show_form(
            step_id="other",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._stored_choices()
            ),
            errors=errors,
        )

    async def _async_fit_sections(self) -> SubentryFlowResult:
        """Fit the stored sections to what the Device has now: drop those it no
        longer has and each source it is no longer offered, then walk those it
        stores nothing for."""
        for section in NEEDS.keys() - self._fitting(NEEDS).keys():
            self._data.pop(section, None)
        for quantity in (ELECTRICITY, WATER):
            stored = self._data.get(quantity.source_key)
            if stored and stored["source"] not in self._sources(quantity):
                del self._data[quantity.source_key]
        power = self._stored_meter(ELECTRICITY, ConsumptionSource.POWER)
        if power and not self._fills_power_gaps(power["source"]):
            # The average power its gaps were filled from went with the estimate.
            self._data[ELECTRICITY.source_key] = {
                key: value for key, value in power.items() if key != "running_power"
            }
        return await self._walk_before_menu(self._sections().keys() - self._data.keys())

    async def _async_refusal(self) -> str | None:
        """Why what the Device being reconfigured has can't change now, as the abort
        reason: a Run of it isn't final yet, or nothing can tell whether one is."""
        entry = self._get_entry()
        device_id = self._get_reconfigure_subentry().subentry_id
        if entry.state is ConfigEntryState.LOADED:
            changing = entry.runtime_data.book.unfinalised(device_id)
            return "run_open" if changing else None
        # A stored Run goes on once the hub entry is loaded again.
        if (stored := await async_stored_runs(self.hass)) is None:
            return "runs_unreadable"
        return "run_open_not_loaded" if unfinalised(stored, device_id) else None

    def _stored_choices(self) -> dict[str, Any] | None:
        """The `other` step's input as the Device being reconfigured has it."""
        if self.source != SOURCE_RECONFIGURE:
            return None
        picked = picked_choices(self._capabilities())
        return {"type_name": self._data["type_name"]} | {
            choice: choice in picked for choice in CHOICES
        }

    def _quick_start_devices(self) -> dict[str, Candidate]:
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
            and not self._status_used_elsewhere(
                candidate.sections["status"]["entity_id"]
            )
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
            self._candidate = offered[device_id]
            self._name = names[device_id]
            self._data = {"printer_device_id": device_id}
            return await self.async_step_quick_start_device_type()
        options = [
            SelectOptionDict(
                value=device_id, label=f"{names[device_id]} · {candidate.integration}"
            )
            for device_id, candidate in offered.items()
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

    async def async_step_quick_start_device_type(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The Device Type of a device whose kind its integration doesn't tell, among
        those the integration serves; a device whose kind is told isn't asked."""
        candidate = self._picked()
        device_types = [t for t in DEVICE_TYPES if t in candidate.device_types]
        if user_input is None and len(device_types) > 1:
            return self.async_show_form(
                step_id="quick_start_device_type",
                data_schema=self._device_type_schema(device_types),
                description_placeholders={
                    "device": self._name,
                    "integration": candidate.integration,
                },
            )
        self._data["device_type"] = (
            user_input["device_type"] if user_input else device_types[0]
        )
        return await self.async_step_quick_start_confirm()

    def _picked(self) -> Candidate:
        """The HA device picked in Quick Start, which its later steps are about."""
        assert self._candidate is not None
        return self._candidate

    def _found_sections(self) -> dict[str, Any]:
        """The picked device's sections as the steps store them: those its Device Type
        has, unused what the profile didn't find, a meter with its unit."""
        sections = self._fitting(self._picked().sections)
        stored = {
            name: values
            for name, values in sections.items()
            if name not in UNUSED and name not in METERS
        }
        stored |= {
            name: unused | sections.get(name, {})
            for name, unused in self._fitting(UNUSED).items()
        }
        for quantity in (ELECTRICITY, WATER):
            found = sections.get(quantity.source_key)
            if found and (
                meter := self._meter_of(quantity, found["entity_id"], [found["source"]])
            ):
                stored[quantity.source_key] = meter
        return stored

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
        found = self._found_sections()
        needs_meter = ELECTRICITY.source_key not in found
        if user_input is not None:
            data = self._data | found
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
                    data["water"] = {"source": NO_SOURCE}
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
                "device_type": await self._device_type_name(),
                "integration": self._picked().integration,
                "inputs": "\n".join(f"- {name}" for name in self._found_inputs(found)),
                "currency": currency,
            },
        )

    async def _device_type_name(self) -> str:
        """The Device Type's name in HA's language: a flow doesn't know its user's."""
        names = await async_get_translations(
            self.hass, self.hass.config.language, "selector", [DOMAIN]
        )
        key = f"selector.device_type.options.{self._data['device_type']}"
        return names[f"component.{DOMAIN}.{key}"]

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

    def _found_inputs(self, found: dict[str, Any]) -> list[str]:
        """The names of the entities Quick Start took from the profile."""
        job = found.get("job", {})
        images = found.get("images", {})
        entity_ids = [
            found["status"]["entity_id"],
            found.get("program", {}).get("entity_id"),
            job.get("entity_id"),
            (job.get("material") or {}).get("entity_id"),
            *job.get("slots", []),
            job.get("loaded_slot"),
            images.get("thumbnail"),
            images.get("camera"),
            *(found.get(key, {}).get("entity_id") for key in METERS),
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
        integrations = known_integrations(self._data["device_type"])
        return self.async_show_form(
            # A step has one text, so the one that names no integration is its own.
            step_id="device" if integrations else "device_without_profile",
            data_schema=vol.Schema({vol.Optional("device"): DeviceSelector()}),
            description_placeholders=(
                {"integrations": integrations} if integrations else None
            ),
        )

    async_step_device_without_profile = async_step_device

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
        return self._source_menu(ELECTRICITY)

    def _source_menu(self, quantity: Quantity) -> SubentryFlowResult:
        return self.async_show_menu(
            step_id=quantity.source_key,
            menu_options=[_step(quantity, s) for s in self._sources(quantity)],
        )

    def _sources(self, quantity: Quantity) -> list[str]:
        """Where the Device can take the quantity from, as its source menu offers it."""
        capabilities = self._capabilities()
        needs = SOURCE_NEEDS[quantity.source_key]
        return [
            source.value
            for source in quantity.sources
            if source not in needs or needs[source] in capabilities
        ]

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
        return self._source_menu(WATER)

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

    async def async_step_none(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._meter = {"source": NO_SOURCE}
        return await self._meter_done(ELECTRICITY)

    async def async_step_water_none(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._meter = {"source": NO_SOURCE}
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
        if quantity.price_key not in self._data:
            # A source picked in reconfigure after none needs its price too.
            self._walking |= {quantity.price_key}
        return await self._section_done(quantity.source_key)

    async def async_step_estimate(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._meter = {
                "source": "estimate",
                "running_power": user_input["running_power"],
                "paused_power": user_input.get("paused_power"),
            }
            return await self._meter_done(ELECTRICITY)
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
