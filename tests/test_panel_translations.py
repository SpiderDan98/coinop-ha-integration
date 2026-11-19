"""Panel translations: complete in every language, and in step with the backend's."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
PANEL = ROOT / "frontend" / "src" / "translations"
BACKEND = ROOT / "custom_components" / "wattbill" / "translations"
LANGUAGES = sorted(path.stem for path in PANEL.glob("*.json"))

# Terms both sides show: panel key -> backend key. Add a pair whenever the panel
# shows a term the backend also translates (e.g. Outcome states, sensor names).
SHARED_TERMS = {
    "runs.title": "entity.sensor.runs.name",
    "run.device": "config_subentries.device.entry_type",
    "run.running_time": "entity.sensor.running_time.name",
    "run.started": "entity.event.run.state_attributes.event_type.state.started",
    "run.ended": "entity.event.run.state_attributes.event_type.state.ended",
    "device.status": "config_subentries.device.step.status.title",
    "device.job": "config_subentries.device.step.job.title",
    "device.consumption": (
        "config_subentries.device.step.reconfigure.menu_options.consumption"
    ),
    "device.price": "config_subentries.device.step.price.title",
    "consumption.energy": "config_subentries.device.step.consumption.menu_options.energy",
    "consumption.power": "config_subentries.device.step.consumption.menu_options.power",
    "consumption.estimate": (
        "config_subentries.device.step.consumption.menu_options.estimate"
    ),
}


def _panel(language: str) -> dict[str, str]:
    strings: dict[str, str] = json.loads(
        (PANEL / f"{language}.json").read_text(encoding="utf-8")
    )
    return strings


def _backend(language: str) -> dict[str, str]:
    def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, str]:
        flat: dict[str, str] = {}
        for name, value in tree.items():
            if isinstance(value, dict):
                flat |= flatten(value, f"{prefix}{name}.")
            else:
                flat[f"{prefix}{name}"] = value
        return flat

    return flatten(json.loads((BACKEND / f"{language}.json").read_text("utf-8")))


def test_the_panel_ships_english_and_german() -> None:
    assert {"en", "de"} <= set(LANGUAGES)


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "en"])
def test_language_has_the_same_keys_as_english(language: str) -> None:
    english, other = set(_panel("en")), set(_panel(language))

    assert {
        "missing": sorted(english - other),
        "not in en.json": sorted(other - english),
    } == {"missing": [], "not in en.json": []}


@pytest.mark.parametrize("language", LANGUAGES)
def test_shared_terms_read_the_same_in_panel_and_backend(language: str) -> None:
    panel, backend = _panel(language), _backend(language)

    assert {key: panel[key] for key in SHARED_TERMS} == {
        key: backend[backend_key] for key, backend_key in SHARED_TERMS.items()
    }
