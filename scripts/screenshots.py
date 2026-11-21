"""The README's screenshots, taken in the dev container with its Presets.

Usage: uv run scripts/screenshots.py [name ...]

Starts the dev container if it isn't running (and stops it again afterwards), loads
each Preset a screenshot needs and saves the screenshots, in the dark theme at a
fixed size, to docs/images/screenshots. Names limit it to those screenshots.
Drives the installed Google Chrome, so Playwright needs no browser of its own.
"""

from collections.abc import Callable
import subprocess
import sys

import devenv
from playwright.sync_api import Page, sync_playwright

OUT = devenv.ROOT / "docs" / "images" / "screenshots"
PANEL = f"{devenv.URL}/coinop"
# The dev container's Scenario button isn't part of Coin-op.
STYLE = "ha-icon-button.dev { display: none !important; }"
# Lit renders a moment after the data arrives; a click before then misses its target.
SETTLE_MS = 2500


def settle(page: Page, selector: str) -> None:
    page.wait_for_selector(selector, state="attached", timeout=60_000)
    page.wait_for_timeout(SETTLE_MS)


def panel(path: str, selector: str) -> Callable[[Page], None]:
    def go(page: Page) -> None:
        page.goto(f"{PANEL}/{path}")
        settle(page, selector)

    return go


def first_run(page: Page) -> None:
    panel("runs", "a.tile")(page)
    page.locator("a.tile").first.click()
    settle(page, "coinop-run-page")


def statement(page: Page) -> None:
    panel("runs", "a.tile")(page)
    page.locator("ha-button.select-all").click()
    page.locator("ha-button.statement").click()
    settle(page, "coinop-statement-dialog")


def quick_start(page: Page) -> None:
    page.goto(f"{devenv.URL}/config/integrations/integration/coinop")
    page.get_by_role("button", name="Add Device").click()
    settle(page, "dialog-data-entry-flow")


# By Preset, so each is loaded once.
SHOTS: dict[str, dict[str, Callable[[Page], None]]] = {
    "long-history": {
        "overview": panel("", "coinop-overview"),
        "runs": panel("runs", "a.tile"),
        "run": first_run,
        "analysis": panel("analysis", "coinop-analysis-page"),
        "statement": statement,
    },
    "washing-machine": {"washing-machine": first_run},
    "quick-start": {"quick-start": quick_start},
}


def main() -> None:
    wanted = set(sys.argv[1:])
    unknown = wanted - {name for shots in SHOTS.values() for name in shots}
    if unknown:
        sys.exit(f"Unknown screenshots: {', '.join(sorted(unknown))}")
    started = not running()
    if started:
        devenv.build_panel()
        devenv.start()
        devenv.prepare("empty")
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                device_scale_factor=1.5,
                color_scheme="dark",
                locale="en-US",
            )
            # HA keeps these frontend settings in the browser.
            context.add_init_script(
                "localStorage.setItem('dockedSidebar', '\"always_hidden\"');"
                "localStorage.setItem('selectedLanguage', '\"en\"');"
            )
            page = context.new_page()
            for preset, shots in SHOTS.items():
                shots = {n: s for n, s in shots.items() if not wanted or n in wanted}
                if not shots:
                    continue
                devenv.load(preset)
                for name, show in shots.items():
                    show(page)
                    page.screenshot(
                        path=OUT / f"{name}.png", style=STYLE, animations="disabled"
                    )
                    print(f"Saved {name}.png", flush=True)
            browser.close()
    finally:
        if started:
            devenv.stop()


def running() -> bool:
    state = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", devenv.CONTAINER],
        capture_output=True,
        text=True,
    )
    return state.stdout.strip() == "true"


if __name__ == "__main__":
    main()
