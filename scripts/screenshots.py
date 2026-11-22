"""The README's screenshots and demo GIF, taken in the dev container with its Presets.

Usage: uv run scripts/screenshots.py [name ...]

Starts the dev container if it isn't running (and stops it again afterwards), loads
each Preset a screenshot needs and saves the screenshots, in the dark theme at a
fixed size, to docs/images/screenshots. The statement image is instead the first
page of the Cost Statement PDF the panel downloads, fitted whole into the same
size. The demo GIF records a wash run live through the washing machine's helpers,
corrected afterwards, then a 3D print. Names limit it to those screenshots. Drives
the installed Google Chrome, so Playwright needs no browser of its own.
"""

from collections.abc import Callable
import io
import subprocess
import sys

import devenv
from PIL import Image, ImageDraw
from playwright.sync_api import Locator, Page, sync_playwright
import pypdfium2 as pdfium

OUT = devenv.ROOT / "docs" / "images" / "screenshots"
PANEL = f"{devenv.URL}/coinop"
# The dev container's Scenario button isn't part of Coin-op.
STYLE = "ha-icon-button.dev { display: none !important; }"
# Lit renders a moment after the data arrives; a click before then misses its target.
SETTLE_MS = 2500
# The newest Runs, few enough to fit the Cost Statement on one page.
STATEMENT_RUNS = 4
WIDTH, HEIGHT = 1280, 800
DEVICE_SCALE = 1.5
SIZE = (int(WIDTH * DEVICE_SCALE), int(HEIGHT * DEVICE_SCALE))
# Room around the PDF page, in pixels, on HA's dark background.
PDF_MARGIN = 48
PDF_BACKGROUND = "#111111"
# The demo's Scenario: a printer's history next to the washing machine it runs live.
DEMO = {"pieces": ["prusa", "bambu", "washer"], "history": "long"}
# Tall enough to show a wash Run's Total.
DEMO_SIZE = (WIDTH, 940)
# Long enough for a helper's change to reach the panel and render.
UPDATE_MS = 900
# A Cotton 60° load (its Program Defaults), metered in steps.
WASH_STEPS = 4
WASH_KWH, WASH_LITRES, DETERGENT_GRAMS = 1.1, 56.0, 75.0
# The pointer glides to what it clicks at 25 frames a second, then shows the press.
MOVE_FRAMES, MOVE_MS, PRESS_MS = 12, 40, 200


def settle(page: Page, selector: str) -> None:
    page.wait_for_selector(selector, state="attached", timeout=60_000)
    page.wait_for_timeout(SETTLE_MS)


def screenshot(page: Page) -> bytes:
    return page.screenshot(style=STYLE, animations="disabled")


def show(page: Page, path: str, selector: str) -> None:
    page.goto(f"{PANEL}/{path}")
    settle(page, selector)


def panel(path: str, selector: str) -> Callable[[Page], bytes]:
    def go(page: Page) -> bytes:
        show(page, path, selector)
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
    width, height = pdf[0].get_size()
    scale = min((SIZE[0] - 2 * PDF_MARGIN) / width, (SIZE[1] - 2 * PDF_MARGIN) / height)
    page_image = pdf[0].render(scale=scale).to_pil()
    pdf.close()
    canvas = Image.new("RGB", SIZE, PDF_BACKGROUND)
    canvas.paste(
        page_image,
        ((SIZE[0] - page_image.width) // 2, (SIZE[1] - page_image.height) // 2),
    )
    image = io.BytesIO()
    canvas.save(image, "PNG")
    return image.getvalue()


def quick_start(page: Page) -> bytes:
    page.goto(f"{devenv.URL}/config/integrations/integration/coinop")
    page.get_by_role("button", name="Add Device").click()
    settle(page, "dialog-data-entry-flow")
    return screenshot(page)


def helper(entity_id: str, value: str | float | None = None) -> str:
    """Sets the helper to `value` as its integration would, and answers its state."""
    access = devenv.access_token()
    if value is not None:
        domain = entity_id.split(".")[0]
        service, field = (
            ("select_option", "option")
            if domain == "input_select"
            else ("set_value", "value")
        )
        devenv.request(
            "POST",
            f"/api/services/{domain}/{service}",
            {"entity_id": entity_id, field: value},
            access,
        )
    state: str = devenv.request("GET", f"/api/states/{entity_id}", None, access)[
        "state"
    ]
    return state


def report(entity_id: str) -> None:
    """Reports the helper's state again, as a meter does on its interval."""
    access = devenv.access_token()
    state = devenv.request("GET", f"/api/states/{entity_id}", None, access)
    devenv.request(
        "POST",
        f"/api/states/{entity_id}",
        {
            "state": state["state"],
            "attributes": state["attributes"],
            "force_update": True,
        },
        access,
    )


def demo(page: Page) -> bytes:
    # Each frame: the page, how long it shows, where the pointer is and if it presses.
    frames: list[tuple[Image.Image, int, tuple[float, float], bool]] = []
    pointer = (0.0, 0.0)

    def hold(ms: int, wait_ms: int = UPDATE_MS) -> None:
        page.wait_for_timeout(wait_ms)
        frames.append((Image.open(io.BytesIO(screenshot(page))), ms, pointer, False))

    def click(target: Locator) -> None:
        """Glides the pointer onto `target` over the page as it is, then clicks it."""
        nonlocal pointer
        box = target.bounding_box()
        assert box, target
        image = Image.open(io.BytesIO(screenshot(page)))
        start = pointer
        end = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        for step in range(1, MOVE_FRAMES + 1):
            done = step / MOVE_FRAMES
            eased = done * done * (3 - 2 * done)
            pointer = (
                start[0] + (end[0] - start[0]) * eased,
                start[1] + (end[1] - start[1]) * eased,
            )
            frames.append((image, MOVE_MS, pointer, False))
        frames.append((image, PRESS_MS, pointer, True))
        target.click()

    meters = {
        f"input_number.{key}": float(helper(f"input_number.{key}"))
        for key in ("washer_energy", "washer_water", "detergent_scale")
    }
    page.set_viewport_size({"width": DEMO_SIZE[0], "height": DEMO_SIZE[1]})

    def meter(entity_id: str, by: float) -> None:
        meters[entity_id] = round(meters[entity_id] + by, 3)
        helper(entity_id, meters[entity_id])

    def tab(name: str) -> Locator:
        return page.locator(f"a.tab[title='{name}']")

    energy, water, scale = meters
    show(page, "", "coinop-overview")
    # Where the last click leaves it, so the loop starts as it ends.
    box = tab("Overview").bounding_box()
    assert box
    pointer = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    hold(2000, 0)
    # A meter's reading long before the start would spread its next step over the
    # time in between, most of it before the Run.
    for entity_id in meters:
        report(entity_id)
    helper("input_select.washer_program", "Cotton 60°")
    helper("input_select.washer_status", "running")
    page.locator("a.live").wait_for()
    hold(900)
    meter(scale, -DETERGENT_GRAMS)
    hold(700)
    for _ in range(WASH_STEPS):
        meter(energy, WASH_KWH / WASH_STEPS)
        meter(water, WASH_LITRES / WASH_STEPS)
        hold(600)
    click(page.locator("a.live"))
    settle(page, "coinop-run-page")
    hold(1400, 0)
    helper("input_select.washer_status", "finished")
    # A report after the end makes the Run final, and editable, without the wait.
    for entity_id in meters:
        report(entity_id)
    page.locator(".item ha-icon-button.edit").first.wait_for()
    hold(1200)
    click(
        page.locator(".item", has_text="Fabric softener").locator("ha-icon-button.edit")
    )
    quantity = page.locator("coinop-dialog input[name=quantity]")
    hold(500, 400)
    click(quantity)
    quantity.select_text()
    for typed in ("4", "45"):
        quantity.fill(typed)
        hold(250, 150)
    hold(500, 0)
    click(page.locator("coinop-dialog ha-button.save"))
    hold(1800)
    click(tab("Runs"))
    settle(page, "a.tile")
    hold(800, 0)
    click(page.locator("a.tile", has_text="Prusa MK4").first)
    settle(page, "coinop-run-page")
    hold(2400, 0)
    click(tab("Overview"))
    settle(page, "coinop-overview")
    hold(1600, 0)
    page.set_viewport_size({"width": WIDTH, "height": HEIGHT})
    return gif(frames)


def sprite(draw: Callable[[ImageDraw.ImageDraw], None], size: int) -> Image.Image:
    """Drawn 4 times as large and scaled down, as PIL draws without antialiasing."""
    image = Image.new("RGBA", (size * 4, size * 4))
    draw(ImageDraw.Draw(image))
    return image.resize((size, size), Image.Resampling.LANCZOS)


# A pointer's arrow, its tip at (POINTER_TIP, POINTER_TIP).
POINTER_TIP = 2
POINTER = sprite(
    lambda draw: draw.polygon(
        [
            ((x * 1.4 + POINTER_TIP) * 4, (y * 1.4 + POINTER_TIP) * 4)
            for x, y in [
                (0, 0),
                (0, 17),
                (4.5, 13),
                (7.5, 19.5),
                (10, 18.5),
                (7, 12),
                (12.5, 12),
            ]
        ],
        fill="white",
        outline="black",
        width=6,
    ),
    32,
)
PRESS_RADIUS = 16
PRESS = sprite(
    lambda draw: draw.ellipse(
        (4, 4, PRESS_RADIUS * 8 - 4, PRESS_RADIUS * 8 - 4),
        fill=(255, 255, 255, 70),
        outline=(255, 255, 255, 170),
        width=8,
    ),
    PRESS_RADIUS * 2,
)


def gif(frames: list[tuple[Image.Image, int, tuple[float, float], bool]]) -> bytes:
    """One palette for every frame, undithered, so a frame stores only what changed."""
    images = []
    for image, _, (x, y), pressed in frames:
        frame = image.convert("RGBA").resize(DEMO_SIZE, Image.Resampling.LANCZOS)
        if pressed:
            frame.alpha_composite(
                PRESS, (round(x) - PRESS_RADIUS, round(y) - PRESS_RADIUS)
            )
        frame.alpha_composite(POINTER, (round(x) - POINTER_TIP, round(y) - POINTER_TIP))
        images.append(frame.convert("RGB"))
    collage = Image.new("RGB", (DEMO_SIZE[0], DEMO_SIZE[1] * len(images)))
    for index, image in enumerate(images):
        collage.paste(image, (0, DEMO_SIZE[1] * index))
    # Median cut greys the few purple pixels of the Other kind and of a corrected item.
    palette = collage.quantize(256, method=Image.Quantize.FASTOCTREE)
    indexed = [
        image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images
    ]
    out = io.BytesIO()
    indexed[0].save(
        out,
        "GIF",
        save_all=True,
        append_images=indexed[1:],
        duration=[ms for _, ms, _, _ in frames],
        loop=0,
    )
    return out.getvalue()


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
# Each by the Scenario it loads.
GIFS = {"demo": (DEMO, demo)}


def main() -> None:
    wanted = set(sys.argv[1:])
    unknown = wanted - {name for shots in SHOTS.values() for name in shots} - set(GIFS)
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
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=DEVICE_SCALE,
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
                for name, take in shots.items():
                    (OUT / f"{name}.png").write_bytes(take(page))
                    print(f"Saved {name}.png", flush=True)
            for name, (scenario, record) in GIFS.items():
                if wanted and name not in wanted:
                    continue
                devenv.load(scenario)
                (OUT / f"{name}.gif").write_bytes(record(page))
                print(f"Saved {name}.gif", flush=True)
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
