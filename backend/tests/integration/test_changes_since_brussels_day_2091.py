"""The changes feed reads "since this day" as the start of the Brussels day (#2091).

`all_changes_since(db, day)` used to turn the day into UTC midnight, so a change made
at 00:30 Brussels on the 17th (22:30 UTC on the 16th) lay before "since the 17th" and
dropped out of today's feed for the first two hours of every Brussels day in summer.
Red before the change: the first case below failed, the row missing from the feed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.mdm.api import Person, PersonHistory, snapshot_person
from app.domains.reporting.api import all_changes_since
from app.kernel.clock import belgian_day_start

DAY = date(2026, 10, 17)  # summer time: Brussels is UTC+2, so the day starts at 22:00 UTC


def _change_at(db, moment, name):
    person = Person(first_name=name, last_name="Wijziging")
    db.add(person)
    db.flush()
    snapshot_person(
        db,
        person,
        operation="insert",
        action="person_created",
        source="test",
        actor="tester@example.com",
    )
    db.commit()
    row = db.query(PersonHistory).filter(PersonHistory.person_id == person.id).one()
    row.recorded_at = moment
    db.commit()
    return person.id


def _ids(db, day):
    return {r["entity_id"] for r in all_changes_since(db, day) if r["entity"] == "Persoon"}


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc),  # 00:00 Brussels
        datetime(2026, 10, 16, 22, 30, tzinfo=timezone.utc),  # 00:30 Brussels
        datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc),  # 10:00 Brussels
    ],
)
def test_a_change_after_midnight_in_brussels_shows_under_that_day(db_session, moment):
    person_id = _change_at(db_session, moment, "Na")

    assert person_id in _ids(db_session, DAY)


def test_a_change_before_midnight_in_brussels_does_not(db_session):
    # 23:30 Brussels on the 16th, 21:30 UTC: still the 16th.
    person_id = _change_at(db_session, datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc), "Voor")

    assert person_id not in _ids(db_session, DAY)


def test_the_day_starts_at_22_utc_in_summer_and_23_utc_in_winter():
    summer = belgian_day_start(date(2026, 7, 1)).astimezone(belgian_day_start(DAY).tzinfo)
    assert belgian_day_start(date(2026, 7, 1)).utcoffset() == timedelta(hours=2)
    assert belgian_day_start(date(2026, 12, 1)).utcoffset() == timedelta(hours=1)
    assert summer.hour == 0
