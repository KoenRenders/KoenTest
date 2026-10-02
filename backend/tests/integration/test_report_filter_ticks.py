"""Ticking several values in a report filter (#1445).

Koen, 1 October 2026, at the annual programme for 2026 and 2027: a filter could
hold one value only. A closed list is a set of ticks now — one tick compares
exactly (EQ, as before), several mean "one of" (IN) — and the ticks travel
everywhere the filter does: the panel, the export, a saved report.

Measured through the real routes, on activities of their own in 2025, 2026 and
2027, with the years as literal ticks ("dit jaar" is resolved against the real
clock inside `run_validated`, so a test of fixed years ticks the years):

- 2026 and 2027 ticked: the programme shows both years and not 2025, and the
  .ods carries the same rows;
- one tick saves as EQ with that value, two save as IN with both;
- a saved report with two years reopens with both boxes ticked;
- "Dit jaar" ticked beside next year means both (Koen's choice): the relative
  value is added to the fixed one, on screen and in what is saved.

Proven red against master `cbd15865`: there a filter takes one value
(`params.get`), so the two-year panel shows 2027 only — the last value wins.
"""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from urllib.parse import urlencode

import pytest

from app.domains.reporting.api import list_saved_reports
from app.domains.reporting.tests.test_reporting_panel_ui import ADMIN_EMAIL, login
from tests._reporting_seed import TENANT_A

MARK = " 1445"
YEAR_FILTER = "year_first_date_year"
#: The annual programme's own columns (#1439), so the panel runs on its fact.
OBJECTS = ("year_first_date_day", "year_dates", "activity", "activity_status")


@pytest.fixture
def situation(db_session):
    from app.domains.activities.api import Activity, ActivityDate

    for year in (2025, 2026, 2027):
        activity = Activity(tenant_id=TENANT_A, name=f"Programma {year}{MARK}")
        db_session.add(activity)
        db_session.flush()
        db_session.add(ActivityDate(activity_id=activity.id, start_date=date(year, 5, 10)))
    db_session.commit()


def _query(*years: str) -> str:
    pairs = [("object", k) for k in OBJECTS] + [("filter", YEAR_FILTER)]
    pairs += [(f"v_{YEAR_FILTER}", y) for y in years]
    pairs += [(f"op_{YEAR_FILTER}", "eq"), ("layout", "detail")]
    return urlencode(pairs)


def _panel_names(client, query: str) -> list[str]:
    answer = client.get(f"/admin/rapporten/paneel?{query}")
    assert answer.status_code == 200
    return sorted(set(re.findall(rf"Programma \d{{4}}{MARK}", answer.text)))


def _export_names(client, query: str) -> list[str]:
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.teletype import extractText

    answer = client.get(f"/admin/rapporten/export.ods?{query}")
    assert answer.status_code == 200
    table = load(BytesIO(answer.content)).getElementsByType(Table)[0]
    cells = [
        extractText(cell)
        for row in table.getElementsByType(TableRow)
        for cell in row.getElementsByType(TableCell)
    ]
    return sorted(c for c in cells if c.endswith(MARK))


def test_two_ticked_years_show_both_and_the_export_agrees(client, db_session, situation):
    login(client, db_session)
    query = _query("2026", "2027")

    on_screen = _panel_names(client, query)

    assert on_screen == ["Programma 2026" + MARK, "Programma 2027" + MARK], on_screen
    assert _export_names(client, query) == on_screen, "the export is the screen"


def test_one_tick_is_still_exact(client, db_session, situation):
    login(client, db_session)

    assert _panel_names(client, _query("2026")) == ["Programma 2026" + MARK]


@pytest.fixture
def saved(client, db_session, situation):
    """Save through the real form post, as htmx sends it; return the stored rows."""
    csrf = login(client, db_session)
    stored = {}
    for name, years in (("Een jaar", ("2026",)), ("Twee jaren", ("2026", "2027"))):
        answer = client.post(
            "/admin/rapporten",
            headers={"X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded"},
            content=f"name={name.replace(' ', '+')}&is_shared=1&{_query(*years)}",
        )
        assert answer.status_code == 200 and "Opgeslagen" in answer.text, answer.text[:300]
    db_session.expire_all()
    for report in list_saved_reports(db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL):
        if report.name in ("Een jaar", "Twee jaren"):
            stored[report.name] = report
    return stored


def test_one_tick_saves_as_eq_and_two_as_in(saved):
    [one] = saved["Een jaar"].selection["filters"]
    [two] = saved["Twee jaren"].selection["filters"]

    assert (one["operator"], one["values"]) == ("eq", ["2026"])
    assert (two["operator"], two["values"]) == ("in", ["2026", "2027"])


def test_a_saved_report_with_two_years_reopens_with_both_ticked(client, saved):
    page = client.get(f"/admin/rapporten/{saved['Twee jaren'].id}").text

    for year in ("2026", "2027"):
        box = re.search(
            rf'<input type="checkbox" name="v_{YEAR_FILTER}" value="{year}"[^>]*>', page
        )
        assert box, f"{year} is not offered as a tick"
        assert "checked" in box.group(0), f"{year} reopens unticked"
    unticked = re.search(rf'<input type="checkbox" name="v_{YEAR_FILTER}" value="2025"[^>]*>', page)
    assert unticked and "checked" not in unticked.group(0), "2025 was never ticked"


def test_this_year_ticked_beside_next_year_means_both(client, db_session):
    """On the real clock: this is the one place "dit jaar" must move with it."""
    from app.domains.activities.api import Activity, ActivityDate

    this_year = date.today().year
    for year in (this_year - 1, this_year, this_year + 1):
        activity = Activity(tenant_id=TENANT_A, name=f"Programma {year}{MARK}")
        db_session.add(activity)
        db_session.flush()
        db_session.add(ActivityDate(activity_id=activity.id, start_date=date(year, 5, 10)))
    db_session.commit()
    csrf = login(client, db_session)
    query = _query("@dit_jaar", str(this_year + 1))

    assert _panel_names(client, query) == [
        f"Programma {this_year}{MARK}",
        f"Programma {this_year + 1}{MARK}",
    ]
    assert _export_names(client, query) == _panel_names(client, query)

    answer = client.post(
        "/admin/rapporten",
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded"},
        content=f"name=Dit+en+volgend+jaar&is_shared=1&{query}",
    )
    assert "Opgeslagen" in answer.text
    db_session.expire_all()
    [report] = [
        r
        for r in list_saved_reports(db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
        if r.name == "Dit en volgend jaar"
    ]
    [saved_filter] = report.selection["filters"]
    # Saved relative, so next January it is that year plus the fixed one.
    assert saved_filter["symbolic"] == "dit_jaar"
    assert saved_filter["values"] == [str(this_year + 1)]
