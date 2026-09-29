"""CR-13 phase 1 (§B4.3, AC5): one registration total, five ways of asking for it.

`activities.totals` owns the computation. `Registration.total()` delegates to it
and stays a delegate (master CLI, 29 September 2026): the same price rule also
quotes the public form before a registration exists (`quote_lines`) and the back
office's live recomputation (`quote_registration`). The report cannot call Python
at all; `reporting.f_registrations` repeats the member-price rule in SQL — the one
declared second computation, bound here by a parity test (§B4.3).

For a member and a guest, over a paid product with a member price, a free product
and a pay-on-site one, all five must give the same amount:

`registration.total()` · `compute_registration_total` · `quote_registration` ·
`quote_lines` · the sum of the view's `line_amount`.

Broken on purpose to see this go red (run, then undone with the reverse edit): the
member price ignored in `totals._unit_price` → the member's four Python answers
move to the list price and the view does not, and the test names the registration
and both figures.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
    RegistrationItem,
)
from app.domains.activities.totals import (
    compute_registration_total,
    quote_lines,
    quote_registration,
)
from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.membership.api import Membership, has_valid_membership

pytestmark = pytest.mark.ui_agnostisch


@pytest.fixture
def world(db_session):
    db = db_session
    activity = Activity(name="Pariteit")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2099, 6, 1)))
    component = ActivitySubRegistration(
        activity_id=activity.id,
        name="Alles",
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        is_free=True,
    )
    db.add(component)
    db.flush()
    products = {
        "paid": ActivityProduct(
            component_id=component.id,
            name="Betalend",
            price=Decimal("12.50"),
            member_price=Decimal("9.75"),
            is_free=False,
        ),
        "free": ActivityProduct(
            component_id=component.id, name="Gratis", price=Decimal("0"), is_free=True
        ),
        "on_site": ActivityProduct(
            component_id=component.id,
            name="Ter plaatse",
            price=Decimal("4.00"),
            is_free=False,
            pay_on_site=True,
        ),
    }
    db.add_all(products.values())
    member = Member()
    person = Person(
        first_name="Lid", last_name="Pariteit", date_of_birth=date(1980, 1, 1), gender_code="F"
    )
    db.add_all([member, person])
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
    db.add(
        Membership(
            member_id=member.id,
            year=2099,
            is_active=True,
            valid_from=date(2099, 1, 1),
            valid_to=date(2099, 12, 31),
        )
    )
    db.flush()

    quantities = {"paid": 3, "free": 2, "on_site": 1}
    registrations = {}
    for key, person_id in (("member", person.id), ("guest", None)):
        registration = Registration(
            activity_id=activity.id,
            component_id=component.id,
            person_id=person_id,
            registered_at=datetime(2099, 3, 1, 12, 0, tzinfo=timezone.utc),
            registration_type="INDIVIDUAL",
            contact_name=f"Pariteit {key}",
            contact_email=f"{key}@example.org",
            phone="0470000000",
        )
        db.add(registration)
        db.flush()
        for name, quantity in quantities.items():
            db.add(
                RegistrationItem(
                    registration_id=registration.id,
                    product_id=products[name].id,
                    quantity=quantity,
                )
            )
        db.flush()
        db.refresh(registration)
        registrations[key] = registration
    return component, products, quantities, registrations


def _view_total(db, registration_id: int) -> Decimal:
    value = db.execute(
        text(
            "SELECT COALESCE(SUM(line_amount), 0) FROM reporting.f_registrations "
            "WHERE registration_id = :id"
        ),
        {"id": registration_id},
    ).scalar()
    return Decimal(value).quantize(Decimal("0.01"))


@pytest.mark.parametrize(
    ("who", "expected"),
    [
        # 3 × 9,75 at the member price; the free and pay-on-site lines do not count.
        ("member", Decimal("29.25")),
        # 3 × 12,50 at the list price.
        ("guest", Decimal("37.50")),
    ],
)
def test_every_way_of_asking_gives_the_same_total(db_session, world, who, expected):
    component, products, quantities, registrations = world
    registration = registrations[who]
    is_member = has_valid_membership(registration.person, registration.registered_at.date())
    assert is_member is (who == "member"), "the world is not what the test thinks it is"

    answers = {
        "Registration.total()": registration.total().amount,
        "compute_registration_total": compute_registration_total(registration)[0],
        "quote_registration": quote_registration(registration, {})[0],
        "quote_lines": quote_lines(
            component,
            {products[name].id: quantity for name, quantity in quantities.items()},
            is_member,
        )[0],
        "reporting.f_registrations": _view_total(db_session, registration.id),
    }
    different = {name: str(value) for name, value in answers.items() if value != expected}
    assert not different, (
        f"registration {registration.id} ({who}) should cost {expected}; these differ: {different}"
    )
