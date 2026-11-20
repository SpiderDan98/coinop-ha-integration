"""Adding Coin-op: a confirmation-only hub flow, allowed once per installation."""

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState, FlowType
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.coinop.const import DOMAIN


async def test_confirmation_creates_the_hub_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["data_schema"] or not result["data_schema"].schema

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    [entry] = hass.config_entries.async_entries(DOMAIN)
    assert entry.title == "Coin-op"
    assert entry.state is ConfigEntryState.LOADED


async def test_confirmation_chains_into_add_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    flow_type, flow_id = result["next_flow"]
    assert flow_type is FlowType.CONFIG_SUBENTRIES_FLOW
    [entry] = hass.config_entries.async_entries(DOMAIN)
    [flow] = hass.config_entries.subentries.async_progress()
    assert flow["flow_id"] == flow_id
    assert flow["handler"] == (entry.entry_id, "device")
    assert flow["step_id"] == "user"


async def test_second_hub_is_refused(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_hub_entry_unloads(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert entry.state is ConfigEntryState.NOT_LOADED
