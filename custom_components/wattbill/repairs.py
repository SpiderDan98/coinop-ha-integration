"""Fix flow for missing stored data: restore a backup, or deliberately start fresh."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

if TYPE_CHECKING:
    # Missing in older HA releases; annotations are never evaluated at runtime.
    from homeassistant.components.repairs import RepairsFlowResult

from .const import DOMAIN
from .schema import vol
from .store import ISSUE_DATA_MISSING, async_start_fresh


class DataMissingFlow(RepairsFlow):
    @property
    def _placeholders(self) -> dict[str, str] | None:
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, ISSUE_DATA_MISSING)
        return None if issue is None else issue.translation_placeholders

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["restore", "fresh_start"],
            description_placeholders=self._placeholders,
        )

    async def async_step_restore(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        return self.async_abort(reason="restore")

    async def async_step_fresh_start(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="fresh_start",
                data_schema=vol.Schema({}),
                description_placeholders=self._placeholders,
            )
        [entry] = self.hass.config_entries.async_entries(DOMAIN)
        async_start_fresh(self.hass, entry)
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return DataMissingFlow()
