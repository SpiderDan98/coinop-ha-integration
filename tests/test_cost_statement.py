"""The Cost Statement: a PDF of selected ended Runs, downloaded through a signed path."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import shutil
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pypdf import PdfReader
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from .clock import CLOCK_START, Clock
from .devices import add_hub
from .http import HttpClient
from .images import colour, picture
from .stored import electricity, line_item, place_runs, stored_run
from .test_spoolman import set_options
from .websocket import PanelClient

DAY = timedelta(days=1)
BENCHY = CLOCK_START - 3 * DAY
HELMET = CLOCK_START - 2 * DAY
PLA = {
    "name": "PLA Black",
    "type": "PLA",
    "density": 1.24,
    "diameter": 1.75,
    "price_per_gram": 0.025,
}


@dataclass
class Statement:
    filename: str
    pages: list[str]
    #: The first page's width and height in mm.
    paper: tuple[int, int]
    pdf: bytes

    @property
    def lines(self) -> list[str]:
        return [line for page in self.pages for line in page.splitlines()]


def read(pdf: bytes) -> tuple[list[str], tuple[int, int]]:
    reader = PdfReader(BytesIO(pdf))
    box = reader.pages[0].mediabox
    return (
        [page.extract_text() for page in reader.pages],
        (round(box.width / 72 * 25.4), round(box.height / 72 * 25.4)),
    )


async def export(panel: PanelClient, browser: HttpClient, **options: Any) -> Statement:
    """Export the way the panel does: create it, then download the signed path."""
    result = await panel.call("wattbill/cost_statement/create", **options)
    status, headers, body = await browser.download(result["path"])
    assert status == 200, (status, body)
    assert headers["Content-Type"] == "application/pdf"
    disposition, filename = headers["Content-Disposition"].split("; filename=")
    assert disposition == "attachment"
    return Statement(filename.strip('"'), *read(body), body)


def pictures(pdf: bytes) -> list[tuple[int, str, tuple[int, int]]]:
    """Each image in the PDF: its page (from 0), colour and size in pixels."""
    found = []
    for number, page in enumerate(PdfReader(BytesIO(pdf)).pages):
        for image in page.images:
            assert image.image is not None
            found.append((number, colour(image.data), image.image.size))
    return found


async def upload(http: HttpClient, run_id: str, *photos: bytes) -> list[str]:
    status, body = await http.upload(f"/api/wattbill/runs/{run_id}/images", *photos)
    assert status == 200, body
    return [image["id"] for image in body["images"]]


@pytest.fixture
async def photographed(
    hass: HomeAssistant,
    files: Path,
    hass_storage: dict[str, Any],
    panel: PanelClient,
    http: HttpClient,
) -> None:
    """Benchy with a large red photo; Helmet with green and blue, blue picked as cover."""
    hass.config.currency = "EUR"
    place_runs(hass_storage, benchy(), helmet())
    await add_hub(hass)
    await upload(http, "benchy", picture("red", size=(4000, 3000)))
    _, blue = await upload(http, "helmet", picture("green"), picture("blue"))
    await panel.call("wattbill/images/set_cover", run_id="helmet", image_id=blue)


def benchy(started: datetime = BENCHY, **fields: Any) -> dict[str, Any]:
    return (
        stored_run(
            "benchy",
            name="Benchy",
            started=started,
            hours=2,
            part_count=2,
            line_items=[
                electricity(0.4, 0.25, started, started + timedelta(hours=2)),
                line_item(
                    "material",
                    0.505,
                    id="pla",
                    quantity=20.2,
                    unit="g",
                    unit_price=0.025,
                    material=PLA,
                ),
                line_item(
                    "other",
                    0.5,
                    id="wear",
                    label="Nozzle wear",
                    quantity=2,
                    unit="h",
                    unit_price=0.25,
                ),
            ],
        )
        | fields
    )


def helmet(**fields: Any) -> dict[str, Any]:
    return (
        stored_run(
            "helmet",
            name="Helmet",
            started=HELMET,
            hours=4.5,
            outcome="failed",
            line_items=[
                electricity(0.8, 0.25, HELMET, HELMET + timedelta(hours=4.5)),
                line_item("other", -1.0, id="refund", label="Refund"),
            ],
        )
        | fields
    )


@pytest.fixture
async def two_runs(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    hass.config.currency = "EUR"
    place_runs(hass_storage, benchy(), helmet())
    await add_hub(hass)


@pytest.mark.usefixtures("two_runs")
async def test_a_detailed_statement_shows_each_run_with_its_line_items_and_totals(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    statement = await export(panel, browser, run_ids=["helmet", "benchy"])

    assert statement.filename == "cost-statement-2026-01-15.pdf"
    assert statement.lines[:3] == [
        "Cost Statement",
        "Created Jan 15, 2026",
        "Period Jan 12, 2026 – Jan 13, 2026",  # noqa: RUF001
    ]
    text = "\n".join(statement.lines)
    for expected in [
        "Benchy",
        "Kobra · Jan 12, 2026 · Running time 2 h 0 min · 2 parts · €0.56 per part",
        "Line Item Quantity Unit price Amount",
        "Electricity 0.4 kWh €0.25 €0.10",
        "PLA Black 20.2 g €0.025 €0.51",
        "Nozzle wear 2 h €0.25 €0.50",
        "Run total €1.11",
        "Helmet",
        "Outcome: Failed",
        "Refund 1 pcs -€1.00 -€1.00",
        "Run total -€0.80",
        "Subtotal €0.31",
        "Total €0.31",
    ]:
        assert expected in text
    assert text.index("Benchy") < text.index("Helmet")
    assert "Completed" not in text


@pytest.mark.usefixtures("two_runs")
async def test_markup_is_its_own_line_and_never_in_the_runs(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    statement = await export(panel, browser, run_ids=["benchy", "helmet"], markup=12.5)

    text = "\n".join(statement.lines)
    assert "Run total €1.11" in text
    assert "Run total -€0.80" in text
    assert statement.lines[-4:-1] == [
        "Subtotal €0.31",
        "Markup 12.5% €0.04",
        "Total €0.35",
    ]


async def test_markup_applies_to_the_rounded_subtotal(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency = "EUR"
    started = CLOCK_START - DAY
    items = [
        electricity(0, 0.3, started, started + timedelta(hours=2)),
        line_item("other", 0.004, id="wear"),
    ]
    place_runs(
        hass_storage,
        *(stored_run(f"run-{n}", started=started, line_items=items) for n in range(3)),
    )
    await add_hub(hass)

    statement = await export(
        panel, browser, run_ids=["run-0", "run-1", "run-2"], markup=100
    )

    # Unrounded, 3 * 0.004 would make a subtotal of 0.01 and a Markup of 0.01.
    assert statement.lines[-4:-1] == [
        "Subtotal €0.00",
        "Markup 100% €0.00",
        "Total €0.00",
    ]


async def test_the_default_markup_is_a_hub_option(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency = "EUR"
    place_runs(hass_storage, benchy(), helmet())
    entry = await add_hub(hass)

    result = await set_options(hass, entry, markup=10)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert await panel.call("wattbill/cost_statement/defaults") == {"markup": 10}
    statement = await export(panel, browser, run_ids=["benchy", "helmet"])
    assert statement.lines[-4:-1] == [
        "Subtotal €0.31",
        "Markup 10% €0.03",
        "Total €0.34",
    ]


@pytest.mark.usefixtures("two_runs")
async def test_without_markup_there_is_no_markup_line(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    assert await panel.call("wattbill/cost_statement/defaults") == {"markup": 0}

    statement = await export(panel, browser, run_ids=["benchy", "helmet"], markup=0)

    assert statement.lines[-3:-1] == ["Subtotal €0.31", "Total €0.31"]


async def test_markup_cannot_be_negative(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, benchy())
    entry = await add_hub(hass)

    with pytest.raises(InvalidData):
        await set_options(hass, entry, markup=-5)
    error = await panel.error(
        "wattbill/cost_statement/create", run_ids=["benchy"], markup=-5
    )
    assert error["code"] == "invalid_format"


@pytest.mark.usefixtures("two_runs")
async def test_a_compact_statement_has_one_row_per_run(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    statement = await export(
        panel, browser, run_ids=["benchy", "helmet"], detail="compact"
    )

    assert statement.lines[3:-1] == [
        "Run Device Start Parts Per part Total",
        "Benchy Kobra Jan 12, 2026 2 €0.56 €1.11",
        "Helmet (Failed) Kobra Jan 13, 2026 1 -€0.80 -€0.80",
        "Subtotal €0.31",
        "Total €0.31",
    ]


@pytest.mark.usefixtures("two_runs")
async def test_title_and_note_head_the_statement_and_name_the_file(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    statement = await export(
        panel,
        browser,
        run_ids=["benchy"],
        title="Gifts for Ünal",
        note="Printed for the school fair.",
    )

    assert statement.filename == "gifts-for-unal-2026-01-15.pdf"
    assert statement.lines[:4] == [
        "Gifts for Ünal",
        "Created Jan 15, 2026",
        "Period Jan 12, 2026",
        "Printed for the school fair.",
    ]


async def test_a_german_statement_on_letter_paper_in_dollars(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency, hass.config.country = "USD", "US"
    place_runs(hass_storage, benchy(), helmet())
    await add_hub(hass)

    statement = await export(
        panel, browser, run_ids=["benchy", "helmet"], language="de", markup=7.5
    )

    assert statement.filename == "kostenaufstellung-2026-01-15.pdf"
    assert statement.paper == (216, 279)
    assert statement.lines[:3] == [
        "Kostenaufstellung",
        "Erstellt am 15.01.2026",
        "Zeitraum 12.01.2026 – 13.01.2026",  # noqa: RUF001
    ]
    text = "\n".join(statement.lines)
    for expected in [
        "Kobra · 12.01.2026 · Laufzeit 2 Std. 0 Min. · 2 Teile · 0,56 $ pro Teil",
        "Posten Menge Stückpreis Betrag",
        "Strom 0,4 kWh 0,25 $ 0,10 $",
        "PLA Black 20,2 g 0,025 $ 0,51 $",
        "Summe Lauf 1,11 $",
        "Ausgang: Fehlgeschlagen",
        "Zwischensumme 0,31 $",
        "Aufschlag 7,5 % 0,02 $",
        "Gesamtsumme 0,33 $",
    ]:
        assert expected in text
    assert statement.lines[-1] == (
        "Dies ist eine Kostenaufstellung, keine Rechnung. Seite 1 von 1"
    )


async def test_the_language_defaults_to_home_assistants_and_a4_outside_us_and_canada(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.language, hass.config.country = "de", "AT"
    place_runs(hass_storage, benchy())
    await add_hub(hass)

    statement = await export(panel, browser, run_ids=["benchy"])

    assert statement.lines[0] == "Kostenaufstellung"
    assert statement.paper == (210, 297)


async def test_internal_details_stay_off_the_statement(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency = "EUR"
    place_runs(
        hass_storage,
        benchy(
            note="Customer never paid the last one",
            tags=["Gift"],
            flags=["fault"],
            pauses=[
                {
                    "start": (BENCHY + timedelta(minutes=30)).isoformat(),
                    "end": (BENCHY + timedelta(minutes=50)).isoformat(),
                }
            ],
        ),
    )
    await add_hub(hass)
    run = await panel.call(
        "wattbill/line_items/update",
        run_id="benchy",
        line_item_id="electricity",
        amount=0.15,
    )
    assert run["run"]["line_items"][0]["computed"]["amount"] == 0.1

    statement = await export(panel, browser, run_ids=["benchy"])

    text = "\n".join(statement.lines)
    assert "Electricity 0.4 kWh €0.375 €0.15" in text
    assert "Running time 1 h 40 min" in text
    for internal in ["Customer", "Gift", "fault", "Fault", "0.10", "↺", "Pause"]:
        assert internal not in text


async def test_every_page_has_the_footer_and_sections_stay_together(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency = "EUR"
    place_runs(
        hass_storage,
        *(
            benchy(id=f"run-{n:02}", name=f"Print {n:02}", started=BENCHY + n * DAY)
            for n in range(20)
        ),
    )
    await add_hub(hass)

    statement = await export(panel, browser, run_ids=[f"run-{n:02}" for n in range(20)])

    count = len(statement.pages)
    assert count > 2
    assert [page.splitlines()[-1] for page in statement.pages] == [
        f"This is a cost statement, not an invoice. Page {n} of {count}"
        for n in range(1, count + 1)
    ]
    for n in range(20):
        [page] = [page for page in statement.pages if f"Print {n:02}" in page]
        section = page[page.index(f"Print {n:02}") :]
        assert "Run total €1.11" in section, f"Print {n:02} breaks across pages"


async def test_a_run_longer_than_a_page_breaks_with_its_table_headings_repeated(
    hass: HomeAssistant,
    clock: Clock,
    panel: PanelClient,
    browser: HttpClient,
    hass_storage: dict[str, Any],
) -> None:
    hass.config.currency = "EUR"
    items = [
        line_item("other", 0.25, id=f"part-{n}", label=f"Part {n:02}")
        for n in range(80)
    ]
    place_runs(
        hass_storage,
        benchy(),
        helmet(line_items=[*helmet()["line_items"], *items]),
    )
    await add_hub(hass)

    statement = await export(panel, browser, run_ids=["benchy", "helmet"])

    pages = statement.pages
    assert len(pages) == 3
    assert "Benchy" in pages[0]
    assert "Helmet" in pages[0]
    assert all("Line Item Quantity Unit price Amount" in page for page in pages[1:])
    assert "Run total €19.20" in pages[2]
    assert "Subtotal €20.31" in pages[2]


@pytest.mark.usefixtures("photographed")
async def test_a_detailed_statement_shows_each_runs_cover_image_downscaled(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    statement = await export(panel, browser, run_ids=["helmet", "benchy"])

    assert pictures(statement.pdf) == [(0, "red", (800, 600)), (0, "blue", (300, 200))]


@pytest.mark.usefixtures("photographed")
async def test_images_can_be_left_off_and_a_compact_statement_has_none(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    without = await export(panel, browser, run_ids=["benchy"], images=False)
    compact = await export(panel, browser, run_ids=["benchy"], detail="compact")

    assert pictures(without.pdf) == pictures(compact.pdf) == []


@pytest.mark.usefixtures("photographed")
async def test_a_cover_image_missing_on_disk_is_left_out(
    clock: Clock, files: Path, panel: PanelClient, browser: HttpClient
) -> None:
    shutil.rmtree(files / "images" / "benchy")

    statement = await export(panel, browser, run_ids=["benchy", "helmet"])

    assert pictures(statement.pdf) == [(0, "blue", (300, 200))]
    assert "Benchy" in statement.lines


@pytest.mark.usefixtures("two_runs")
async def test_the_pdf_shows_the_runs_as_they_are_at_download(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    result = await panel.call(
        "wattbill/cost_statement/create", run_ids=["benchy", "helmet"]
    )
    await panel.call("wattbill/runs/update", run_id="benchy", name="Benchy v2")
    await panel.call("wattbill/runs/delete", run_ids=["helmet"])

    status, _, body = await browser.download(result["path"])

    assert status == 200
    text = "\n".join(read(body)[0])
    assert "Benchy v2" in text
    assert "Helmet" not in text
    assert "Total €1.11" in text


async def test_only_ended_runs_can_be_exported(
    hass: HomeAssistant, clock: Clock, panel: PanelClient, hass_storage: dict[str, Any]
) -> None:
    place_runs(hass_storage, benchy(), stored_run("live", ended=False))
    await add_hub(hass)

    open_run = await panel.error(
        "wattbill/cost_statement/create", run_ids=["benchy", "live"]
    )
    missing = await panel.error(
        "wattbill/cost_statement/create", run_ids=["benchy", "gone"]
    )
    empty = await panel.error("wattbill/cost_statement/create", run_ids=[])

    assert [open_run["code"], missing["code"], empty["code"]] == [
        "not_allowed",
        "not_found",
        "invalid_format",
    ]


@pytest.mark.usefixtures("two_runs")
async def test_only_admins_export(
    clock: Clock,
    connect_panel: Callable[[MockUser], PanelClient],
    hass_read_only_user: MockUser,
    connect_http: Callable[[MockUser], HttpClient],
    panel: PanelClient,
) -> None:
    user = connect_panel(hass_read_only_user)
    error = await user.error("wattbill/cost_statement/create", run_ids=["benchy"])
    assert error["code"] == "unauthorized"

    result = await panel.call("wattbill/cost_statement/create", run_ids=["benchy"])
    status, _ = await connect_http(hass_read_only_user).get(result["path"])
    assert status == 401


@pytest.mark.usefixtures("two_runs")
async def test_the_download_needs_its_signature_and_expires(
    clock: Clock, panel: PanelClient, browser: HttpClient
) -> None:
    result = await panel.call("wattbill/cost_statement/create", run_ids=["benchy"])
    unsigned = result["path"].split("?")[0]

    assert (await browser.get(unsigned))[0] == 401
    await clock.advance(minutes=4)
    assert (await browser.get(result["path"]))[0] == 200
    await clock.advance(minutes=2)
    assert (await browser.get(result["path"]))[0] == 401
