"""The annual programme: every activity once per year, drafts included (#1428, #1439).

#1428 built it with one row per date. Koen, validating it: a monthly bike ride
stood in it twelve times. #1439: one row per activity, its first date and that
date's time for the sort, and one cell "Datums" with all its dates in that year,
joined like the organisers.

Measured on a situation of its own in 2027 — a fixed year, set as the value of
the report's own year filter (the way a board member picks another year; "dit
jaar" is resolved against the real clock inside `run_validated`) — and only on
the activities this module makes:

- three dates give one row: "Datum" is the first, "Datums" holds all three in
  order; a removed fourth date is not in it;
- the time is in "Datums" only when it differs between the dates;
- one date gives that one date;
- New Year: a series with dates in both years is in each year with that year's
  dates; one date running from 31 December to 2 January is in the year it starts;
- a draft is in it with its labels; last year, a removed activity and the other
  tenant are not;
- the .ods has as many rows as the screen.

Proven red against master `2f1b853e`: there the report lists one row per date,
so `test_three_dates_are_one_row` finds three rows for the course.
"""

from __future__ import annotations

import re
from datetime import date, time
from io import BytesIO

import pytest

from app.domains.reporting.api import (
    build_report_ods,
    list_saved_reports,
    run_validated,
    selection_from_dict,
)
from app.soft_delete import soft_delete
from tests._reporting_seed import TENANT_A, TENANT_B

YEAR = 2027
MARK = " 1439"


def _activity(db, tenant_id: int, name: str, dates, **fields):
    """`dates` are (start, time) or (start, time, end)."""
    from app.domains.activities.api import Activity, ActivityDate

    activity = Activity(tenant_id=tenant_id, name=name + MARK, **fields)
    db.add(activity)
    db.flush()
    rows = []
    for start, at, *end in dates:
        row = ActivityDate(
            activity_id=activity.id,
            start_date=start,
            start_time=at,
            end_date=end[0] if end else None,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return activity, rows


@pytest.fixture
def situation(db_session):
    db = db_session
    _, evenings = _activity(
        db,
        TENANT_A,
        "Kookcursus",
        [
            (date(YEAR, 3, 12), time(19, 30)),
            (date(YEAR, 1, 15), time(19, 0)),
            (date(YEAR, 2, 5), None),
            (date(YEAR, 4, 2), time(20, 0)),
        ],
        status="draft",
        target_audience="women",
        location="Parochiezaal",
        board_notes="Sleutel bij de koster",
    )
    soft_delete(evenings[3])
    _activity(
        db,
        TENANT_A,
        "Fietstocht",
        [(date(YEAR, m, 1), time(9, 0)) for m in (5, 6, 7)],
    )
    _activity(db, TENANT_A, "Quiz", [(date(YEAR, 10, 9), time(20, 0))])
    _activity(
        db,
        TENANT_A,
        "Wintercursus",
        [(date(YEAR, 11, 20), None), (date(YEAR + 1, 2, 5), None)],
    )
    _activity(
        db,
        TENANT_A,
        "Oudejaarsweekend",
        [(date(YEAR, 12, 31), None, date(YEAR + 1, 1, 2))],
    )
    _activity(db, TENANT_A, "Nieuwjaarsdrink", [(date(YEAR - 1, 12, 30), None)])
    gone, _ = _activity(db, TENANT_A, "Verwijderd", [(date(YEAR, 5, 1), None)])
    soft_delete(gone)
    _activity(db, TENANT_B, "Andere tenant", [(date(YEAR, 6, 1), None)])
    db.commit()


def _programme(db, tenant_id: int):
    reports = [
        r
        for r in list_saved_reports(db, tenant_id=tenant_id, viewer="")
        if r.builtin_key == "annual_programme"
    ]
    assert len(reports) == 1, "the annual programme is seeded once per tenant"
    return reports[0]


def _run(db, year: int = YEAR, tenant_id: int = TENANT_A):
    """The shipped report, with its year filter set to `year`."""
    report = _programme(db, tenant_id)
    stored = dict(report.selection)
    [year_filter] = stored["filters"]
    assert year_filter["symbolic"] == "dit_jaar", "the report filters on this year"
    stored["filters"] = [{**year_filter, "symbolic": "", "values": [str(year)]}]
    selection = selection_from_dict(stored)
    result = run_validated(db, selection, tenant_id=tenant_id)
    return report, selection, result


def _mine(rows) -> dict[str, dict]:
    """This module's rows, by activity name without the mark. A name that comes
    twice is the bug this issue is about, so it fails here rather than vanish."""
    mine = [r for r in rows if str(r["activity"]).endswith(MARK)]
    names = [r["activity"].removesuffix(MARK) for r in mine]
    assert len(names) == len(set(names)), f"an activity is in it twice: {names}"
    return dict(zip(names, mine))


def test_three_dates_are_one_row(db_session, situation):
    _report, _selection, result = _run(db_session)
    rows = [r for r in result.rows if r["activity"] == "Kookcursus" + MARK]

    assert len(rows) == 1, f"three dates, one row — not {len(rows)}"
    row = rows[0]
    assert row["year_first_date_day"] == date(YEAR, 1, 15), "Datum is the first date"
    assert row["year_first_date_month"] == f"{YEAR}-01", "Maand follows the first date"
    assert row["year_first_time"] == "19:00"
    # The times differ (19:00, none, 19:30), so each date that has one carries it.
    assert row["year_dates"] == (f"15-01-{YEAR} 19:00 · 05-02-{YEAR} · 12-03-{YEAR} 19:30"), (
        "all three, in order; the removed fourth is not there"
    )


def test_the_time_is_left_out_when_every_date_shares_it(db_session, situation):
    _report, _selection, result = _run(db_session)
    row = _mine(result.rows)["Fietstocht"]

    assert row["year_first_time"] == "09:00"
    assert row["year_dates"] == f"01-05-{YEAR} · 01-06-{YEAR} · 01-07-{YEAR}"


def test_one_date_gives_that_date(db_session, situation):
    _report, _selection, result = _run(db_session)
    row = _mine(result.rows)["Quiz"]

    assert row["year_first_date_day"] == date(YEAR, 10, 9)
    assert row["year_dates"] == f"09-10-{YEAR}"


def test_new_year(db_session, situation):
    """A date belongs to the year it starts in."""
    _report, _selection, this_year = _run(db_session)
    _report, _selection, next_year = _run(db_session, YEAR + 1)
    now, then = _mine(this_year.rows), _mine(next_year.rows)

    assert now["Wintercursus"]["year_dates"] == f"20-11-{YEAR}"
    assert then["Wintercursus"]["year_dates"] == f"05-02-{YEAR + 1}"
    assert then["Wintercursus"]["year_first_date_day"] == date(YEAR + 1, 2, 5)

    assert now["Oudejaarsweekend"]["year_dates"] == f"31-12-{YEAR}–02-01-{YEAR + 1}"
    assert "Oudejaarsweekend" not in then, "it starts in the old year and stays there"


def test_a_draft_is_in_it_with_its_labels(db_session, situation):
    _report, _selection, result = _run(db_session)
    row = _mine(result.rows)["Kookcursus"]

    assert row["activity_status"] == "Concept"
    assert row["activity_target_audience"] == "Vrouwen"
    assert row["activity_location"] == "Parochiezaal"
    assert row["activity_board_notes"] == "Sleutel bij de koster"


def test_what_stays_out_and_the_order(db_session, situation):
    """Last year, a removed activity and the other tenant are not in it; the rows
    come by their first date."""
    _report, _selection, result = _run(db_session)

    assert list(_mine(result.rows)) == [
        "Kookcursus",
        "Fietstocht",
        "Quiz",
        "Wintercursus",
        "Oudejaarsweekend",
    ]


def test_the_columns_are_the_programme(db_session, situation):
    _report, selection, result = _run(db_session)

    assert list(selection.object_keys) == [
        "year_first_date_month",
        "year_first_date_day",
        "year_first_time",
        "year_dates",
        "activity_target_audience",
        "activity",
        "activity_location",
        "activity_organisers",
        "activity_board_notes",
        "activity_status",
    ]
    assert len(result.columns) == 10


def _sheet(content: bytes) -> list[list[str]]:
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.teletype import extractText

    table = load(BytesIO(content)).getElementsByType(Table)[0]
    return [
        [extractText(cell) for cell in row.getElementsByType(TableCell)]
        for row in table.getElementsByType(TableRow)
    ]


def test_the_export_has_the_rows_of_the_screen(db_session, situation):
    report, selection, result = _run(db_session)

    sheet = _sheet(
        build_report_ods(db_session, result, selection, title=report.name, tenant_id=TENANT_A)
    )
    exported = [row for row in sheet if any(cell.endswith(MARK) for cell in row)]

    assert result.rows, "the screen shows something"
    assert len(exported) == len(_mine(result.rows)) == 5
    # The sheet opens with a head block (report, filter, column names); a data
    # row is one whose first cell is a month, `2027-03`.
    data = [row for row in sheet if row and re.fullmatch(r"\d{4}-\d{2}", row[0])]
    assert len(data) == len(result.rows), "every row of the screen, once"
