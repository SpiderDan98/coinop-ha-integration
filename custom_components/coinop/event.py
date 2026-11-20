"""Per-Device Run event: `started` when a Run opens, `ended` once it is finalised."""

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .cost.totals import run_totals
from .device_config import DeviceConfig
from .entity import DeviceEntity
from .models import Run
from .run_book import RunBook, RunChange
from .runtime import CoinOpConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CoinOpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    book = entry.runtime_data.book
    for device in entry.runtime_data.devices:
        async_add_entities(
            [RunEvent(book, device)], config_subentry_id=device.device_id
        )


RUN_EVENT = EventEntityDescription(
    key="run",
    translation_key="run",
    event_types=[RunChange.STARTED, RunChange.ENDED],
)


class RunEvent(DeviceEntity, EventEntity):
    def __init__(self, book: RunBook, device: DeviceConfig) -> None:
        super().__init__(book, device, RUN_EVENT.key)
        self.entity_description = RUN_EVENT

    @callback
    def _on_run_change(self, change: RunChange, run: Run) -> None:
        # Only finalisation sends ENDED, so later corrections never refire it.
        if change is RunChange.STARTED:
            self._trigger_event(
                change, {"name": run.name, "start": run.started, "tags": list(run.tags)}
            )
        elif change is RunChange.ENDED:
            totals = run_totals(run, dt_util.utcnow())
            self._trigger_event(
                change,
                {
                    "name": run.name,
                    "outcome": run.outcome,
                    "start": run.started,
                    "end": run.ended,
                    "running_hours": totals.running_hours,
                    "total_cost": totals.cost,
                    "cost_per_part": totals.cost / run.part_count,
                    "part_count": run.part_count,
                    "energy_kwh": totals.energy_kwh,
                    "material_grams": totals.material_grams,
                    "has_flags": bool(run.flags),
                    "tags": list(run.tags),
                },
            )
        else:
            return
        self.async_write_ha_state()
