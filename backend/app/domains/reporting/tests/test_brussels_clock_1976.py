"""A moment is shown in the association's time, converted in one place (#1976).

For the same moment the newsletter showed 19:04 and the rest of the back office
17:04: the filter `short_datetime` formatted the stored UTC value as given, and
only the newsletter converted on its own. Koen, 15 October 2026, to "Waar gebeurt
de omzetting naar Belgische tijd?": "a" — the display filter converts. So
`app.i18n.local_moment` converts every timezone-aware moment to Brussels, the
formatters call it, and a naive moment is refused.

Per kind of input, in summer and in winter: aware UTC (what every column holds),
already Brussels-aware (a time the board typed, the chatbot's log before this
issue) — which must not shift twice — and naive, which is refused. And the
dashboard's `now` and `today` between 00:00 and 02:00 Belgian time, when the UTC
date is still yesterday.

Broken on purpose (15 October 2026, each put back):
- `local_moment` returning the moment unconverted → the summer, day boundary and
  export tests fail ("14-07-2026 15:04" for "17:04"); the dashboard's stays
  green, as it should: its moment comes Brussels-aware from the kernel clock;
- the naive check taken out → the four refusal tests fail ("DID NOT RAISE");
- the dashboard back on `datetime.now()` → its test fails: the filter refuses
  the naive moment and the page answers with an error.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.kernel.clock import BELGIUM

SUMMER = datetime(2026, 7, 14, 15, 4, tzinfo=timezone.utc)
WINTER = datetime(2026, 1, 14, 15, 4, tzinfo=timezone.utc)
#: 00:30 on the 15th in Brussels, 22:30 on the 14th in UTC.
AFTER_MIDNIGHT = datetime(2026, 7, 14, 22, 30, tzinfo=timezone.utc)


def test_a_stored_moment_is_shown_in_brussels_in_summer_and_in_winter():
    from app.i18n import clock_time, short_datetime

    assert short_datetime(SUMMER) == "14-07-2026 17:04"
    assert short_datetime(WINTER) == "14-01-2026 16:04"
    assert clock_time(SUMMER) == "17:04"


def test_a_moment_already_in_brussels_does_not_shift_twice():
    from app.i18n import short_datetime

    typed = datetime(2026, 7, 14, 17, 4, tzinfo=BELGIUM)
    assert short_datetime(typed) == "14-07-2026 17:04"
    assert short_datetime(datetime(2026, 1, 14, 16, 4, tzinfo=BELGIUM)) == "14-01-2026 16:04"


def test_the_day_of_a_moment_is_its_day_in_brussels():
    from app.i18n import long_date, long_date_no_year, short_date, short_datetime

    assert short_datetime(AFTER_MIDNIGHT) == "15-07-2026 00:30"
    assert short_date(AFTER_MIDNIGHT) == "15-07-2026"
    assert "15 juli 2026" in long_date(AFTER_MIDNIGHT)
    assert long_date_no_year(AFTER_MIDNIGHT).endswith("15 juli")


def test_a_date_stays_a_date():
    from app.i18n import long_date, short_date

    assert short_date(date(2026, 7, 14)) == "14-07-2026"
    assert "14 juli 2026" in long_date(date(2026, 7, 14))


@pytest.mark.parametrize("name", ["short_datetime", "short_date", "long_date", "clock_time"])
def test_a_naive_moment_is_refused(name):
    import app.i18n as i18n

    with pytest.raises(ValueError, match="time zone"):
        getattr(i18n, name)(datetime(2026, 7, 14, 15, 4))


def test_an_export_column_keeps_its_own_shape_in_brussels():
    from app.i18n import moment_text

    assert moment_text(SUMMER, "%Y-%m-%d %H:%M") == "2026-07-14 17:04"
    assert moment_text(WINTER, "%d/%m/%Y %H:%M") == "14/01/2026 16:04"
    assert moment_text(None, "%Y-%m-%d %H:%M") == ""


def test_the_dashboard_stands_on_today_in_brussels_after_midnight(client, db_session, monkeypatch):
    """Between 00:00 and 02:00 Belgian time the UTC date is still yesterday: the
    dashboard's `today` (on which its tiles resolve "vandaag") and the line under
    it come from the kernel clock, in Brussels."""
    import app.domains.reporting.api as reporting_api
    import app.kernel.clock as clock
    from app.domains.reporting.tests.test_reporting_panel_ui import login
    from tests.conftest import SEEDED_ADMIN_EMAIL

    real_now = clock.belgian_now
    monkeypatch.setattr(clock, "belgian_now", lambda now=None: real_now(now or AFTER_MIDNIGHT))
    asked: list[date] = []
    real_numbers = reporting_api.dashboard_numbers

    def numbers(*args, **kwargs):
        asked.append(kwargs["today"])
        return real_numbers(*args, **kwargs)

    monkeypatch.setattr(reporting_api, "dashboard_numbers", numbers)

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    page = client.get("/admin")

    assert page.status_code == 200
    assert asked == [date(2026, 7, 15)]
    assert "15 juli 2026 · 00:30" in page.text
