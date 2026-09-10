"""A known situation, with known numbers, for the reporting facts (#832 test 1).

CR-06 §9 asks for known-seed numbers, and for one reason: *a plausible but wrong
number is reporting's worst failure*. A test that asserts "the sum is a positive
Decimal" would stay green through a broken join, a lost soft-delete filter or a
tenant leak. So this module builds one exact situation — two tenants, three
membership years, a lapsed household, a refund, an open balance, an anonymous
registration and a registration without lines — and states every number it should
produce in :data:`EXPECTED`. The tests assert those numbers and nothing softer.

**Dates are relative to today, values are not.** The membership years are "this
year and the two before it", and the payment dates are a fixed number of days ago,
so the ageing buckets and the age groups still mean the same thing when this test
runs next year. What must not move — amounts, counts, statuses — is written out.

**What is deliberately in here to be caught:**

- a household in tenant B, so a tenant leak shows up as a number that is too high;
- a soft-deleted registration and a soft-deleted membership, so a view that forgets
  ``deleted_at IS NULL`` counts them;
- a member price, so the registration amount is wrong if the member rule is lost;
- a registration with no lines, so a fact that inner-joins its lines loses it;
- **a household that joins in October for next year.** From mid-September a
  membership can be taken out for the following year: ``valid_from`` falls in this
  year while ``year`` is the next one, and the free tail of this year is a gift,
  not a membership of this year. The fact counts it once, in ``year``. A star
  schema that reads the validity dates instead would count it twice, and both
  numbers would look reasonable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

TENANT_A = 2
TENANT_B = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _year() -> int:
    return date.today().year


def seed(db) -> dict:
    """Build the situation. Returns the ids the tests need to reach into it."""
    from app.domains.activities.api import (
        Activity, ActivityDate, ActivityProduct, ActivitySubRegistration,
        Registration, RegistrationItem,
    )
    from app.domains.mdm.api import Member, MemberPerson, Person, PostalCode
    from app.domains.mdm.api import Address
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord
    from app.soft_delete import soft_delete

    y2 = _year()
    y1, y0 = y2 - 1, y2 - 2
    y3 = y2 + 1
    born = date(y2 - 30, 6, 15)

    postal = PostalCode(postal_code="2400", municipality="Mol")
    db.add(postal)
    db.flush()

    def household(tenant: int, persons: int) -> tuple:
        member = Member(tenant_id=tenant)
        db.add(member)
        db.flush()
        people = []
        for index in range(persons):
            person = Person(tenant_id=tenant, first_name=f"Persoon{index}",
                            last_name="Test", date_of_birth=born, gender_code="M")
            db.add(person)
            db.flush()
            db.add(MemberPerson(tenant_id=tenant, member_id=member.id,
                                person_id=person.id,
                                relation_type="HOOFDLID" if index == 0 else "PARTNER"))
            people.append(person)
        db.add(Address(tenant_id=tenant, person_id=people[0].id, street="Straat",
                       house_number="1", postal_code_id=postal.id))
        db.flush()
        return member, people

    # ── Households ──────────────────────────────────────────────────────────
    # H1 renews every year, H2 lapses after the first, H3 joins in the last one.
    h1, h1_people = household(TENANT_A, 2)
    h2, _h2_people = household(TENANT_A, 1)
    h3, h3_people = household(TENANT_A, 3)
    h4, _h4_people = household(TENANT_A, 2)
    hb, _hb_people = household(TENANT_B, 4)

    def membership(member, year: int, tenant: int = TENANT_A, valid: bool = False):
        row = Membership(
            tenant_id=tenant, member_id=member.id, year=year, is_active=True,
            valid_from=date(year, 1, 1) if valid else None,
            valid_to=date(year, 12, 31) if valid else None,
        )
        db.add(row)
        db.flush()
        return row

    ms_h1_y0 = membership(h1, y0)
    membership(h1, y1)
    ms_h1_y2 = membership(h1, y2, valid=True)     # valid: gives H1 the member price
    membership(h2, y0)
    ms_h3_y2 = membership(h3, y2)
    membership(hb, y2, tenant=TENANT_B)

    # H4 joins in October of this year for NEXT year. The membership is already
    # valid — that is the point of the September rule — but it belongs to `year`,
    # and to that year only.
    db.add(Membership(tenant_id=TENANT_A, member_id=h4.id, year=y3, is_active=True,
                      valid_from=date(y2, 10, 1), valid_to=date(y3, 12, 31)))
    db.flush()

    # A soft-deleted membership must not be counted anywhere. H2 in the last year
    # would otherwise turn a LAPSED row into a RENEWED one.
    deleted_ms = membership(h2, y2)
    soft_delete(deleted_ms)
    db.flush()

    # ── Activity ────────────────────────────────────────────────────────────
    activity = Activity(tenant_id=TENANT_A, name="Quiz")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(tenant_id=TENANT_A, activity_id=activity.id,
                        start_date=date(y2, 3, 15)))
    component = ActivitySubRegistration(
        tenant_id=TENANT_A, activity_id=activity.id, name="Quizploeg",
        registration_type_code="INDIVIDUAL", price=Decimal("0"), is_free=True,
    )
    db.add(component)
    db.flush()
    product = ActivityProduct(
        tenant_id=TENANT_A, component_id=component.id, name="Deelname",
        price=Decimal("10.00"), member_price=Decimal("8.00"), is_free=False,
    )
    db.add(product)
    db.flush()

    def registration(person, day: int, quantity: int | None, team: str | None = None):
        row = Registration(
            tenant_id=TENANT_A, activity_id=activity.id,
            person_id=person.id if person else None,
            registered_at=datetime(y2, 1, day, 12, 0, tzinfo=timezone.utc),
            registration_type="INDIVIDUAL", component_id=component.id,
            contact_name="Contact", contact_email="contact@example.com",
            team_name=team, payment_method="online",
        )
        db.add(row)
        db.flush()
        if quantity is not None:
            db.add(RegistrationItem(tenant_id=TENANT_A, registration_id=row.id,
                                    product_id=product.id, quantity=quantity))
            db.flush()
        return row

    # A member (H1) pays the member price; an anonymous registrant pays full; a
    # third registers without ever picking a product.
    reg_member = registration(h1_people[0], 15, 2, team="De Slimmeriken")
    reg_guest = registration(None, 16, 1)
    registration(h3_people[0], 17, None)

    deleted_reg = registration(h3_people[1], 18, 5)
    soft_delete(deleted_reg)
    db.flush()

    # ── Payments ────────────────────────────────────────────────────────────
    def payment(payable_type: str, payable_id, amount: str, *, method: str,
                status: str, paid: str | None, days_ago: int,
                record_type: str = "charge", tenant: int = TENANT_A):
        created = _now() - timedelta(days=days_ago)
        row = PaymentRecord(
            tenant_id=tenant, payable_type=payable_type, payable_id=payable_id,
            amount=Decimal(amount), method=method, status=status,
            type=record_type,
            amount_paid=Decimal(paid) if paid is not None else None,
            created_at=created,
            paid_at=(created + timedelta(days=4)) if status == "paid" else None,
        )
        db.add(row)
        db.flush()
        return row

    payment("registration", reg_member.id, "16.00", method="online",
            status="paid", paid="16.00", days_ago=30)
    payment("registration", reg_member.id, "-6.00", method="online",
            status="paid", paid="-6.00", days_ago=20, record_type="refund")
    payment("registration", reg_guest.id, "10.00", method="transfer",
            status="pending", paid=None, days_ago=120)
    payment("membership", ms_h1_y2.id, "35.00", method="online",
            status="paid", paid="35.00", days_ago=30)
    payment("membership", ms_h3_y2.id, "35.00", method="transfer",
            status="pending", paid=None, days_ago=10)
    payment("membership", ms_h1_y0.id, "30.00", method="cash",
            status="paid", paid="30.00", days_ago=200)

    # Tenant B pays too — every sum below proves it stayed on its own side.
    payment("registration", 999_999, "500.00", method="online", status="paid",
            paid="500.00", days_ago=5, tenant=TENANT_B)

    db.commit()
    return {
        "years": (y0, y1, y2, y3),
        "households": {"h1": h1.id, "h2": h2.id, "h3": h3.id, "h4": h4.id,
                       "b": hb.id},
        "activity_id": activity.id,
        "component_id": component.id,
        "product_id": product.id,
        "registrations": {"member": reg_member.id, "guest": reg_guest.id},
    }


# What the seed above must produce. Every number here was worked out by hand from
# the situation, not read off a first run — a number copied from the code it is
# meant to check proves only that the code is consistent with itself.
EXPECTED = {
    # f_memberships, per year, tenant A
    "memberships": {
        # Index = offset in the `years` tuple: 0 = two years ago, 2 = this year,
        # 3 = next year (where only H4 is a member, and H1 and H3 read as lapsed
        # because they have not renewed for it yet).
        "households": {0: 2, 1: 1, 2: 2, 3: 1},
        "new": {0: 2, 1: 0, 2: 1, 3: 1},
        "renewed": {0: 0, 1: 1, 2: 1, 3: 0},
        "lapsed": {0: 0, 1: 1, 2: 0, 3: 2},
        "persons": {0: 3, 1: 2, 2: 5, 3: 2},
        # Membership money: this year has charges (35 + 35), of which 35 was
        # received; two years ago H1 paid 30. H4 has not been invoiced yet.
        "charged": {0: Decimal("30.00"), 1: Decimal("0.00"),
                    2: Decimal("70.00"), 3: Decimal("0.00")},
        "paid": {0: Decimal("30.00"), 1: Decimal("0.00"),
                 2: Decimal("35.00"), 3: Decimal("0.00")},
    },
    # f_registrations, tenant A — the soft-deleted one is not among them
    "registrations": {
        "count": 3,
        "quantity": 3,
        "amount": Decimal("26.00"),   # 2 x 8.00 (member price) + 1 x 10.00
    },
    # f_payments, tenant A
    "payments": {
        "count": 6,
        "amount": Decimal("120.00"),      # 16 - 6 + 10 + 35 + 35 + 30
        "amount_paid": Decimal("75.00"),  # 16 - 6 + 0 + 35 + 0 + 30
        "open": Decimal("45.00"),
        "refunded": Decimal("6.00"),
        "per_payable_type": {
            "Activiteit": {"amount": Decimal("20.00"), "paid": Decimal("10.00")},
            "Lidgeld": {"amount": Decimal("100.00"), "paid": Decimal("65.00")},
        },
        "per_activity": {"Quiz": {"amount": Decimal("20.00"),
                                  "paid": Decimal("10.00")}},
        "per_method": {
            "Online": Decimal("45.00"),          # 16 - 6 + 35
            "Overschrijving": Decimal("45.00"),  # 10 + 35
            "Cash": Decimal("30.00"),
        },
        # The paid records were created 30/20/200 days ago and settled four days
        # later, so every one of them took exactly four days.
        "days_to_paid": 4,
    },
    "tenant_b": {"payments_amount": Decimal("500.00"), "households": 1},
}
