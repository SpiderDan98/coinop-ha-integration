"""Per-Device sensors: totals over every Run, the current and the last Run."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    Platform,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .cost.projection import projected_total
from .cost.rounding import currency_decimals
from .cost.totals import run_totals
from .device_config import Capability, DeviceConfig
from .entity import DeviceEntity, unique_id
from .models import Run
from .run_book import RunBook
from .runtime import CoinOpConfigEntry


def _cost(key: str, translation_key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=translation_key,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    )


# Each key names the `Totals` field the sensor shows; some only for a Capability.
MATERIAL_USED = "material_grams"
WATER_COST = "water_cost"
WATER_IN_RUNS = "water_litres"
NEEDS = {
    MATERIAL_USED: Capability.MATERIAL,
    WATER_COST: Capability.WATER,
    WATER_IN_RUNS: Capability.WATER,
}
TOTALS = (
    _cost("cost", "total_cost"),
    _cost("electricity_cost", "electricity_cost"),
    _cost(WATER_COST, "water_cost"),
    _cost("material_cost", "material_cost"),
    _cost("other_cost", "other_cost"),
    SensorEntityDescription(
        key=MATERIAL_USED,
        translation_key="material_used",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="energy_kwh",
        translation_key="energy_in_runs",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    ),
    SensorEntityDescription(
        key=WATER_IN_RUNS,
        translation_key="water_in_runs",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="runs", translation_key="runs", state_class=SensorStateClass.TOTAL
    ),
    SensorEntityDescription(
        key="running_hours",
        translation_key="running_time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(key="flagged_runs", translation_key="flagged_runs"),
)
CURRENT_RUN_COST = SensorEntityDescription(
    key="current_run_cost",
    translation_key="current_run_cost",
    device_class=SensorDeviceClass.MONETARY,
    suggested_display_precision=2,
)
PROJECTED_RUN_COST = SensorEntityDescription(
    key="projected_run_cost",
    translation_key="projected_run_cost",
    device_class=SensorDeviceClass.MONETARY,
    suggested_display_precision=2,
)
LAST_RUN_COST = SensorEntityDescription(
    key="last_run_cost",
    translation_key="last_run_cost",
    device_class=SensorDeviceClass.MONETARY,
    suggested_display_precision=2,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CoinOpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    book = entry.runtime_data.book
    for device in entry.runtime_data.devices:
        async_add_entities(
            [
                *(
                    TotalSensor(hass, book, device, description)
                    for description in TOTALS
                    if description.key not in NEEDS
                    or NEEDS[description.key] in device.capabilities
                ),
                CurrentRunCostSensor(hass, book, device, CURRENT_RUN_COST),
                ProjectedRunCostSensor(hass, book, device, PROJECTED_RUN_COST),
                LastRunCostSensor(hass, book, device, LAST_RUN_COST),
            ],
            config_subentry_id=device.device_id,
        )


@callback
def async_remove_lost(
    hass: HomeAssistant, device_id: str, lost: frozenset[Capability]
) -> None:
    """Take the sensors a Device had only for the Capabilities it `lost` out of the
    entity registry: exactly those registered here, by their unique id."""
    registry = er.async_get(hass)
    for key, capability in NEEDS.items():
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, unique_id(device_id, key)
        )
        if capability in lost and entity_id is not None:
            registry.async_remove(entity_id)


class DeviceSensor(DeviceEntity, SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        book: RunBook,
        device: DeviceConfig,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(book, device, description.key)
        self.entity_description = description
        if description.device_class is SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = hass.config.currency


class TotalSensor(DeviceSensor):
    @property
    def native_value(self) -> float:
        value: float = getattr(
            self._book.totals(self._device_id), self.entity_description.key
        )
        return value


class CurrentRunCostSensor(DeviceSensor):
    @property
    def native_value(self) -> float | None:
        run = self._book.open_run(self._device_id)
        return None if run is None else run_totals(run, dt_util.utcnow()).cost

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        run = self._book.open_run(self._device_id)
        if run is None:
            return None
        return {
            "name": run.name,
            "start": run.started,
            "running_hours": run_totals(run, dt_util.utcnow()).running_hours,
            "tags": list(run.tags),
        }


class ProjectedRunCostSensor(DeviceSensor):
    def __init__(
        self,
        hass: HomeAssistant,
        book: RunBook,
        device: DeviceConfig,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(hass, book, device, description)
        self._decimals = currency_decimals(hass.config.currency)

    @property
    def native_value(self) -> float | None:
        run = self._book.open_run(self._device_id)
        total = None if run is None else projected_total(run, self._decimals)
        return None if total is None else float(total)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        run = self._book.open_run(self._device_id)
        if run is None or run.projection is None:
            return None
        return {"ends_at": run.projection.ends_at}


class LastRunCostSensor(DeviceSensor):
    def _last_run(self) -> Run | None:
        ended = [
            run
            for run in self._book.runs()
            if run.device_id == self._device_id and run.ended is not None
        ]
        return max(ended, key=lambda run: run.ended or run.started, default=None)

    @property
    def native_value(self) -> float | None:
        run = self._last_run()
        return None if run is None else run_totals(run, dt_util.utcnow()).cost

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        run = self._last_run()
        if run is None:
            return None
        cost = run_totals(run, dt_util.utcnow()).cost
        parts = (
            {}
            if run.part_count is None
            else {"part_count": run.part_count, "cost_per_part": cost / run.part_count}
        )
        program = (
            {"program": run.program} if Capability.PROGRAM in self._capabilities else {}
        )
        return {
            "name": run.name,
            **program,
            "outcome": run.outcome,
            "start": run.started,
            "end": run.ended,
            **parts,
            "has_flags": bool(run.flags),
            "tags": list(run.tags),
        }
