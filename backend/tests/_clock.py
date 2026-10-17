"""The UTC day, for the tests whose subject reads a date as a UTC day (#2091).

A test that asks for "today" asks the clock the app asks: `belgian_today()`. The one
exception is the changes feed: `all_changes_since(db, since)` turns the date it is
given into UTC midnight (`reporting/changes.py`, `datetime.combine(since, time.min,
tzinfo=timezone.utc)`), so a test that reads the feed since "today" must name the same
UTC day, or between 22:00 and 24:00 UTC its own rows lie before its own `since`.
Named here, once, and not as `date.today()`, which the Brussels-day gate refuses in a
test (`test_brussels_day_gate_2065.py`).
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
