"""'Wie doet er mee?' lists registrations from old to new (#1340).

Koen, 29 September 2026: the list on the home page looked reversed, the most
recent first. `Activity.registrations` had no `order_by`, so the list followed the
order in which PostgreSQL returned the rows — which is not the order of registering.

**Two measurements shape these tests** (dev1, on master `08beaa85`):

- changing the oldest row afterwards (`remarks`, then `expire_all`) still came back
  A, B, C: no indexed column changes, so the update is HOT and the row keeps its
  place. A behaviour test of "the oldest was changed" stays green on the broken
  code, so the clause itself is tested, as `test_sorteervolgorde_gelijkstand.py`
  does for the same trap;
- what does come back wrong on master is a registration entered later for an
  earlier moment — the board typing in a paper form: B, A, C instead of A, B, C.
  That is the main test, on the relationship and on the public screen.

The same fix, in the same issue: the member card's membership years (oldest first,
as the card has always shown them by accident — and the card proposed "the year
after the first" as the next one to add, which was the oldest year + 1; now the
year after the last) and a household's members on the board's family view (the
portal's `household_position`).

Newest first was tried and dropped: the e2e flow that removes a membership takes the
card's first row, and newest first made that the pending renewal instead of the
current year — the change reordered what the board sees, not only what it gets.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `order_by` removed from `Activity.registrations` → the paper-form test on
the list and on the screen (B, A, C), and the clause test; `order_by` removed from
the `memberships` backref → the membership clause test (a behaviour test stayed
green: the unique index on (member, year) returns them by year anyway); `sorted(…)` removed from
`_build_family_response` → the household test; `memberships[-1]` set back to
`memberships[0]` in `_leden_kaarten.html` → the proposal test (2026 instead of 2028).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.activities.api import Activity, Registration, public_registrations
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch

START = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _register(db, activity, component, name: str, minutes: int) -> Registration:
    reg = Registration(
        activity_id=activity.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_name=name,
        contact_email=f"{name.lower()}@example.com",
        phone="0470000000",
        registered_at=START + timedelta(minutes=minutes),
    )
    db.add(reg)
    db.flush()
    return reg


@pytest.fixture
def paper_form_last(db_session):
    """Bert and Carla registered at 10:05; Anna's paper form (10:00) typed in after
    Bert, before Carla. Registering order is Anna, Bert, Carla — the ids are not."""
    activity, component, _product = seed_activity_with_product(db_session)
    _register(db_session, activity, component, "Bert", 5)
    _register(db_session, activity, component, "Anna", 0)
    _register(db_session, activity, component, "Carla", 5)
    db_session.commit()
    db_session.expire_all()
    return activity, component


def test_the_moment_of_registering_decides_not_the_row(db_session, paper_form_last):
    activity, component = paper_form_last
    names = [r["contact_name"] for r in public_registrations(db_session, activity.id, component.id)]
    assert names == ["Anna", "Bert", "Carla"], names


@pytest.mark.ui_serverrendered
def test_the_public_list_shows_them_in_registering_order(client, paper_form_last):
    activity, component = paper_form_last
    html = client.get(f"/activiteiten/{activity.id}/deelnemers/{component.id}").text
    text = re.sub(r"<[^>]+>", " ", html)
    positions = [text.find(name) for name in ("Anna", "Bert", "Carla")]
    assert -1 not in positions, text
    assert positions == sorted(positions), f"'Wie doet er mee?' reads: {' '.join(text.split())}"


def test_the_order_is_the_moment_then_the_id():
    """The clause, because a changed row keeps its place in a HOT update (above)."""
    keys = [getattr(k, "name", str(k)) for k in Activity.registrations.property.order_by]
    assert keys == ["registered_at", "id"], keys


def test_membership_years_are_ordered_by_year_then_id():
    """The clause, not the rows: `uq_memberships_member_year` makes PostgreSQL read a
    household's memberships through that index, so they come back by year even
    without an order — measured, the behaviour test stayed green on the broken code.
    Another plan (a bulk load, no index) would not."""
    from app.domains.mdm.api import Member

    keys = [getattr(k, "name", str(k)) for k in Member.memberships.property.order_by]
    assert keys == ["year", "id"], keys


@pytest.mark.ui_serverrendered
def test_the_card_proposes_the_year_after_the_last(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.mdm.api import Member
    from app.domains.membership.api import Membership
    from tests.conftest import SEEDED_ADMIN_EMAIL

    member = Member()
    db_session.add(member)
    db_session.flush()
    for year in (2025, 2027, 2026):
        db_session.add(Membership(member_id=member.id, year=year))
    db_session.commit()

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/leden/gezin/{member.id}").text
    field = re.search(r'<input[^>]*name="year"[^>]*>', html)
    assert field, "no year field on the membership card"
    assert 'value="2028"' in field.group(0), field.group(0)


def test_the_board_sees_a_household_in_its_own_order(db_session):
    """The primary member first, then the partner, then the children oldest first —
    whatever order the rows were added in."""
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.household_service import _build_family_response

    member = Member()
    db_session.add(member)
    db_session.flush()
    people = [
        ("Kind", "Jong", date(2018, 1, 1), "KIND"),
        ("Hoofd", "Lid", date(1980, 1, 1), "HOOFDLID"),
        ("Kind", "Oud", date(2012, 1, 1), "KIND"),
        ("Partner", "Lid", date(1982, 1, 1), "PARTNER"),
    ]
    for last, first, born, relation in people:
        person = Person(first_name=first, last_name=last, date_of_birth=born, gender_code="X")
        db_session.add(person)
        db_session.flush()
        db_session.add(
            MemberPerson(member_id=member.id, person_id=person.id, relation_type=relation)
        )
    db_session.commit()
    db_session.expire_all()

    family = _build_family_response(db_session.get(Member, member.id))
    assert [f"{p.last_name} {p.first_name}" for p in family.members] == [
        "Hoofd Lid",
        "Partner Lid",
        "Kind Oud",
        "Kind Jong",
    ]
