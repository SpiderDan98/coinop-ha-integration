"""The Cost Statement PDF, laid out with fpdf2 in Noto Sans.

Blocking (fonts, layout): run it in the executor, on copies of the Runs. Every
amount is rounded first and every sum adds rounded amounts, so each column adds
up; Markup applies to the rounded subtotal only.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from io import BytesIO
from pathlib import Path

from fpdf import FPDF, FontFace
from PIL import Image

from custom_components.coinop.cost.rounding import round_amount, rounded_sum
from custom_components.coinop.cost.running_time import running_time
from custom_components.coinop.images.encode import InvalidImage, jpeg
from custom_components.coinop.models import LineItem, Outcome, Run

from .export import Detail, Options
from .text import Text

FONTS = Path(__file__).parent / "fonts"
FONT = "NotoSans"
LETTER_COUNTRIES = ("US", "CA")
MARGIN = 18
FOOTER = 14
GREY = (110, 110, 110)
RULE = (200, 200, 200)
HEADINGS = FontFace(emphasis="BOLD", fill_color=(242, 242, 242))
TOTAL_ROW = FontFace(emphasis="BOLD")
# Pixels: sharp at the printed size (about 300 dpi), small in the file.
COVER_EDGE = 800
# The largest a Cover Image is printed, width and height in mm.
COVER_BOX = (64, 48)


class _Document(FPDF):
    def __init__(self, text: Text, paper: str) -> None:
        super().__init__(format=paper, unit="mm")
        self.t = text
        self.add_font(FONT, "", FONTS / "NotoSans-Regular.ttf")
        self.add_font(FONT, "B", FONTS / "NotoSans-Bold.ttf")
        self.alias_nb_pages(align="R")
        self.set_margins(MARGIN, MARGIN)
        self.set_auto_page_break(True, MARGIN + FOOTER)
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)

    def footer(self) -> None:
        self.set_y(-MARGIN - 4)
        self.set_font(FONT, "", 8)
        self.set_text_color(*GREY)
        self.cell(self.epw / 2, 5, self.t("footer"))
        page = self.t("page", page=self.page_no(), pages=self.str_alias_nb_pages)
        self.cell(self.epw / 2, 5, page, align="R")
        self.set_text_color(0)

    def line_of_text(
        self, text: str, size: float, style: str = "", grey: bool = False
    ) -> None:
        self.set_font(FONT, style, size)
        self.set_text_color(*(GREY if grey else (0, 0, 0)))
        self.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)

    def keep_together(self, draw: Callable[[], None]) -> None:
        """On one page unless it is longer than a page; then it breaks."""
        top, page = self.y, self.page
        with self.offset_rendering() as trial:
            draw()
            height = trial.y - top + (trial.page - page) * self.eph
        if top + height > self.page_break_trigger >= self.t_margin + height:
            self.add_page()
        draw()

    def rows(
        self,
        widths: Sequence[float],
        align: Sequence[str],
        headings: Sequence[str],
        rows: Sequence[Sequence[str]],
        total: Sequence[str] | None = None,
        width: float | None = None,
    ) -> None:
        self.set_font(FONT, "", 9)
        with self.table(
            col_widths=widths,
            text_align=align,
            width=width,
            align="RIGHT",
            borders_layout="HORIZONTAL_LINES",
            headings_style=HEADINGS,
            first_row_as_headings=bool(headings),
            line_height=5,
            padding=(1, 1.5),
        ) as table:
            for row in [headings, *rows] if headings else rows:
                table.row(row)
            if total:
                table.row(total, style=TOTAL_ROW)


def _total(run: Run, decimals: int) -> Decimal:
    return rounded_sum((item.amount for item in run.line_items), decimals)


def _per_part(run: Run, decimals: int) -> Decimal:
    return round_amount(float(_total(run, decimals)) / run.part_count, decimals)


def _name(run: Run, text: Text) -> str:
    return run.name or text("untitled")


def _outcome(run: Run, text: Text) -> str | None:
    """Only an Outcome other than Completed is worth printing."""
    outcome = run.outcome or Outcome.UNKNOWN
    return None if outcome is Outcome.COMPLETED else text(f"outcome_name.{outcome}")


def _label(item: LineItem, text: Text) -> str:
    if item.label:
        return item.label
    if item.material is not None:
        return item.material.name
    return text(f"kind.{item.kind}")


def _parts(count: int, text: Text) -> str:
    return text("part_one") if count == 1 else text("parts", count=count)


def _header(pdf: _Document, runs: list[Run], options: Options, now: datetime) -> None:
    text = pdf.t
    pdf.line_of_text(options.title or text("title"), 18, "B")
    pdf.ln(1)
    pdf.line_of_text(text("created", date=text.date(now)), 9, grey=True)
    start = text.date(runs[0].started)
    end = text.date(max(run.ended or run.started for run in runs))
    period = (
        text("period_day", day=start)
        if start == end
        else text("period", start=start, end=end)
    )
    pdf.line_of_text(period, 9, grey=True)
    if options.note:
        pdf.ln(3)
        pdf.line_of_text(options.note, 10)
    pdf.ln(6)


def _cover(path: Path) -> tuple[bytes, float, float] | None:
    """The JPEG to print and its printed width and height; None without a readable file."""
    try:
        data = jpeg(path.read_bytes(), COVER_EDGE)
    except OSError, InvalidImage:
        return None
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
    scale = min(COVER_BOX[0] / width, COVER_BOX[1] / height)
    return data, width * scale, height * scale


def _section(
    pdf: _Document,
    run: Run,
    now: datetime,
    cover: tuple[bytes, float, float] | None,
) -> None:
    text, decimals = pdf.t, pdf.t.decimals
    pdf.line_of_text(_name(run, text), 12, "B")
    details = [
        run.device_name,
        text.date(run.started),
        text("running_time", duration=text.duration(running_time(run, now))),
        _parts(run.part_count, text),
        text("per_part", amount=text.money(_per_part(run, decimals))),
    ]
    pdf.line_of_text(" · ".join(details), 9, grey=True)
    if outcome := _outcome(run, text):
        pdf.line_of_text(text("outcome", outcome=outcome), 9, grey=True)
    pdf.ln(1.5)
    if cover:
        data, width, height = cover
        pdf.image(BytesIO(data), w=width, h=height)
        pdf.ln(2)
    pdf.rows(
        (46, 18, 18, 18),
        ("LEFT", "RIGHT", "RIGHT", "RIGHT"),
        [
            text(f"column.{column}")
            for column in ("line_item", "quantity", "unit_price", "amount")
        ],
        [
            (
                _label(item, text),
                ""
                if item.quantity is None
                else text.quantity(item.quantity, item.unit),
                text.unit_price(item.unit_price),
                text.money(round_amount(item.amount, decimals)),
            )
            for item in run.line_items
        ],
        total=(text("run_total"), "", "", text.money(_total(run, decimals))),
    )
    pdf.ln(7)


def _compact(pdf: _Document, runs: list[Run]) -> None:
    text, decimals = pdf.t, pdf.t.decimals

    def name(run: Run) -> str:
        if outcome := _outcome(run, text):
            return text("with_outcome", name=_name(run, text), outcome=outcome)
        return _name(run, text)

    pdf.rows(
        (32, 20, 16, 8, 12, 12),
        ("LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        [
            text(f"column.{column}")
            for column in (
                "run",
                "device",
                "started",
                "part_count",
                "cost_per_part",
                "total",
            )
        ],
        [
            (
                name(run),
                run.device_name,
                text.date(run.started),
                str(run.part_count),
                text.money(_per_part(run, decimals)),
                text.money(_total(run, decimals)),
            )
            for run in runs
        ],
    )
    pdf.ln(7)


def _totals(pdf: _Document, runs: list[Run], markup: float) -> None:
    text, decimals = pdf.t, pdf.t.decimals
    subtotal = sum((_total(run, decimals) for run in runs), Decimal(0))
    amount = (subtotal * Decimal(repr(markup)) / 100).quantize(
        Decimal(1).scaleb(-decimals), ROUND_HALF_UP
    )
    rows = [(text("subtotal"), text.money(subtotal))]
    if markup:
        rows.append((text("markup", percent=text.percent(markup)), text.money(amount)))
    pdf.rows(
        (1, 1),
        ("LEFT", "RIGHT"),
        [],
        rows,
        total=(text("total"), text.money(subtotal + amount)),
        width=80,
    )


def render(
    runs: list[Run],
    options: Options,
    *,
    covers: Mapping[str, Path],
    now: datetime,
    currency: str,
    country: str | None,
    time_zone: tzinfo,
) -> bytes:
    """`runs`: the final Runs, ordered by start; `covers`: Cover Image files by Run id."""
    text = Text(options.language, currency, time_zone)
    pdf = _Document(text, "Letter" if country in LETTER_COUNTRIES else "A4")
    pdf.set_title(options.title or text("title"))
    pdf.add_page()
    _header(pdf, runs, options, now)
    if options.detail is Detail.COMPACT:
        _compact(pdf, runs)
    else:
        for run in runs:
            cover = _cover(covers[run.id]) if run.id in covers else None
            pdf.keep_together(partial(_section, pdf, run, now, cover))
    pdf.keep_together(partial(_totals, pdf, runs, options.markup))
    return bytes(pdf.output())
