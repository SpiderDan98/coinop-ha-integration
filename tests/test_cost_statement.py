"""The Cost Statement: a PDF of selected ended Runs, downloaded through a signed path."""

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import Any

from homeassistant.core import HomeAssistant
from pypdf import PdfReader
import pytest

from .clock import CLOCK_START, Clock
from .devices import add_hub
from .http import HttpClient
from .stored import electricity, line_item, place_runs, stored_run
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
    return Statement(filename.strip('"'), *read(body))


def benchy(**fields: Any) -> dict[str, Any]:
    return (
        stored_run(
            "benchy",
            name="Benchy",
            started=BENCHY,
            hours=2,
            part_count=2,
            line_items=[
                electricity(0.4, 0.25, BENCHY, BENCHY + timedelta(hours=2)),
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
