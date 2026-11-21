"""The Cost Statement PDF, laid out with fpdf2 in Noto Sans.

It opens with the total and what it is made of, then lists the Runs.

Blocking (fonts, layout): run it in the executor, on copies of the Runs. Every
amount is rounded first and every sum adds rounded amounts, so each column adds
up; Markup applies to the rounded subtotal only.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from io import BytesIO
from pathlib import Path

from fpdf import FPDF, FontFace
from PIL import Image

from custom_components.coinop.cost.rounding import round_amount, rounded_sum
from custom_components.coinop.cost.running_time import running_time
from custom_components.coinop.images.encode import InvalidImage, jpeg
from custom_components.coinop.models import LineItem, LineItemKind, Outcome, Run
from custom_components.coinop.quantities import WATER

from .export import Detail, Options
from .text import Text

FONTS = Path(__file__).parent / "fonts"
FONT = "NotoSans"
LOGO = Path(__file__).parents[1] / "brand" / "icon.png"
BRAND = "Coin-op"
LETTER_COUNTRIES = ("US", "CA")
MARGIN = 22
# From the page's bottom edge to where the text ends, and to the footer line.
BOTTOM = 26
FOOTER = 17
INK = (28, 36, 34)
GREY = (104, 114, 111)
RULE = (224, 231, 229)
ACCENT = (14, 118, 104)
WHITE = (255, 255, 255)
# The panel's colours for the same kinds (frontend/src/styles.ts).
KIND_COLOURS = {
    LineItemKind.ELECTRICITY: (249, 168, 37),
    LineItemKind.WATER: (30, 136, 229),
    LineItemKind.MATERIAL: (38, 166, 154),
    LineItemKind.OTHER: (126, 87, 194),
}
MARKUP_COLOUR = (120, 134, 131)
BAR = 4.6
# The narrowest a legend entry gets before the legend wraps.
LEGEND_COLUMN = 40
# Pixels: sharp at the printed size (about 300 dpi), small in the file.
COVER_EDGE = 300
# The largest a Cover Image is printed, width and height in mm.
COVER_BOX = (24, 18)
COVER_RADIUS = 1.8
# What the Cover Images take of a section's width, when any Run has one.
COVER_COLUMN = 29
# The width kept for a Run's total beside its name.
AMOUNT = 34
# Less room than this and a section starts on the next page.
SECTION_START = 30
GAP = 2
HEADINGS = FontFace(color=GREY)
QUIET = FontFace(color=GREY, size_pt=8.5)
TOTAL_ROW = FontFace(emphasis="BOLD")


class _Document(FPDF):
    def __init__(self, text: Text, paper: str) -> None:
        super().__init__(format=paper, unit="mm")
        self.t = text
        self.add_font(FONT, "", FONTS / "NotoSans-Regular.ttf")
        self.add_font(FONT, "B", FONTS / "NotoSans-Bold.ttf")
        self.set_margins(MARGIN, MARGIN)
        self.set_auto_page_break(True, BOTTOM)
        self.c_margin = 0
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)

    def footers(self) -> None:
        """Every page's footer, drawn last: fpdf2's page count alias leaves a gap."""
        self.set_auto_page_break(False)
        self.style(8, colour=GREY)
        pages = self.pages_count
        for number in range(1, pages + 1):
            self.page = number
            self.set_y(-FOOTER)
            self.cell(self.epw / 2, 5, self.t("footer"))
            page = self.t("page", page=number, pages=pages)
            self.cell(self.epw / 2, 5, page, align="R")

    def style(
        self, size: float, style: str = "", colour: tuple[int, int, int] = INK
    ) -> None:
        self.set_font(FONT, style, size)
        self.set_text_color(*colour)

    def paragraph(self, text: str, height: float, width: float = 0) -> None:
        """Wrapped text from the current position, in the current style."""
        self.multi_cell(width, height, text, align="L", new_x="LEFT", new_y="NEXT")

    def dot(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        colour: tuple[int, int, int],
    ) -> None:
        """A filled box with round ends."""
        # A fill colour left set would fill every table cell after it.
        with self.local_context(fill_color=colour):
            self.rect(
                x,
                y,
                width,
                height,
                "F",
                round_corners=True,
                # fpdf2 misreads a radius of half the side or more.
                corner_radius=min(height, width) * 0.49,
            )

    def rule(self) -> None:
        self.line(self.l_margin, self.y, self.w - self.r_margin, self.y)

    def round_corners(self, x: float, y: float, width: float, height: float) -> None:
        """fpdf2 can't clip an image to a rounded box: a white frame covers its corners."""
        frame = COVER_RADIUS / 2
        with self.local_context(draw_color=WHITE, line_width=frame):
            self.rect(
                x - frame / 2,
                y - frame / 2,
                width + frame,
                height + frame,
                round_corners=True,
                corner_radius=COVER_RADIUS + frame / 2,
            )

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
        rows: Sequence[Sequence[str]],
        *,
        headings: Sequence[str] = (),
        styles: Mapping[int, FontFace] | None = None,
        total: Sequence[str] | None = None,
        width: float | None = None,
        ruled: bool = False,
    ) -> None:
        """A table at the right margin; `styles` are the rows' own by column."""
        self.style(9)
        last = len(widths) - 1
        space = 1.1 if ruled else 0.2
        with self.table(
            col_widths=widths,
            text_align=align,
            width=width,
            align="RIGHT",
            v_align="TOP",
            borders_layout="HORIZONTAL_LINES" if ruled else "NONE",
            headings_style=HEADINGS,
            first_row_as_headings=bool(headings),
            line_height=4.4,
        ) as table:
            for cells, row_style in [
                *([(headings, None)] if headings else []),
                *((row, None) for row in rows),
                *([(total, TOTAL_ROW)] if total else []),
            ]:
                row = table.row(style=row_style)
                for column, cell in enumerate(cells):
                    row.cell(
                        cell,
                        style=(styles or {}).get(column) if cells in rows else None,
                        padding=(space, 0 if column == last else GAP, space, 0),
                    )


def _total(run: Run, decimals: int) -> Decimal:
    return rounded_sum((item.amount for item in run.line_items), decimals)


def _per_part(run: Run, part_count: int, decimals: int) -> Decimal:
    return round_amount(float(_total(run, decimals)) / part_count, decimals)


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


def _unit_price(item: LineItem, text: Text) -> str:
    """Water is priced per m³, as the utility bills it."""
    if item.kind is LineItemKind.WATER and item.unit == WATER.unit:
        per_m3 = item.unit_price / WATER.per_unit(1.0)
        return f"{text.unit_price(per_m3)}/{WATER.price_unit}"
    return text.unit_price(item.unit_price)


def _quantity(item: LineItem, text: Text) -> str:
    if item.quantity is None:
        return ""
    return f"{text.quantity(item.quantity, item.unit)} × {_unit_price(item, text)}"  # noqa: RUF001


def _details(run: Run, now: datetime, text: Text) -> str:
    details = [
        run.device_name,
        text.date(run.started),
        *([text("program", program=run.program)] if run.program else []),
        text("running_time", duration=text.duration(running_time(run, now))),
    ]
    # One part costs what the Run costs.
    if (count := run.part_count) is not None and count > 1:
        amount = text.money(_per_part(run, count, text.decimals))
        details += [text("parts", count=count), text("per_part", amount=amount)]
    if outcome := _outcome(run, text):
        details.append(outcome)
    return " · ".join(details)


def _header(
    pdf: _Document, runs: list[Run], options: Options, now: datetime, total: Decimal
) -> None:
    text = pdf.t
    top = pdf.y
    pdf.image(LOGO, x=pdf.l_margin, y=top, w=9)
    pdf.set_xy(pdf.l_margin + 12, top + 2)
    pdf.style(10.5, "B", ACCENT)
    pdf.cell(pdf.epw / 2 - 12, 5, BRAND)
    pdf.style(8.5, colour=GREY)
    pdf.cell(pdf.epw / 2, 5, text("created", date=text.date(now)), align="R")
    pdf.set_y(top + 21)
    pdf.style(11, "B", ACCENT)
    pdf.paragraph(options.title or text("title"), 5.5)
    pdf.ln(1.5)
    pdf.style(36, "B")
    pdf.paragraph(text.money(total), 15)
    pdf.ln(1.5)
    start = text.date(runs[0].started)
    end = text.date(max(run.ended or run.started for run in runs))
    time = sum((running_time(run, now) for run in runs), timedelta())
    pdf.style(9.5, colour=GREY)
    pdf.paragraph(
        " · ".join(
            [
                text("run_one") if len(runs) == 1 else text("runs", count=len(runs)),
                start if start == end else text("period", start=start, end=end),
                text("running_time", duration=text.duration(time)),
            ]
        ),
        4.8,
    )
    if options.note:
        pdf.ln(3.5)
        pdf.style(10)
        pdf.paragraph(options.note, 5)
    pdf.ln(8)


def _breakdown(
    pdf: _Document, runs: list[Run], percent: float, markup: Decimal
) -> None:
    """What the total is made of: a bar and its legend, largest kind first.

    The bar is left out when an amount is negative, as no length shows that.
    """
    text = pdf.t
    kinds = sorted(
        (
            (kind, amount)
            for kind in LineItemKind
            if (
                amount := rounded_sum(
                    (
                        item.amount
                        for run in runs
                        for item in run.line_items
                        if item.kind is kind
                    ),
                    text.decimals,
                )
            )
        ),
        key=lambda share: -share[1],
    )
    shares = [
        *((text(f"kind.{kind}"), amount, KIND_COLOURS[kind]) for kind, amount in kinds),
        *(
            [(text("markup", percent=text.percent(percent)), markup, MARKUP_COLOUR)]
            if markup
            else []
        ),
    ]
    if len(shares) < 2:
        return
    total = sum((amount for _, amount, _ in shares), Decimal(0))
    proportional = all(amount > 0 for _, amount, _ in shares)
    if proportional:
        x = pdf.l_margin
        length = pdf.epw - 0.7 * (len(shares) - 1)
        for _, amount, colour in shares:
            width = length * float(amount / total)
            pdf.dot(x, pdf.y, width, BAR, colour)
            x += width + 0.7
        pdf.ln(BAR + 4.5)
    columns = int(pdf.epw // LEGEND_COLUMN)
    top = pdf.y
    for index, (label, amount, colour) in enumerate(shares):
        x = pdf.l_margin + index % columns * pdf.epw / columns
        y = top + index // columns * 14
        pdf.dot(x, y + 1.1, 2.6, 2.6, colour)
        pdf.set_xy(x + 4.2, y)
        pdf.style(9, colour=GREY)
        pdf.cell(text=label, h=4.8)
        pdf.set_xy(x + 4.2, y + 5.2)
        pdf.style(10.5, "B")
        pdf.cell(text=text.money(amount), h=5.4)
        if proportional and index < len(kinds):
            share = text.number(float(amount / total) * 100, 0)
            pdf.set_xy(pdf.x + 1.8, y + 5.5)
            pdf.style(8.5, colour=GREY)
            pdf.cell(text=text("share", percent=share), h=5.4)
    pdf.set_y(top + (len(shares) + columns - 1) // columns * 14 + 2)


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
    indent: float,
) -> None:
    """`indent`: how far its text starts from the margin, past the Cover Images."""
    text = pdf.t
    if pdf.will_page_break(SECTION_START):
        pdf.add_page()
    pdf.rule()
    pdf.ln(5.5)
    top, page, left = pdf.y, pdf.page, pdf.l_margin + indent
    if cover:
        data, width, height = cover
        pdf.image(BytesIO(data), x=pdf.l_margin, y=top, w=width, h=height)
        pdf.round_corners(pdf.l_margin, top, width, height)
    pdf.set_xy(left, top)
    pdf.style(11, "B")
    pdf.paragraph(_name(run, text), 5.5, pdf.epw - indent - AMOUNT)
    below = pdf.y
    pdf.set_xy(pdf.w - pdf.r_margin - AMOUNT, top)
    pdf.cell(AMOUNT, 5.5, text.money(_total(run, text.decimals)), align="R")
    pdf.set_xy(left, below)
    pdf.style(8.5, colour=GREY)
    pdf.paragraph(_details(run, now, text), 4.4, pdf.epw - indent)
    pdf.ln(1.8)
    if run.line_items:
        pdf.rows(
            (9, 7, 4),
            ("LEFT", "LEFT", "RIGHT"),
            [
                (
                    _label(item, text),
                    _quantity(item, text),
                    text.money(round_amount(item.amount, text.decimals)),
                )
                for item in run.line_items
            ],
            styles={1: QUIET},
            width=pdf.epw - indent,
        )
    if cover and pdf.page == page:
        pdf.set_y(max(pdf.y, top + cover[2]))
    pdf.ln(5)


def _compact(pdf: _Document, runs: list[Run]) -> None:
    text, decimals = pdf.t, pdf.t.decimals

    def name(run: Run) -> str:
        if outcome := _outcome(run, text):
            return text("with_outcome", name=_name(run, text), outcome=outcome)
        return _name(run, text)

    def parts(run: Run) -> tuple[str, str]:
        if (count := run.part_count) is None:
            return "", ""
        return str(count), text.money(_per_part(run, count, decimals))

    # Without any Run that has a Program or Part Count, its columns are left out.
    with_programs = any(run.program for run in runs)
    with_parts = any(run.part_count is not None for run in runs)
    programs = ("program",) if with_programs else ()
    columns = ("part_count", "cost_per_part") if with_parts else ()
    pdf.rows(
        (
            32,
            20,
            *((18,) if with_programs else ()),
            16,
            *((8, 12) if with_parts else ()),
            12,
        ),
        (
            "LEFT",
            "LEFT",
            *(("LEFT",) * len(programs)),
            "LEFT",
            *(("RIGHT",) * len(columns)),
            "RIGHT",
        ),
        [
            (
                name(run),
                run.device_name,
                *((run.program or "",) if with_programs else ()),
                text.date(run.started),
                *(parts(run) if with_parts else ()),
                text.money(_total(run, decimals)),
            )
            for run in runs
        ],
        headings=[
            text(f"column.{column}")
            for column in ("run", "device", *programs, "started", *columns, "total")
        ],
        ruled=True,
    )


def _totals(pdf: _Document, subtotal: Decimal, percent: float, markup: Decimal) -> None:
    """How the Runs' amounts and the Markup make the total."""
    text = pdf.t
    pdf.ln(6)
    pdf.rows(
        (1, 1),
        ("LEFT", "RIGHT"),
        [
            (text("subtotal"), text.money(subtotal)),
            (text("markup", percent=text.percent(percent)), text.money(markup)),
        ],
        total=(text("total"), text.money(subtotal + markup)),
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
    subtotal = sum((_total(run, text.decimals) for run in runs), Decimal(0))
    markup = (subtotal * Decimal(repr(options.markup)) / 100).quantize(
        Decimal(1).scaleb(-text.decimals), ROUND_HALF_UP
    )
    _header(pdf, runs, options, now, subtotal + markup)
    _breakdown(pdf, runs, options.markup, markup)
    pdf.ln(5)
    if options.detail is Detail.COMPACT:
        _compact(pdf, runs)
    else:
        printed = {
            run.id: cover
            for run in runs
            if run.id in covers and (cover := _cover(covers[run.id]))
        }
        indent = COVER_COLUMN if printed else 0
        for run in runs:
            pdf.keep_together(
                partial(_section, pdf, run, now, printed.get(run.id), indent)
            )
        pdf.rule()
    if options.markup:
        pdf.keep_together(partial(_totals, pdf, subtotal, options.markup, markup))
    pdf.footers()
    return bytes(pdf.output())
