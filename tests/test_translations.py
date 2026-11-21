"""Backend translations: complete in every shipped language and loadable by HA."""

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
import pytest

from custom_components.coinop.const import DOMAIN

from .clock import Clock
from .devices import (
    add_device,
    add_hub,
    configure,
    open_device_types,
    open_other,
    start_reconfigure,
)
from .test_device_flow import fields, offered
from .test_other_devices import add_kiln, set_kiln

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
    assert "{integrations}" in translations[f"{prefix}.step.device.description"]
    unnamed = translations[f"{prefix}.step.device_without_profile.description"]
    assert unnamed
    assert "{" not in unnamed
    asked = translations[f"{prefix}.step.quick_start_device_type.description"]
    assert all(placeholder in asked for placeholder in ("{device}", "{integration}"))
    assert translations[f"{prefix}.step.quick_start_device_type.data.device_type"]
    confirm = translations[f"{prefix}.step.quick_start_confirm.description"]
    assert all(
        placeholder in confirm
        for placeholder in ("{device}", "{device_type}", "{integration}", "{inputs}")
    )


@pytest.mark.parametrize(
    ("language", "words", "device_inputs"),
    [
        # "Loaded slot" names a Device Input of the job step, not a load of laundry.
        ("en", ("print", "wash", "laundry", "load", "machine"), ("loaded slot",)),
        ("de", ("druck", "wasch", "wäsche", "maschine"), ()),
    ],
)
def test_steps_shared_between_device_types_speak_of_none_of_them(
    language: str, words: tuple[str, ...], device_inputs: tuple[str, ...]
) -> None:
    def plain(text: str) -> str:
        """`text` in lower case, without the Device Inputs' names."""
        lowered = text.lower()
        for name in device_inputs:
            lowered = lowered.replace(name, "")
        return lowered

    def texts(tree: dict[str, Any]) -> list[str]:
        return [
            text
            for value in tree.values()
            for text in (texts(value) if isinstance(value, dict) else [value])
        ]

    steps = _load(language)["config_subentries"]["device"]["step"]
    shared = [text for step in steps.values() for text in texts(step)]

    assert [text for text in shared if any(word in plain(text) for word in words)] == []


@pytest.mark.parametrize(
    ("language", "words"), [("en", ("load", "laundry")), ("de", ("wäsche",))]
)
def test_the_hub_description_speaks_of_no_laundry(
    language: str, words: tuple[str, ...]
) -> None:
    description = _load(language)["config"]["step"]["user"]["description"]

    assert not any(word in description.lower() for word in words)


@pytest.mark.parametrize("language", ["en", "de"])
async def test_quick_starts_manual_choice_is_translated(
    hass: HomeAssistant, language: str
) -> None:
    translations = await async_get_translations(hass, language, "selector", [DOMAIN])

    assert translations[
        f"component.{DOMAIN}.selector.quick_start_device.options.manual"
    ] not in ("", "manual")


@pytest.mark.parametrize("language", ["en", "de"])
async def test_every_device_type_add_device_offers_is_named(
    hass: HomeAssistant, language: str
) -> None:
    entry = await add_hub(hass)
    result = await open_device_types(hass, entry)

    named = _load(language)["selector"]["device_type"]["options"]

    # Quick Start's Device Type step offers the way back to its device list too.
    assert list(named) == [*offered(result, "device_type"), "pick_another_device"]
    assert all(named.values())


@pytest.mark.parametrize(
    ("language", "other", "type_name", "unseen"),
    [
        ("en", "Other", "Type Name", "capabilit"),
        ("de", "Sonstiges", "Typbezeichnung", "fähigkeit"),
    ],
)
async def test_what_an_other_device_can_have_is_named_and_explained(
    hass: HomeAssistant, language: str, other: str, type_name: str, unseen: str
) -> None:
    entry = await add_hub(hass)
    result = await open_device_types(hass, entry)
    result = await configure(hass, result, {"device_type": "other"})

    texts = await async_get_translations(hass, language, "config_subentries", [DOMAIN])
    names = await async_get_translations(hass, language, "selector", [DOMAIN])

    assert names[f"component.{DOMAIN}.selector.device_type.options.other"] == other
    prefix = f"component.{DOMAIN}.config_subentries.device"
    step = f"{prefix}.step.{result['step_id']}"
    assert texts[f"{step}.title"]
    assert texts[f"{step}.description"]
    assert texts[f"{step}.data.type_name"] == type_name
    for field in fields(result):
        assert texts[f"{step}.data.{field}"], field
        assert texts[f"{step}.data_description.{field}"], field
    assert texts[f"{prefix}.error.type_name_required"]
    shown = [text for key, text in texts.items() if key.startswith(step)]
    assert [text for text in shown if unseen in text.lower()] == []


@pytest.mark.parametrize(
    ("language", "quoted", "by_hand"),
    [("en", "“{}”", "by hand"), ("de", "„{}“", "von Hand")],
)
async def test_the_other_step_says_which_choices_cant_be_combined_and_what_to_do_instead(
    hass: HomeAssistant, language: str, quoted: str, by_hand: str
) -> None:
    texts = await async_get_translations(hass, language, "config_subentries", [DOMAIN])

    prefix = f"component.{DOMAIN}.config_subentries.device"
    description = texts[f"{prefix}.step.other.description"]
    refusal = texts[f"{prefix}.error.job_with_program_or_doses"]
    # Stated before anything is picked, and again when the mix is refused.
    for text in (description, refusal):
        for choice in ("job", "program", "doses"):
            name = texts[f"{prefix}.step.other.data.{choice}"]
            assert quoted.format(name) in text, (choice, text)
    assert by_hand in description


@pytest.mark.parametrize(
    ("language", "quoted", "unseen"),
    [("en", "“{}”", "capabilit"), ("de", "„{}“", "fähigkeit")],
)
async def test_changing_what_an_other_device_has_is_named_announced_and_refused_in_words(
    hass: HomeAssistant, language: str, quoted: str, unseen: str
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    menu = await start_reconfigure(hass, entry, kiln)
    await set_kiln(hass, "on")
    refused = await configure(hass, menu, {"next_step_id": "other"})

    texts = await async_get_translations(hass, language, "config_subentries", [DOMAIN])

    prefix = f"component.{DOMAIN}.config_subentries.device"
    named = [
        texts.get(f"{prefix}.step.reconfigure.menu_options.{option}", "")
        for option in menu["menu_options"]
    ]
    assert all(named), named
    refusal = texts[f"{prefix}.abort.{refused['reason']}"]
    assert refusal
    assert [text for text in (named[0], refusal) if unseen in text.lower()] == []
    # Add Device says where its answers can be changed, before they are given.
    reconfigure = texts[f"{prefix}.step.reconfigure.title"]
    assert quoted.format(reconfigure) in texts[f"{prefix}.step.other.description"]


@pytest.mark.parametrize(
    ("language", "unseen"), [("en", "capabilit"), ("de", "fähigkeit")]
)
async def test_a_change_refused_while_coinop_is_not_loaded_says_why_in_its_own_words(
    hass: HomeAssistant, hass_storage: dict[str, Any], language: str, unseen: str
) -> None:
    entry = await add_hub(hass)
    kiln = await add_kiln(hass, entry=entry)
    await set_kiln(hass, "on")
    loaded = await open_other(hass, entry, kiln)
    await hass.config_entries.async_unload(entry.entry_id)
    with_a_run = await open_other(hass, entry, kiln)
    hass_storage["coinop.live"]["version"] += 1
    unreadable = await open_other(hass, entry, kiln)

    texts = await async_get_translations(hass, language, "config_subentries", [DOMAIN])

    refusals = [
        texts.get(f"component.{DOMAIN}.config_subentries.device.abort.{reason}")
        for reason in (loaded["reason"], with_a_run["reason"], unreadable["reason"])
    ]
    assert all(refusals), refusals
    assert len(set(refusals)) == 3
    assert [text for text in refusals if text and unseen in text.lower()] == []


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
