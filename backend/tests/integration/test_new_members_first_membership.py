"""A new member is one whose FIRST membership begins in the window (#1358).

Found by Koen on 29 September 2026, preparing the meeting of 1 October on PROD:
six households with only a membership of 2025 stood under "Leden" as new, because
a catch-up import had created their records that week. The section chose by
`Member.created_at`; it now chooses by the start of the earliest membership that
is not deleted — `valid_from`, or 1 January of `year`.

Proven red against master `e308b5aa`, this file copied onto an export of it (with a
shim calling the old `mdm.new_members_between`): six of seven failed — the
imported household was new, the old record that began now was not, and so on.
The seventh, a renewal, passes on master because that household is old; it was
proven with an added violation instead: the LAST membership in place of the
first (`func.max` for `func.min`) makes it fail. Run and restored.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.meetings.api import SectionKind, create_meeting, document_of
from app.domains.membership.api import Membership, new_members_between

pytestmark = pytest.mark.ui_agnostisch

WINDOW = (date(2026, 9, 3), date(2026, 10, 2))  # since the previous meeting, to 1 October
LONG_AGO = datetime(2020, 5, 1, tzinfo=timezone.utc)


def _household(db, last: str, *, created: datetime | None = None) -> Member:
    household = Member()
    if created is not None:
        household.created_at = created
    db.add(household)
    db.flush()
    head = Person(
        first_name="Hoofd", last_name=last, date_of_birth=date(1980, 1, 1), gender_code="M"
    )
    db.add(head)
    db.flush()
    db.add(MemberPerson(member_id=household.id, person_id=head.id, relation_type="HOOFDLID"))
    db.flush()
    return household


def _membership(db, household, year: int, valid_from: date | None = None) -> Membership:
    membership = Membership(
        member_id=household.id,
        year=year,
        valid_from=valid_from,
        valid_to=date(year, 12, 31) if valid_from else None,
    )
    db.add(membership)
    db.flush()
    return membership


def _new_ids(db) -> list[int]:
    return [row["member_id"] for row in new_members_between(db, *WINDOW)]


def test_a_catch_up_import_of_last_year_is_not_new(db_session):
    """Created today, with only a membership of last year: the PROD case."""
    imported = _household(db_session, "Inhaalimport")
    _membership(db_session, imported, 2025, date(2025, 3, 1))

    assert imported.id not in _new_ids(db_session)


def test_an_old_record_whose_first_membership_begins_now_is_new(db_session):
    household = _household(db_session, "Lang Gekend", created=LONG_AGO)
    _membership(db_session, household, 2026, date(2026, 9, 15))

    assert household.id in _new_ids(db_session)


def test_without_a_valid_from_the_first_of_january_counts(db_session):
    """No `valid_from`: 1 January of `year`, here outside the window."""
    household = _household(db_session, "Zonder Begindatum")
    _membership(db_session, household, 2026)

    assert household.id not in _new_ids(db_session)


def test_a_renewal_is_not_new(db_session):
    household = _household(db_session, "Vernieuwer", created=LONG_AGO)
    _membership(db_session, household, 2025, date(2025, 2, 1))
    _membership(db_session, household, 2026, date(2026, 9, 20))

    assert household.id not in _new_ids(db_session)


def test_a_deleted_membership_does_not_count(db_session):
    """A deleted earlier membership is not the first one: the live one in the
    window makes the household new."""
    household = _household(db_session, "Herbegin", created=LONG_AGO)
    deleted = _membership(db_session, household, 2025, date(2025, 2, 1))
    deleted.deleted_at = datetime.now(timezone.utc)
    _membership(db_session, household, 2026, date(2026, 9, 10))
    db_session.flush()

    assert household.id in _new_ids(db_session)


def test_a_household_without_a_membership_is_not_new(db_session):
    household = _household(db_session, "Geen Lidmaatschap")

    assert household.id not in _new_ids(db_session)


def test_the_meeting_agenda_follows_the_rule(db_session):
    """Through the agenda build: "Leden" of the meeting of 1 October holds the
    household that began, not the imported one."""
    imported = _household(db_session, "Inhaalimport")
    _membership(db_session, imported, 2025, date(2025, 3, 1))
    joined = _household(db_session, "Nieuwkomer", created=LONG_AGO)
    _membership(db_session, joined, 2026, date(2026, 9, 15))

    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    labels = [
        item.label
        for s in document_of(db_session, meeting)
        if s.kind is SectionKind.MEMBERS
        for item in s.items
    ]
    assert "Hoofd Nieuwkomer" in labels
    assert "Hoofd Inhaalimport" not in labels
