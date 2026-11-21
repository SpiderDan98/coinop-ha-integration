"""The README's screenshots, taken in the dev container with its Presets.

Usage: uv run scripts/screenshots.py [name ...]

Starts the dev container if it isn't running (and stops it again afterwards), loads
each Preset a screenshot needs and saves the screenshots, in the dark theme at a
fixed size, to docs/images/screenshots. The statement image is instead the first
page of the Cost Statement PDF the panel downloads. Names limit it to those
screenshots. Drives the installed Google Chrome, so Playwright needs no browser of
its own.
"""

from collections.abc import Callable
import io
import subprocess
import sys

import devenv
from playwright.sync_api import Page, sync_playwright
import pypdfium2 as pdfium

OUT = devenv.ROOT / "docs" / "images" / "screenshots"
PANEL = f"{devenv.URL}/coinop"
# The dev container's Scenario button isn't part of Coin-op.
STYLE = "ha-icon-button.dev { display: none !important; }"
# Lit renders a moment after the data arrives; a click before then misses its target.
SETTLE_MS = 2500
# The newest Runs, few enough to fit the Cost Statement on one page.
STATEMENT_RUNS = 4
# PDF points to pixels: an A4 page comes out 1190 pixels wide.
PDF_SCALE = 2


def settle(page: Page, selector: str) -> None:
    page.wait_for_selector(selector, state="attached", timeout=60_000)
    page.wait_for_timeout(SETTLE_MS)


def screenshot(page: Page) -> bytes:
    return page.screenshot(style=STYLE, animations="disabled")


def panel(path: str, selector: str) -> Callable[[Page], bytes]:
    def go(page: Page) -> bytes:
        page.goto(f"{PANEL}/{path}")
        settle(page, selector)
        return screenshot(page)

    return go


def first_run(page: Page) -> bytes:
    panel("runs", "a.tile")(page)
    page.locator("a.tile").first.click()
    settle(page, "coinop-run-page")
    return screenshot(page)


def statement(page: Page) -> bytes:
    panel("runs", "a.tile")(page)
    for pick in page.locator("input.pick").all()[:STATEMENT_RUNS]:
        pick.check()
    page.locator("ha-button.statement").click()
    settle(page, "coinop-statement-dialog")
    with page.expect_download(timeout=60_000) as download:
        page.locator("ha-button.download").click()
    pdf = pdfium.PdfDocument(download.value.path())
    image = io.BytesIO()
    pdf[0].render(scale=PDF_SCALE).to_pil().save(image, "PNG")
    pdf.close()
    return image.getvalue()


def quick_start(page: Page) -> bytes:
    page.goto(f"{devenv.URL}/config/integrations/integration/coinop")
    page.get_by_role("button", name="Add Device").click()
    settle(page, "dialog-data-entry-flow")
    return screenshot(page)


# By Preset, so each is loaded once.
SHOTS: dict[str, dict[str, Callable[[Page], bytes]]] = {
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
                    (OUT / f"{name}.png").write_bytes(show(page))
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
