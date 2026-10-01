"""The annual programme: one row per date of an activity, drafts included (#1428).

The board plans its year as a list of dates. Measured here on a situation of its
own, next to whatever the reporting seed holds, and only on the activities this
module makes:

- a course of three evenings is three rows, in date order, with the start time
  where one was given and an empty cell where not;
- a removed date, a removed activity and a date of last year are not in it;
- a draft is in it, and says "Concept"; the audience reads as its label;
- the other tenant's activity is not in it;
- it exports.

Proven red against part A (`4e41b3b6`): the report is not seeded there,
so `_programme` finds no row with the key `annual_programme`.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (
    build_report_ods,
    list_saved_reports,
    resolve_selection,
    run_validated,
    selection_of,
)
from app.soft_delete import soft_delete
from tests._reporting_seed import TENANT_A, TENANT_B


def _activity(db, tenant_id: int, name: str, dates, **fields):
    from app.domains.activities.api import Activity, ActivityDate

    activity = Activity(tenant_id=tenant_id, name=name, **fields)
    db.add(activity)
    db.flush()
    rows = []
    for day, start in dates:
        row = ActivityDate(activity_id=activity.id, start_date=day, start_time=start)
        db.add(row)
        rows.append(row)
    db.flush()
    return activity, rows


@pytest.fixture
def situation(db_session):
    """Three evenings of a draft course, and what must stay out."""
    db = db_session
    today = db.execute(text("SELECT CURRENT_DATE")).scalar()
    year = today.year
    course, evenings = _activity(
        db,
        TENANT_A,
        "Kookcursus 1428",
        [
            (date(year, 3, 12), time(19, 30)),
            (date(year, 1, 15), time(19, 0)),
            (date(year, 2, 5), None),
            (date(year, 4, 2), time(20, 0)),
        ],
        status="draft",
        target_audience="women",
        location="Parochiezaal",
        board_notes="Sleutel bij de koster",
    )
    soft_delete(evenings[3])
    _activity(db, TENANT_A, "Nieuwjaarsdrink 1428", [(date(year - 1, 12, 30), None)])
    gone, _ = _activity(db, TENANT_A, "Verwijderd 1428", [(date(year, 5, 1), None)])
    soft_delete(gone)
    _activity(db, TENANT_B, "Andere tenant 1428", [(date(year, 6, 1), None)])
    db.commit()
    return {"today": today, "year": year}


def _programme(db, tenant_id: int):
    reports = [
        r
        for r in list_saved_reports(db, tenant_id=tenant_id, viewer="")
        if r.builtin_key == "annual_programme"
    ]
    assert len(reports) == 1, "the annual programme is seeded once per tenant"
    return reports[0]


def _run(db, situation, tenant_id=TENANT_A):
    report = _programme(db, tenant_id)
    selection = resolve_selection(selection_of(report), today=situation["today"])
    result = run_validated(db, selection, tenant_id=tenant_id)
    return report, selection, result


def _mine(rows):
    return [r for r in rows if str(r["activity"]).endswith("1428")]


def test_one_row_per_date_in_date_order(db_session, situation):
    _report, _selection, result = _run(db_session, situation)
    rows = _mine(result.rows)
    year = situation["year"]

    assert [r["activity_date_day"] for r in rows] == [
        date(year, 1, 15),
        date(year, 2, 5),
        date(year, 3, 12),
    ], "three evenings, in the order of the year; the removed fourth is not there"
    assert [r["activity_date_time"] for r in rows] == ["19:00", "", "19:30"]
    assert [r["activity_date_month"] for r in rows] == [
        f"{year}-01",
        f"{year}-02",
        f"{year}-03",
    ]


def test_a_draft_is_in_it_with_its_labels(db_session, situation):
    _report, _selection, result = _run(db_session, situation)
    row = _mine(result.rows)[0]

    assert row["activity_status"] == "Concept"
    assert row["activity_target_audience"] == "Vrouwen"
    assert row["activity_location"] == "Parochiezaal"
    assert row["activity_board_notes"] == "Sleutel bij de koster"


def test_what_stays_out(db_session, situation):
    """Last year, a removed activity, and the other tenant."""
    _report, _selection, result = _run(db_session, situation)
    names = {r["activity"] for r in _mine(result.rows)}

    assert names == {"Kookcursus 1428"}, names


def test_the_columns_are_the_programme(db_session, situation):
    """The order Koen asked for: month, date, time, audience, activity, location,
    organisers, notes, status."""
    _report, selection, result = _run(db_session, situation)

    assert list(selection.object_keys) == [
        "activity_date_month",
        "activity_date_day",
        "activity_date_time",
        "activity_target_audience",
        "activity",
        "activity_location",
        "activity_organisers",
        "activity_board_notes",
        "activity_status",
    ]
    assert len(result.columns) == 9


def test_it_exports(db_session, situation):
    report, selection, result = _run(db_session, situation)

    content = build_report_ods(db_session, result, selection, title=report.name, tenant_id=TENANT_A)

    assert len(content) > 500
