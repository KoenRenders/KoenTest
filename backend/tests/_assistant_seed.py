"""A situation big enough to answer the test-set questions (#917, CR-07 §3/§9).

The reporting seed (`_reporting_seed.py`) is built to catch join and tenant
mistakes, and it is deliberately tiny: four households. For the assistant that is
too small to say anything, and not because of a bug — the small-cell threshold
merges every group under five people, so almost every grouped answer over that
seed is one row reading "Samengevoegd". A harness on that data would grade the
threshold, not the assistant.

So this is a second situation, shaped by the questions it must answer: nine
households of three people across three streets, two board members, two
activities with their payments. Every group it produces is above the threshold on
purpose, and every number it should produce is written out in :data:`EXPECTED` —
worked out by hand from the description below, never read off a run.

**The people are 45, 38 and 10 years old** in every household, which puts them in
three different age buckets (41-60, 26-40, 6-12) with nine in each. That is what
makes question 6 answerable and its answer checkable.

The situation, in words:

- **Dorpsstraat** has four households, **Kerkstraat** three, **Molenweg** two. So
  "in which street do most members live" has one answer, and the runner-up is not
  a tie.
- **Bestuurslid A** looks after the first five households, **bestuurslid B** the
  other four.
- Everybody is a member for the current year, three people per household.
- The **Quiz** has six registrations from six households, one place each, at €5.
  The **Wandeling** has five registrations from five households, at €4. Six
  participants against five, and €30 against €20 — so "most participants" and
  "most revenue" have the same answer, which is worth knowing when an answer
  claims the wrong one.
- Every registration is charged; the Quiz ones are paid, the Wandeling ones are
  not. That gives "€30 received, €20 outstanding" as a second, independent check.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

TENANT = 2

STREETS = (("Dorpsstraat", 4), ("Kerkstraat", 3), ("Molenweg", 2))
AGES = (45, 38, 10)
QUIZ_PLACES = 6
WALK_PLACES = 5
QUIZ_PRICE = Decimal("5.00")
WALK_PRICE = Decimal("4.00")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed(db) -> dict:
    from app.domains.activities.api import (
        Activity, ActivityDate, ActivityProduct, ActivitySubRegistration,
        Registration, RegistrationItem,
    )
    from app.domains.mdm.api import (
        Address, Member, MemberPerson, Person, PostalCode,
    )
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    jaar = date.today().year
    postal = db.query(PostalCode).filter(PostalCode.postal_code == "2400").first()
    if postal is None:
        postal = PostalCode(postal_code="2400", municipality="Mol")
        db.add(postal)
        db.flush()

    # ── Board members: two people who are nobody's household head ────────────
    bestuur = []
    for naam in ("Anke", "Bram"):
        persoon = Person(tenant_id=TENANT, first_name=naam, last_name="Bestuur",
                         date_of_birth=date(jaar - 50, 5, 5), gender_code="M")
        db.add(persoon)
        db.flush()
        bestuur.append(persoon)

    # ── Nine households ──────────────────────────────────────────────────────
    households: list = []
    heads: list = []
    index = 0
    for straat, aantal in STREETS:
        for nummer in range(aantal):
            index += 1
            verantwoordelijke = bestuur[0] if index <= 5 else bestuur[1]
            member = Member(tenant_id=TENANT,
                            board_member_id=verantwoordelijke.id)
            db.add(member)
            db.flush()
            for rol, leeftijd in zip(("HOOFDLID", "PARTNER", "KIND"), AGES):
                persoon = Person(
                    tenant_id=TENANT, first_name=f"{rol.title()}{index}",
                    last_name=f"Gezin{index}",
                    date_of_birth=date(jaar - leeftijd, 6, 15), gender_code="M",
                )
                db.add(persoon)
                db.flush()
                db.add(MemberPerson(tenant_id=TENANT, member_id=member.id,
                                    person_id=persoon.id, relation_type=rol))
                db.add(Address(tenant_id=TENANT, person_id=persoon.id,
                               street=straat, house_number=str(nummer + 1),
                               postal_code_id=postal.id))
                if rol == "HOOFDLID":
                    heads.append(persoon)
            db.add(Membership(tenant_id=TENANT, member_id=member.id, year=jaar,
                              valid_from=date(jaar, 1, 1),
                              valid_to=date(jaar, 12, 31), is_active=True))
            db.flush()
            households.append(member)

    # ── Two activities ───────────────────────────────────────────────────────
    def activiteit(naam: str, prijs: Decimal):
        row = Activity(tenant_id=TENANT, name=naam)
        db.add(row)
        db.flush()
        db.add(ActivityDate(tenant_id=TENANT, activity_id=row.id,
                            start_date=date(jaar, 5, 1)))
        component = ActivitySubRegistration(
            tenant_id=TENANT, activity_id=row.id, name="Deelname",
            registration_type_code="INDIVIDUAL", price=prijs, is_free=False)
        db.add(component)
        db.flush()
        product = ActivityProduct(tenant_id=TENANT, component_id=component.id,
                                  name="Plaats", price=prijs, is_free=False)
        db.add(product)
        db.flush()
        return row, component, product

    quiz, quiz_component, quiz_product = activiteit("Quiz", QUIZ_PRICE)
    wandeling, walk_component, walk_product = activiteit("Wandeling", WALK_PRICE)

    def inschrijving(activity, component, product, persoon, prijs, betaald: bool):
        reg = Registration(
            tenant_id=TENANT, activity_id=activity.id, person_id=persoon.id,
            registered_at=datetime(jaar, 4, 1, 12, 0, tzinfo=timezone.utc),
            registration_type="INDIVIDUAL", component_id=component.id,
            contact_name="Contact", contact_email="contact@example.com",
            payment_method="online")
        db.add(reg)
        db.flush()
        db.add(RegistrationItem(tenant_id=TENANT, registration_id=reg.id,
                                product_id=product.id, quantity=1))
        aangemaakt = _now() - timedelta(days=20)
        db.add(PaymentRecord(
            tenant_id=TENANT, payable_type="registration", payable_id=reg.id,
            amount=prijs, method="online",
            status="paid" if betaald else "pending", type="charge",
            amount_paid=prijs if betaald else None, created_at=aangemaakt,
            paid_at=aangemaakt + timedelta(days=1) if betaald else None))
        db.flush()
        return reg

    for head in heads[:QUIZ_PLACES]:
        inschrijving(quiz, quiz_component, quiz_product, head, QUIZ_PRICE, True)
    for head in heads[:WALK_PLACES]:
        inschrijving(wandeling, walk_component, walk_product, head, WALK_PRICE,
                     False)

    db.commit()
    return {
        "year": jaar,
        "households": [m.id for m in households],
        "board_members": [p.id for p in bestuur],
        "activities": {"quiz": quiz.id, "wandeling": wandeling.id},
    }


# Every number below was worked out from the description in the module docstring.
EXPECTED = {
    "households": 9,
    "persons": 27,
    "per_street": {"Dorpsstraat": 12, "Kerkstraat": 9, "Molenweg": 6},
    "busiest_street": "Dorpsstraat",
    "per_board_member": {"A": 5, "B": 4},
    "participants": {"Quiz": QUIZ_PLACES, "Wandeling": WALK_PLACES},
    "revenue": {"Quiz": QUIZ_PRICE * QUIZ_PLACES,
                "Wandeling": WALK_PRICE * WALK_PLACES},
    "received": QUIZ_PRICE * QUIZ_PLACES,
    "outstanding": WALK_PRICE * WALK_PLACES,
    "age_groups": {"41-60": 9, "26-40": 9, "6-12": 9},
}
