"""Backend translations: complete in every shipped language and loadable by HA."""

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
import pytest

from custom_components.wattbill.const import DOMAIN

TRANSLATIONS = Path(__file__).parents[1] / "custom_components" / DOMAIN / "translations"


def _keys(tree: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in tree.items():
        path = f"{prefix}{name}"
        keys |= _keys(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


def _load(language: str) -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(
        (TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")
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


@pytest.mark.parametrize("language", ["en", "de"])
async def test_hub_flow_texts_load_in_home_assistant(
    hass: HomeAssistant, language: str
) -> None:
    translations = await async_get_translations(hass, language, "config", [DOMAIN])

    prefix = f"component.{DOMAIN}.config"
    assert translations[f"{prefix}.step.user.description"]
    assert translations[f"{prefix}.abort.single_instance_allowed"]
