"""The tile "Komende activiteiten (alle statussen)" and its report count the same (#1979).

The tile counted seven where the public list showed six: one activity was a
draft. Koen chose to keep the count and let the name say so (14 October 2026:
"b"), in the words "Komende activiteiten (alle statussen)" (15 October 2026:
"a") — on the tile and on the title of its report.

One published, one draft, one cancelled and one soft-deleted upcoming activity:
the tile's figure and its report give the same number, three more than before —
the draft and the cancelled one counted, the soft-deleted one not.

Broken on purpose (15 October 2026, put back): the migration's rename taken out
→ the title test fails on "Dashboard — Komende activiteiten".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.reporting.api import (
    DASHBOARD_TEGELS,
    dashboard_numbers,
    list_saved_reports,
    run_validated,
    selection_of,
)
from app.domains.reporting.tests.test_reporting_panel_ui import ADMIN_EMAIL
from app.kernel.clock import belgian_today
from tests._reporting_seed import TENANT_A, seed

KEY = "dashboard_upcoming_activities"
MEASURE = next(m for _l, k, m, _h, _g in DASHBOARD_TEGELS if k == KEY)


def _report(db):
    return next(
        r
        for r in list_saved_reports(db, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
        if r.builtin_key == KEY
    )


def _both(db, today: date) -> tuple[int, int]:
    """The tile's figure and the figure of the report behind its link."""
    tile = dashboard_numbers(
        db, [(KEY, MEASURE)], tenant_id=TENANT_A, viewer=ADMIN_EMAIL, today=today
    )[KEY].value
    result = run_validated(db, selection_of(_report(db)), tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
    assert len(result.rows) == 1, "a tile's report gives one row with one number"
    return tile, result.rows[0][MEASURE]


def _activity(db, name: str, **state) -> None:
    from app.domains.activities.api import Activity, ActivityDate

    activity = Activity(tenant_id=TENANT_A, name=name, **state)
    db.add(activity)
    db.flush()
    db.add(
        ActivityDate(
            tenant_id=TENANT_A,
            activity_id=activity.id,
            start_date=belgian_today() + timedelta(days=10),
        )
    )
    db.flush()


def test_the_tile_and_its_report_count_every_status_but_not_a_deleted_one(db_session):
    from app.domains.activities.api import ActivityStatus

    seed(db_session)
    today = belgian_today()
    tile_before, report_before = _both(db_session, today)
    assert tile_before == report_before

    _activity(db_session, "Gepubliceerd 1979", status=ActivityStatus.PUBLISHED)
    _activity(db_session, "Concept 1979", status=ActivityStatus.DRAFT)
    _activity(db_session, "Geannuleerd 1979", status=ActivityStatus.PUBLISHED, is_cancelled=True)
    _activity(
        db_session,
        "Verwijderd 1979",
        status=ActivityStatus.PUBLISHED,
        deleted_at=datetime.now(timezone.utc),
    )

    tile, report = _both(db_session, today)
    assert tile == report, f"the tile says {tile}, its report {report}"
    assert tile - tile_before == 3, (
        f"published, draft and cancelled count, the soft-deleted one not: +{tile - tile_before}"
    )


def test_the_tile_and_its_report_say_all_statuses(db_session):
    seed(db_session)
    label = next(label for label, k, _m, _h, _g in DASHBOARD_TEGELS if k == KEY)
    assert label == "Komende activiteiten (alle statussen)"
    assert _report(db_session).name == "Dashboard — Komende activiteiten (alle statussen)"


@pytest.mark.parametrize("path", ["/admin"])
def test_the_dashboard_shows_the_new_name(client, db_session, path):
    from app.domains.reporting.tests.test_reporting_panel_ui import login
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    assert "Komende activiteiten (alle statussen)" in client.get(path).text
