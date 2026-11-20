"""Backend translations: complete in every shipped language and loadable by HA."""

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
import pytest

from custom_components.coinop.const import DOMAIN

from .clock import Clock
from .devices import add_device, add_hub

TRANSLATIONS = Path(__file__).parents[1] / "custom_components" / DOMAIN / "translations"
STATEMENT = TRANSLATIONS.parent / "statement" / "strings"


def _keys(tree: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in tree.items():
        path = f"{prefix}{name}"
        keys |= _keys(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


def _load(language: str, folder: Path = TRANSLATIONS) -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(
        (folder / f"{language}.json").read_text(encoding="utf-8")
    )
    return tree


@pytest.mark.parametrize(
    "language",
    sorted({"de"} | {path.stem for path in TRANSLATIONS.glob("*.json")} - {"en"}),
)
def test_language_has_the_same_keys_as_english(language: str) -> None:
    english, other = _keys(_load("en")), _keys(_load(language))

    assert {
        "missing": sorted(english - other),
        "not in en.json": sorted(other - english),
    } == {"missing": [], "not in en.json": []}


def test_the_cost_statement_has_the_same_strings_in_german_as_in_english() -> None:
    english, german = _keys(_load("en", STATEMENT)), _keys(_load("de", STATEMENT))

    assert {
        "missing": sorted(english - german),
        "not in en.json": sorted(german - english),
    } == {"missing": [], "not in en.json": []}


@pytest.mark.parametrize("language", ["en", "de"])
async def test_hub_flow_texts_load_in_home_assistant(
    hass: HomeAssistant, language: str
) -> None:
    translations = await async_get_translations(hass, language, "config", [DOMAIN])

    prefix = f"component.{DOMAIN}.config"
    assert translations[f"{prefix}.step.user.description"]
    assert translations[f"{prefix}.abort.single_instance_allowed"]


@pytest.mark.parametrize("language", ["en", "de"])
async def test_add_device_texts_load_in_home_assistant(
    hass: HomeAssistant, language: str
) -> None:
    translations = await async_get_translations(
        hass, language, "config_subentries", [DOMAIN]
    )

    prefix = f"component.{DOMAIN}.config_subentries.device"
    assert translations[f"{prefix}.initiate_flow.user"]
    assert translations[f"{prefix}.step.estimate.data_description.running_power"]
    assert translations[f"{prefix}.error.no_ending_value"]


async def test_entities_are_named_in_the_configured_language(
    hass: HomeAssistant, clock: Clock
) -> None:
    hass.config.language = "de"
    entry = await add_hub(hass)
    await add_device(hass, entry)

    names = {
        state.entity_id: state.name
        for state in hass.states.async_all()
        if state.entity_id.startswith(("sensor.kobra", "event.kobra"))
    }
    assert names["sensor.kobra_gesamtkosten"] == "Kobra Gesamtkosten"
    assert names["sensor.kobra_kosten_letzter_lauf"] == "Kobra Kosten letzter Lauf"
    assert names["event.kobra_lauf"] == "Kobra Lauf"
    assert all(name.startswith("Kobra ") for name in names.values())
