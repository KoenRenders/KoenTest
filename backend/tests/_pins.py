"""Both clocks pinned inside the window between midnight in Brussels and midnight UTC (#2156).

The application's clock (`kernel.clock`) and the database's `now()` are put at 22:30 UTC
on 2 October 2026: 00:30 on the 3rd in Brussels, 22:30 on the 2nd in UTC. A reader that
asks the tenant's day says the 3rd in both languages; a reader that still asks the
database's own `CURRENT_DATE` says whatever day the database really is on — it cannot be
pinned — so a test that compares the two is red on the old views at ANY hour and green on
the new ones at any hour, instead of red only inside the hour itself.

- Python: the clock's `datetime` is replaced by a subclass whose `now()` is the pinned
  instant (the clock reads `datetime.now(timezone.utc)` and nothing else).
- SQL: a function `now()` in a schema of the test, first on the search path for this
  transaction (the temporary schema is never searched for functions, so a real schema
  is made; it goes with the rolled-back transaction). `mdm.tenant_today()` calls the
  unqualified `now()`, so it follows. The database's `CURRENT_DATE` is a keyword and
  does not.

Measured (19 October 2026, dev4's review of #2165): the four parity tests of the issue run
with the pin at any hour and are green on the new views. Against the OLD views — their
definitions put back, `CURRENT_DATE` read as the UTC day of the pinned `now()`, which is what
Postgres says at that instant — `test_the_member_list_and_the_dashboard_give_the_same_number`
and `test_a_household_that_joined_after_the_turnover_date_counts_on_both` are red at any
hour. The dashboard tile and the saved-report/button pair stay green: their data is made with
the real clock (`created_at` defaults), so they differ only when the real instant lies in
the window, which a pin of the two clocks cannot force without pinning every row's
creation moment. They are in the window's company here nonetheless, and green.

Use: `@pytest.mark.usefixtures("pinned_window")` after `from tests._pins import
pinned_window  # noqa: F401`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.kernel import clock

PINNED = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
SCHEMA = "pin_2156"


class _Pinned(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: D102 - the clock only ever asks `now(timezone.utc)`
        return PINNED.astimezone(tz) if tz is not None else PINNED.replace(tzinfo=None)


def pin_database_now(db, moment: datetime = PINNED) -> None:
    """The database's `now()` at `moment` for this transaction (read from a setting, so a
    test can move it between two queries: `SELECT set_config('pin_2156.at', …, true)`)."""
    db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    db.execute(
        text(
            f"CREATE OR REPLACE FUNCTION {SCHEMA}.now() RETURNS timestamptz LANGUAGE sql AS "
            f"$$ SELECT current_setting('{SCHEMA}.at')::timestamptz $$"
        )
    )
    db.execute(
        text("SELECT set_config(:name, :at, true)"),
        {"name": f"{SCHEMA}.at", "at": moment.isoformat()},
    )
    db.execute(text(f"SET LOCAL search_path = {SCHEMA}, pg_catalog, public"))


@pytest.fixture
def pinned_window(db_session, monkeypatch):
    monkeypatch.setattr(clock, "datetime", _Pinned)
    pin_database_now(db_session)
    yield PINNED
