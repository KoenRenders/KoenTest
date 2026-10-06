"""The poster's date line shows the end too (#1677).

Koen, 6 October 2026: the poster of a weekend printed "VRIJDAG 7 MEI" though
the activity runs from Friday to Sunday. The wording per combination is his,
confirmed on the issue; every row of his table stands here with its exact line.

Broken on purpose (7 October 2026): the end date ignored → the two-day rows;
the month kept on the first day of a same-month range → "VRIJDAG 7 MEI TOT …";
the year left off → the two-years row; "VAN … TOT" replaced by "OM" → the
from-and-to row.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.domains.designstudio.blocks import _date_lines
from app.domains.designstudio.service import date_row_line

FRI, SUN = date(2027, 5, 7), date(2027, 5, 9)


@pytest.mark.parametrize(
    ("row", "line"),
    [
        ((FRI, None, None, None), "VRIJDAG 7 MEI"),
        ((FRI, None, time(14), None), "VRIJDAG 7 MEI OM 14U"),
        ((FRI, None, time(14), time(17)), "VRIJDAG 7 MEI VAN 14U TOT 17U"),
        ((FRI, SUN, None, None), "VRIJDAG 7 TOT ZONDAG 9 MEI"),
        ((date(2027, 4, 30), date(2027, 5, 2), None, None), "VRIJDAG 30 APRIL TOT ZONDAG 2 MEI"),
        ((FRI, SUN, time(18), time(16)), "VRIJDAG 7 MEI 18U TOT ZONDAG 9 MEI 16U"),
        ((FRI, SUN, time(18), None), "VRIJDAG 7 MEI 18U TOT ZONDAG 9 MEI"),
        ((FRI, SUN, None, time(16)), "VRIJDAG 7 MEI TOT ZONDAG 9 MEI 16U"),
        # an end date equal to the start date is one day
        ((FRI, FRI, None, None), "VRIJDAG 7 MEI"),
        ((FRI, FRI, time(14), time(17)), "VRIJDAG 7 MEI VAN 14U TOT 17U"),
        (
            (date(2027, 12, 31), date(2028, 1, 1), None, None),
            "VRIJDAG 31 DECEMBER 2027 TOT ZATERDAG 1 JANUARI 2028",
        ),
        # minutes as before
        ((FRI, None, time(14, 30), None), "VRIJDAG 7 MEI OM 14U30"),
        ((FRI, SUN, time(18, 15), time(16, 45)), "VRIJDAG 7 MEI 18U15 TOT ZONDAG 9 MEI 16U45"),
    ],
)
def test_the_line_of_one_date_row(row, line):
    assert date_row_line(*row) == line


@pytest.mark.parametrize(
    ("row", "cell"),
    [
        ((FRI, None, time(14), time(17)), "7 MEI"),
        ((FRI, SUN, time(18), time(16)), "7 TOT 9 MEI"),
        ((date(2027, 4, 30), date(2027, 5, 2), None, None), "30 APRIL TOT 2 MEI"),
    ],
)
def test_a_cell_of_the_dates_grid_shows_the_end_without_weekday_or_hours(row, cell):
    """Twelve dates in two narrow columns: the same function, short."""
    assert date_row_line(*row, weekday=False, hours=False) == cell


@pytest.mark.parametrize(
    ("line", "lines"),
    [
        # two days: after TOT
        ("VRIJDAG 7 MEI 18U TOT ZONDAG 9 MEI 16U", ["VRIJDAG 7 MEI 18U TOT", "ZONDAG 9 MEI 16U"]),
        ("VRIJDAG 7 TOT ZONDAG 9 MEI", ["VRIJDAG 7 TOT", "ZONDAG 9 MEI"]),
        # one day with a from and a to: before VAN
        ("VRIJDAG 7 MEI VAN 14U TOT 17U", ["VRIJDAG 7 MEI", "VAN 14U TOT 17U"]),
    ],
)
def test_a_date_line_breaks_where_it_reads(line, lines):
    """The block's own width and size on the simple layout: 95 mm at 8 mm."""
    assert _date_lines(line, 95.0, 8.0) == lines


@pytest.mark.parametrize(
    "line",
    [
        "DONDERDAG 31 DECEMBER 2027 TOT ZATERDAG 1 JANUARI 2028",
        "WOENSDAG 30 SEPTEMBER 18U30 TOT WOENSDAG 7 OKTOBER 16U30",
        "VRIJDAG 7 MEI OM 14U",
    ],
)
def test_a_line_wider_than_the_block_runs_on_and_loses_no_word(line):
    """Three or four lines, nothing cut, nothing made smaller; the break after
    TOT still stands."""
    lines = _date_lines(line, 95.0, 8.0)
    assert " ".join(lines) == line, "a word was lost or moved"
    assert len(lines) <= 4
    if " TOT " in line:
        assert any(part.endswith(" TOT") for part in lines), lines


def _rendered(line: str, layout: str = "print_a"):
    import re

    from app.domains.designstudio import render
    from app.domains.designstudio.content import Highlight, PosterContent

    merged = render.merge(
        PosterContent(
            duo_code="dark_green-golden_yellow",
            preset="eenvoudig",
            title_lines=("FIETSWEEKEND",),
            date_line=line,
            location="DORPSPLEIN",
            highlights=(Highlight("calendar", line, True), Highlight("map-pin", "DORPSPLEIN")),
            explanation_md="Een korte tekst.",
        ),
        layout=layout,
    )
    rows = re.findall(r'<text id="t-hl-0-\d"[^>]*>([^<]*)<', merged.svg)
    text_y = float(
        re.search(r'<text id="t-rt-explanation"[^>]* y="([0-9.]+)"', merged.svg).group(1)
    )
    return merged, rows, text_y


@pytest.mark.parametrize("layout", ["print_a", "feed_portrait"])
def test_on_the_poster_a_long_date_line_takes_four_lines_and_pushes_the_rest_down(layout):
    """The longest case in the narrowest block (95 mm in every layout): the
    whole line is drawn, nothing is reported, and what stands under the row
    starts lower than under a one-line date. Red when the row may not grow:
    "Kernpunt 1 past niet in twee regels" and the line cut after two."""
    long = "DONDERDAG 31 DECEMBER 2027 TOT ZATERDAG 1 JANUARI 2028"
    merged, rows, text_y = _rendered(long, layout)
    _short, short_rows, short_y = _rendered("VRIJDAG 7 MEI", layout)

    assert " ".join(rows) == long and len(rows) == 4, rows
    assert short_rows == ["VRIJDAG 7 MEI"]
    assert render_check(merged) == [], "a date line that is drawn whole is reported"
    assert text_y > short_y, "the row grew over what stands under it"


def render_check(merged) -> list[str]:
    from app.domains.designstudio import render

    return render.check(merged)
