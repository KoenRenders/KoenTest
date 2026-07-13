"""Tests voor lidmaatschap-bewust prijzen (#111) en het altijd koppelen van een
inschrijving aan de ingelogde persoon (#112).

De invarianten die ertoe doen (geld + datakoppeling):
  - Een ingelogd lid met een **geldig** lidmaatschap op de inschrijfdatum krijgt
    de ledenprijs; zonder geldig lidmaatschap de gewone prijs.
  - Een anonieme bezoeker krijgt altijd de gewone prijs.
  - Een ingelogde inschrijving wordt altijd aan de persoon gekoppeld
    (``person_id``), ook zónder geldig lidmaatschap.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.domains.auth.api import create_access_token


def _member_headers(email):
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def seed_household(db, email, *, is_active=True, valid_from=None, valid_to=None,
                   with_membership=True):
    """Eén gezin met één hoofdlid-persoon (e-mail als EMAIL-contact) en optioneel
    een lidmaatschap met opgegeven geldigheid."""
    from app.domains.membership.api import Membership
    from app.domains.mdm.api import Member, Person, MemberPerson
    from app.domains.mdm.api import ContactDetail

    member = Member()
    db.add(member)
    db.flush()
    person = Person(last_name="Lid", first_name="Test")
    db.add(person)
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
    db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email, is_primary=True))
    db.flush()
    if with_membership:
        today = date.today()
        db.add(Membership(
            member_id=member.id, year=today.year, is_active=is_active,
            valid_from=valid_from or date(today.year, 1, 1),
            valid_to=valid_to or date(today.year, 12, 31),
        ))
        db.flush()
    return member, person


def seed_activity_with_member_product(db, price="20.00", member_price="12.00"):
    from app.models.activity import Activity
    from app.models.activity_sub_registration import ActivitySubRegistration, ActivityProduct

    from app.models.activity import ActivityDate
    activity = Activity(name="Ledenprijs-activiteit")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=30)))
    db.flush()
    comp = ActivitySubRegistration(
        activity_id=activity.id, name="Onderdeel", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True,
    )
    db.add(comp)
    db.flush()
    product = ActivityProduct(
        component_id=comp.id, name="Product", price=Decimal(price),
        member_price=Decimal(member_price), is_free=False,
    )
    db.add(product)
    db.flush()
    return activity, comp, product


def _register(client, activity_id, comp_id, product_id, email, qty=2, headers=None):
    return client.post(
        f"/api/v1/activities/{activity_id}/register",
        headers=headers or {},
        json={
            "contact_name": "Test", "contact_email": email,
            "payment_method": "transfer", "component_id": comp_id,
            "items": [{"product_id": product_id, "quantity": qty}],
        },
    )


# ── #111: lidmaatschap-bewust prijzen ──────────────────────────────────────────

def test_member_with_valid_membership_gets_member_price(client, db_session):
    email = "geldiglid@example.com"
    seed_household(db_session, email)  # actief lidmaatschap, dekt vandaag
    activity, comp, product = seed_activity_with_member_product(db_session, "20.00", "12.00")

    resp = _register(client, activity.id, comp.id, product.id, email,
                     qty=2, headers=_member_headers(email))
    assert resp.status_code == 200, resp.text

    from app.domains.payment.api import PaymentRecord
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    assert rec.amount == Decimal("24.00")  # 2 × ledenprijs 12.00


def test_member_without_valid_membership_pays_regular_price(client, db_session):
    """Lidmaatschap verlopen (valid_to gisteren): gewone prijs, maar de
    inschrijving blijft aan de persoon gekoppeld (#112)."""
    email = "verlopenlid@example.com"
    yesterday = date.today() - timedelta(days=1)
    seed_household(db_session, email, valid_from=date(2000, 1, 1), valid_to=yesterday)
    activity, comp, product = seed_activity_with_member_product(db_session, "20.00", "12.00")

    resp = _register(client, activity.id, comp.id, product.id, email,
                     qty=2, headers=_member_headers(email))
    assert resp.status_code == 200, resp.text

    from app.domains.payment.api import PaymentRecord
    from app.models.activity import Registration
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    assert rec.amount == Decimal("40.00")  # 2 × gewone prijs 20.00
    reg = db_session.query(Registration).first()
    assert reg.person_id is not None  # #112: toch gekoppeld


def test_inactive_membership_pays_regular_price(client, db_session):
    """Niet-actief lidmaatschap (is_active=False) telt niet voor de ledenprijs."""
    email = "inactieflid@example.com"
    seed_household(db_session, email, is_active=False)
    activity, comp, product = seed_activity_with_member_product(db_session, "20.00", "12.00")

    resp = _register(client, activity.id, comp.id, product.id, email,
                     qty=1, headers=_member_headers(email))
    assert resp.status_code == 200, resp.text

    from app.domains.payment.api import PaymentRecord
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    assert rec.amount == Decimal("20.00")  # gewone prijs


def test_anonymous_registration_regular_price_and_no_person(client, db_session):
    activity, comp, product = seed_activity_with_member_product(db_session, "20.00", "12.00")
    resp = _register(client, activity.id, comp.id, product.id, "anon@example.com", qty=1)
    assert resp.status_code == 200, resp.text

    from app.domains.payment.api import PaymentRecord
    from app.models.activity import Registration
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    assert rec.amount == Decimal("20.00")
    reg = db_session.query(Registration).first()
    assert reg.person_id is None  # #112: anoniem → geen koppeling


# ── #112: koppeling aan persoon ────────────────────────────────────────────────

def test_logged_in_registration_links_person(client, db_session):
    email = "koppellid@example.com"
    _member, person = seed_household(db_session, email)
    activity, comp, product = seed_activity_with_member_product(db_session, "5.00", "5.00")

    resp = _register(client, activity.id, comp.id, product.id, email,
                     qty=1, headers=_member_headers(email))
    assert resp.status_code == 200, resp.text

    from app.models.activity import Registration
    reg = db_session.query(Registration).first()
    assert reg.person_id == person.id


# ── service-laag ───────────────────────────────────────────────────────────────

def test_has_valid_membership_service(db_session):
    from app.domains.membership.api import has_valid_membership

    assert has_valid_membership(None) is False

    _m, person = seed_household(db_session, "svc@example.com")
    assert has_valid_membership(person, date.today()) is True
    # Buiten de periode
    assert has_valid_membership(person, date.today() - timedelta(days=10000)) is False
