"""The supported integrations page: every Integration Profile, linked from Quick Start."""

import json
from pathlib import Path
import re
from typing import Any

from homeassistant.core import HomeAssistant
import pytest

from custom_components.coinop.profiles import INTEGRATIONS

from .test_quick_start import QUICK_START_STATES, open_quick_start_in

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "docs" / "supported-integrations.md"
REPOSITORY = "https://github.com/SpiderDan98/coinop-ha-integration/blob/main/"


def anchors(markdown: str) -> set[str]:
    """The anchors GitHub gives the headings of `markdown`."""
    return {
        re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
        for heading in re.findall(r"^#+ (.+)$", markdown, re.MULTILINE)
    }


@pytest.mark.parametrize("domain", list(INTEGRATIONS))
def test_the_page_lists_every_integration_with_a_profile(domain: str) -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert f"(`{domain}`" in page
    assert INTEGRATIONS[domain].name in page


def test_the_page_says_why_a_device_isnt_offered() -> None:
    assert "why-isnt-my-device-offered" in anchors(PAGE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("document", ["README.md", "docs/supported-integrations.md"])
def test_every_link_to_a_section_finds_its_heading(document: str) -> None:
    path = ROOT / document
    own = anchors(path.read_text(encoding="utf-8"))
    for target, anchor in re.findall(
        r"\]\(([^)#\s]*)#([^)\s]+)\)", path.read_text(encoding="utf-8")
    ):
        if target.startswith("http"):
            continue
        linked = (path.parent / target).read_text(encoding="utf-8") if target else ""
        assert anchor in (anchors(linked) if target else own), f"{target}#{anchor}"


@pytest.mark.parametrize("state", QUICK_START_STATES)
async def test_every_quick_start_state_links_to_the_page(
    hass: HomeAssistant, state: str
) -> None:
    result = await open_quick_start_in(hass, state)

    url = result["description_placeholders"]["supported_integrations"]
    assert url.startswith(REPOSITORY)
    assert (ROOT / url.removeprefix(REPOSITORY)) == PAGE


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("state", QUICK_START_STATES)
def test_every_quick_start_text_shows_the_link(language: str, state: str) -> None:
    texts: dict[str, Any] = json.loads(
        (ROOT / "custom_components/coinop/translations" / f"{language}.json").read_text(
            encoding="utf-8"
        )
    )

    description = texts["config_subentries"]["device"]["step"][state]["description"]

    assert "]({supported_integrations})" in description
